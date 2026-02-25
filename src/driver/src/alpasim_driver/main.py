# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-2026 NVIDIA Corporation

"""Unified driver implementation for Alpasim supporting multiple model backends."""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import pickle
import queue
import socket
import threading
from dataclasses import dataclass, field
from importlib.metadata import version
from io import BytesIO
from typing import Any, Callable, Optional, cast

import hydra
import matplotlib.pyplot as plt
import numpy as np
import torch
from alpasim_dds.endpoints.driver_server import DriverServerEndpoints
from alpasim_dds.participant import get_participant
from alpasim_dds.types.camera import AvailableCamera
from alpasim_dds.types.common import (
    DynamicState,
    Pose,
    PoseAtTime,
    Quat,
    Trajectory,
    Vec3,
)
from alpasim_dds.types.egodriver import (
    DriveRequest,
    DriveResponse,
    DriveResponseDebugInfo,
    DriveSessionCloseRequest,
    DriveSessionRequest,
    GroundTruthRequest,
    RolloutCameraImage,
    RolloutEgoTrajectory,
    Route,
    RouteRequest,
)
from alpasim_dds.types.common import APIVersion, SessionRequestStatus, VersionResponse
from omegaconf import OmegaConf
from PIL import Image

from .frame_cache import FrameCache
from .models import DriveCommand
from .models.ar1_model import AR1Model
from .models.base import BaseTrajectoryModel, ModelPrediction
from .models.manual_model import ManualModel
from .models.transfuser_model import TransfuserModel
from .models.vam_model import VAMModel
from .navigation import determine_command_from_route
from .rectification import (
    FthetaToPinholeRectifier,
    build_ftheta_rectifier_for_resolution,
)
from .schema import DriverConfig, ModelConfig, ModelType, RectificationTargetConfig
from .trajectory_optimizer import (
    TrajectoryOptimizer,
    VehicleConstraints,
    add_heading_to_trajectory,
)

logger = logging.getLogger(__name__)


def _get_external_ip() -> str:
    """Get the external IP address of this machine."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "unknown"


def _quat_to_yaw(quaternion: Quat) -> float:
    """Extract the yaw component (rotation about +Z) from a quaternion."""
    return np.arctan2(
        2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
        1.0 - 2.0 * (quaternion.y * quaternion.y + quaternion.z * quaternion.z),
    )


def _yaw_to_quat(yaw: float) -> Quat:
    """Create a Z-only rotation quaternion from the provided yaw angle."""
    half_yaw = 0.5 * yaw
    return Quat(w=float(np.cos(half_yaw)), x=0.0, y=0.0, z=float(np.sin(half_yaw)))


def _rig_est_offsets_to_local_positions(
    current_pose_in_local: PoseAtTime, offsets_in_rig: np.ndarray
) -> np.ndarray:
    """Project rig-est displacements onto the local-frame pose anchored by `current_pose`."""
    curr_x = current_pose_in_local.pose.vec.x
    curr_y = current_pose_in_local.pose.vec.y

    curr_quat = current_pose_in_local.pose.quat
    curr_yaw = _quat_to_yaw(curr_quat)

    cos_yaw = np.cos(curr_yaw)
    sin_yaw = np.sin(curr_yaw)

    offsets_array = np.asarray(offsets_in_rig, dtype=float).reshape(-1, 2)
    rotation = np.array([[cos_yaw, -sin_yaw], [sin_yaw, cos_yaw]], dtype=float)
    rotated_offsets = offsets_array @ rotation.T

    translation = np.array([curr_x, curr_y], dtype=float)
    return rotated_offsets + translation


# Unique queue marker instructing the worker thread to flush and exit.
_SENTINEL_JOB = object()


@dataclass
class DriveJob:
    """Unit of work processed by the background inference worker."""

    session_id: str
    session: "Session"
    command: DriveCommand
    pose: Optional[PoseAtTime]
    timestamp_us: int
    result: asyncio.Future[DriveResponse]


@dataclass
class Session:
    """Represents a driver session."""

    uuid: str
    seed: int
    debug_scene_id: str

    frame_caches: dict[str, FrameCache]
    available_cameras_logical_ids: set[str]
    desired_cameras_logical_ids: set[str]
    camera_specs: dict[str, AvailableCamera]
    rectification_cfg: Optional[dict[str, RectificationTargetConfig]] = None
    rectifiers: dict[str, Optional[FthetaToPinholeRectifier]] = field(
        default_factory=dict
    )
    poses: list[PoseAtTime] = field(default_factory=list)
    dynamic_states: list[tuple[int, DynamicState]] = field(default_factory=list)
    current_command: DriveCommand = DriveCommand.STRAIGHT

    @staticmethod
    def create(
        request: DriveSessionRequest,
        cfg: DriverConfig,
        context_length: int,
        subsample_factor: int = 1,
    ) -> Session:
        """Create a new driver session."""
        debug_scene_id = (
            request.debug_info.scene_id
            if request.debug_info is not None and request.debug_info.scene_id
            else request.session_uuid
        )

        available_cameras_logical_ids: set[str] = set()
        vehicle = request.rollout_spec.vehicle
        if vehicle is None:
            raise ValueError("Vehicle definition is required in DriveSessionRequest")

        camera_specs: dict[str, AvailableCamera] = {}
        for camera_def in vehicle.available_cameras:
            if not camera_def.logical_id:
                raise ValueError(
                    "Logical ID is required for each camera in VehicleDefinition"
                )
            available_cameras_logical_ids.add(camera_def.logical_id)
            camera_specs[camera_def.logical_id] = camera_def
            logger.debug(
                f"Available camera: {camera_def.logical_id}, "
                f"resolution: ({camera_def.intrinsics.resolution_h}, {camera_def.intrinsics.resolution_w}), "
                f"intrinsics: {camera_def.intrinsics}"
            )

        desired_cameras_logical_ids = set(cfg.inference.use_cameras)
        if not desired_cameras_logical_ids:
            raise ValueError("No cameras specified in inference configuration")

        missing_defs = desired_cameras_logical_ids - set(camera_specs.keys())
        if missing_defs:
            raise ValueError(
                f"Requested cameras {sorted(missing_defs)} are missing from the rollout spec"
            )
        if cfg.rectification is not None:
            missing_rect = desired_cameras_logical_ids - set(cfg.rectification.keys())
            if missing_rect:
                raise ValueError(
                    "Missing rectification targets for cameras "
                    f"{sorted(missing_rect)} in driver configuration"
                )

        rectifiers: dict[str, Optional[FthetaToPinholeRectifier]] = {
            logical_id: None for logical_id in desired_cameras_logical_ids
        }

        frame_caches: dict[str, FrameCache] = {}
        for camera_id in cfg.inference.use_cameras:
            frame_caches[camera_id] = FrameCache(
                context_length=context_length,
                camera_id=camera_id,
                subsample_factor=subsample_factor,
            )

        session = Session(
            uuid=request.session_uuid,
            seed=request.random_seed,
            debug_scene_id=debug_scene_id,
            frame_caches=frame_caches,
            available_cameras_logical_ids=available_cameras_logical_ids,
            desired_cameras_logical_ids=desired_cameras_logical_ids,
            camera_specs=camera_specs,
            rectification_cfg=cfg.rectification,
            rectifiers=rectifiers,
        )

        return session

    def add_image(
        self, logical_id: str, image_tensor: np.ndarray, timestamp_us: int
    ) -> None:
        """Add an image observation for a specific camera."""
        if logical_id not in self.frame_caches:
            raise ValueError(
                f"Camera {logical_id} not in desired cameras: {list(self.frame_caches.keys())}"
            )
        self.frame_caches[logical_id].add_image(timestamp_us, image_tensor)

    def all_cameras_ready(self) -> bool:
        """Check if all cameras have enough frames for inference."""
        return all(cache.has_enough_frames() for cache in self.frame_caches.values())

    def min_frame_count(self) -> int:
        """Return the minimum frame count across all cameras."""
        if not self.frame_caches:
            return 0
        return min(cache.frame_count() for cache in self.frame_caches.values())

    def _maybe_build_rectifier(
        self, logical_id: str, source_resolution_hw: tuple[int, int]
    ) -> Optional[FthetaToPinholeRectifier]:
        """Instantiate and cache a rectifier once the true source resolution is known."""
        if self.rectification_cfg is None or logical_id not in self.rectification_cfg:
            return None

        if self.rectifiers.get(logical_id) is not None:
            return self.rectifiers[logical_id]

        rectifier = build_ftheta_rectifier_for_resolution(
            camera_proto=self.camera_specs[logical_id],
            target_cfg=self.rectification_cfg[logical_id],
            source_resolution_hw=source_resolution_hw,
        )
        self.rectifiers[logical_id] = rectifier
        logger.debug(
            "Built f-theta rectifier for %s using source resolution %s",
            logical_id,
            source_resolution_hw,
        )
        return rectifier

    def rectify_image(self, logical_id: str, image: Image.Image) -> Image.Image:
        """Apply rectification for logical_id if configured."""
        source_resolution_hw = (image.height, image.width)
        rectifier = self._maybe_build_rectifier(logical_id, source_resolution_hw)
        if rectifier is None:
            return image
        return Image.fromarray(rectifier.rectify(np.array(image)))

    def add_egoposes(self, traj: Trajectory) -> None:
        """Add rig-est pose observations in the local frame."""
        self.poses.extend(traj.poses)
        self.poses = sorted(self.poses, key=lambda pose: pose.timestamp_us)
        logger.debug(f"poses: {self.poses}")

    def add_dynamic_state(
        self, timestamp_us: int, dynamic_state: Optional[DynamicState]
    ) -> None:
        """Add a dynamic state observation at the given timestamp."""
        if dynamic_state is None:
            raise ValueError("Dynamic state is required")
        self.dynamic_states.append((timestamp_us, dynamic_state))
        self.dynamic_states = sorted(self.dynamic_states, key=lambda x: x[0])
        logger.debug(
            f"dynamic_state at {timestamp_us}: "
            f"lin_vel=({dynamic_state.linear_velocity.x:.2f}, "
            f"{dynamic_state.linear_velocity.y:.2f}, "
            f"{dynamic_state.linear_velocity.z:.2f})"
        )

    def update_command_from_route(
        self,
        route: Route,
        use_waypoint_commands: bool,
        command_distance_threshold: Optional[float] = None,
        min_lookahead_distance: Optional[float] = None,
    ) -> None:
        """Derive command from waypoints using route geometry."""
        if not use_waypoint_commands or len(route.waypoints) < 1:
            return

        if len(self.poses) == 0:
            return

        if command_distance_threshold is None or min_lookahead_distance is None:
            raise ValueError(
                "command_distance_threshold and min_lookahead_distance must be provided "
                "when use_waypoint_commands is True"
            )

        self.current_command = determine_command_from_route(
            route=route,
            command_distance_threshold=command_distance_threshold,
            min_lookahead_distance=min_lookahead_distance,
        )

        logger.debug(
            "Command updated: %s",
            self.current_command.name,
        )


def async_log_call(func: Callable) -> Callable:
    """Helper to add logging for calls (sync or async)."""

    @functools.wraps(func)
    async def async_wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            logger.debug("Calling %s", func.__name__)
            return await func(*args, **kwargs)
        except Exception:
            logger.exception("Exception in %s", func.__name__)
            raise

    return async_wrapped


def _create_model(
    cfg: ModelConfig,
    device: torch.device,
    camera_ids: list[str],
    context_length: int | None,
    output_frequency_hz: int,
) -> BaseTrajectoryModel:
    """Factory method to create the appropriate model."""
    if cfg.model_type == ModelType.VAM:
        if cfg.tokenizer_path is None:
            raise ValueError("VAM model requires tokenizer_path")
        return VAMModel(
            checkpoint_path=cfg.checkpoint_path,
            tokenizer_path=cfg.tokenizer_path,
            device=device,
            camera_ids=camera_ids,
            context_length=context_length or 8,
        )
    elif cfg.model_type == ModelType.TRANSFUSER:
        return TransfuserModel(
            checkpoint_path=cfg.checkpoint_path,
            device=device,
            camera_ids=camera_ids,
        )
    elif cfg.model_type == ModelType.ALPAMAYO_R1:
        return AR1Model(
            checkpoint_path=cfg.checkpoint_path,
            device=device,
            camera_ids=camera_ids,
            context_length=context_length or 4,
        )
    elif cfg.model_type == ModelType.MANUAL:
        return ManualModel(
            camera_ids=camera_ids,
            output_frequency_hz=output_frequency_hz,
            context_length=context_length or 1,
        )
    else:
        raise ValueError(f"Unknown model type: {cfg.model_type}")


class EgoDriverService:
    """Unified policy service supporting multiple model backends (DDS)."""

    def __init__(
        self,
        cfg: DriverConfig,
        loop: asyncio.AbstractEventLoop,
        endpoints: DriverServerEndpoints,
    ) -> None:
        self._cfg = cfg
        self._loop = loop
        self._endpoints = endpoints
        self._stop = asyncio.Event()

        self._device = torch.device(
            cfg.model.device if torch.cuda.is_available() else "cpu"
        )

        self._model = _create_model(
            cfg.model,
            self._device,
            camera_ids=cfg.inference.use_cameras,
            context_length=cfg.inference.context_length,
            output_frequency_hz=cfg.inference.output_frequency_hz,
        )

        self._context_length = (
            cfg.inference.context_length
            if cfg.inference.context_length is not None
            else self._model.context_length
        )

        logger.info(
            "Initialized %s model with %d cameras, context_length=%d",
            cfg.model.model_type.value,
            self._model.num_cameras,
            self._context_length,
        )

        self._max_batch_size = cfg.inference.max_batch_size
        self._job_queue: queue.Queue[DriveJob | object] = queue.Queue()
        self._worker_stop = threading.Event()
        self._worker_thread = threading.Thread(
            target=self._worker_main,
            name="ego-driver-worker",
            daemon=True,
        )
        self._sessions: dict[str, Session] = {}

        self._trajectory_optimizer: Optional[TrajectoryOptimizer] = None
        self._vehicle_constraints: Optional[VehicleConstraints] = None
        if cfg.trajectory_optimizer.enabled:
            opt_cfg = cfg.trajectory_optimizer
            self._trajectory_optimizer = TrajectoryOptimizer(
                smoothness_weight=opt_cfg.smoothness_weight,
                deviation_weight=opt_cfg.deviation_weight,
                comfort_weight=opt_cfg.comfort_weight,
                max_iterations=opt_cfg.max_iterations,
                enable_frenet_retiming=opt_cfg.retime_in_frenet,
                retime_alpha=opt_cfg.retime_alpha,
            )
            self._vehicle_constraints = VehicleConstraints(
                max_deviation=opt_cfg.max_deviation,
                max_heading_change=opt_cfg.max_heading_change,
                max_speed=opt_cfg.max_speed,
                max_accel=opt_cfg.max_accel,
                max_abs_yaw_rate=opt_cfg.max_abs_yaw_rate,
                max_abs_yaw_acc=opt_cfg.max_abs_yaw_acc,
                max_lon_acc_pos=opt_cfg.max_lon_acc_pos,
                max_lon_acc_neg=opt_cfg.max_lon_acc_neg,
                max_abs_lon_jerk=opt_cfg.max_abs_lon_jerk,
            )

            logger.info(
                "Trajectory optimizer enabled with retiming=%s, alpha=%.2f",
                opt_cfg.retime_in_frenet,
                opt_cfg.retime_alpha,
            )
            logger.info(f"Trajectory optimizer config: {opt_cfg}")

        self._worker_thread.start()

    async def stop_worker(self) -> None:
        """Signal the worker thread to stop and wait for it to exit."""
        if not self._worker_stop.is_set():
            self._worker_stop.set()
            self._job_queue.put_nowait(_SENTINEL_JOB)
        if self._worker_thread.is_alive():
            await asyncio.to_thread(self._worker_thread.join)

    def _worker_main(self) -> None:
        """Blocking worker loop that batches drive jobs for inference."""
        torch.set_grad_enabled(False)
        batch_count = 0
        total_items = 0
        while True:
            if self._worker_stop.is_set():
                break

            try:
                job = self._job_queue.get()
            except queue.Empty:
                continue

            if job is _SENTINEL_JOB:
                break

            batch: list[DriveJob] = [job]

            stop_after_batch = False
            while len(batch) < self._max_batch_size:
                try:
                    next_job = self._job_queue.get_nowait()
                except queue.Empty:
                    break
                if next_job is _SENTINEL_JOB:
                    stop_after_batch = True
                    break
                batch.append(next_job)

            try:
                logger.debug("Running inference batch of size %s", len(batch))
                responses = self._run_batch(batch)
                batch_count += 1
                total_items += len(batch)
                if batch_count % 100 == 0:
                    logger.info(
                        "Inference batches: %d processed, %d total items, avg size %.1f",
                        batch_count,
                        total_items,
                        total_items / batch_count,
                    )
            except Exception as exc:
                logger.exception("Inference batch failed")
                for pending_job in batch:
                    self._loop.call_soon_threadsafe(
                        pending_job.result.set_exception, exc
                    )
            else:
                logger.debug("Inference batch succeeded")
                for pending_job, response in zip(batch, responses, strict=True):
                    self._loop.call_soon_threadsafe(
                        pending_job.result.set_result, response
                    )

            if stop_after_batch:
                break

        self._worker_stop.set()
        while True:
            try:
                leftover = self._job_queue.get_nowait()
            except queue.Empty:
                break
            if leftover is _SENTINEL_JOB:
                continue
            self._loop.call_soon_threadsafe(leftover.result.cancel)

    def _get_speed_and_acceleration(self, session: Session) -> tuple[float, float]:
        """Extract speed and acceleration from session's dynamic state."""
        if not session.dynamic_states:
            raise ValueError(
                "No dynamic states available in session. "
                "Ensure egomotion observations are submitted before calling drive."
            )

        _, state = session.dynamic_states[-1]
        speed = np.sqrt(state.linear_velocity.x**2 + state.linear_velocity.y**2)
        acceleration = state.linear_acceleration.x

        return float(speed), float(acceleration)

    def _prepare_camera_images(
        self, session: Session
    ) -> dict[str, list[tuple[int, np.ndarray]]]:
        """Collect raw images from frame caches for all cameras."""
        camera_images: dict[str, list[tuple[int, np.ndarray]]] = {}

        for cam_id in self._model.camera_ids:
            frame_cache = session.frame_caches[cam_id]
            entries = frame_cache.latest_frame_entries(self._context_length)
            camera_images[cam_id] = [(e.timestamp_us, e.image) for e in entries]

        return camera_images

    def _maybe_save_rectification_debug_image(
        self,
        pre_image: Image.Image,
        post_image: Image.Image,
        scene_id: str,
        logical_id: str,
        timestamp_us: int,
    ) -> None:
        """Save pre- and post-rectification images side by side for debugging."""
        if not self._cfg.plot_debug_images:
            return

        if not self._cfg.output_dir:
            logger.warning("Output directory is not set; skipping rectification dump")
            return

        session_folder = os.path.join(
            self._cfg.output_dir, scene_id, "rectification_debug"
        )
        os.makedirs(session_folder, exist_ok=True)

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))

        axes[0].imshow(np.array(pre_image))
        axes[0].set_title(f"Pre-rectification ({pre_image.width}x{pre_image.height})")
        axes[0].axis("off")

        axes[1].imshow(np.array(post_image))
        axes[1].set_title(
            f"Post-rectification ({post_image.width}x{post_image.height})"
        )
        axes[1].axis("off")

        fig.suptitle(f"{logical_id} @ {timestamp_us} us")
        fig.tight_layout()

        filename = f"{timestamp_us}_{logical_id}_rectification.png"
        output_path = os.path.join(session_folder, filename)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

    def _run_batch(self, batch: list[DriveJob]) -> list[ModelPrediction]:
        """Run inference for a batch of jobs using the model abstraction."""
        responses: list[ModelPrediction] = []

        for job in batch:
            camera_images = self._prepare_camera_images(job.session)
            speed, acceleration = self._get_speed_and_acceleration(job.session)

            prediction = self._model.predict(
                camera_images=camera_images,
                command=job.command,
                speed=speed,
                acceleration=acceleration,
                ego_pose_at_time_history_local=job.session.poses,
            )
            responses.append(prediction)

        return responses

    def start_session(self, request: DriveSessionRequest) -> SessionRequestStatus:
        if request.session_uuid in self._sessions:
            logger.error(f"Session {request.session_uuid} already exists.")
            return SessionRequestStatus()

        logger.info(
            "Starting %s session %s",
            self._cfg.model.model_type.value,
            request.session_uuid,
        )
        session = Session.create(
            request,
            self._cfg,
            self._context_length,
            subsample_factor=self._cfg.inference.subsample_factor,
        )
        self._sessions[request.session_uuid] = session
        return SessionRequestStatus()

    def close_session(self, request: DriveSessionCloseRequest) -> None:
        if request.session_uuid not in self._sessions:
            raise KeyError(f"Session {request.session_uuid} does not exist.")
        logger.info(f"Closing session {request.session_uuid}")
        del self._sessions[request.session_uuid]

    def get_version(self, request) -> VersionResponse:
        driver_version = version("alpasim_driver")
        model_type = self._cfg.model.model_type.value
        return VersionResponse(
            version_id=f"{model_type}-driver-{driver_version}",
            git_hash="unknown",
            api_version=APIVersion(major=0, minor=0, patch=1),
        )

    def submit_image_observation(self, request: RolloutCameraImage) -> None:
        logger.debug(
            "submit_image_observation called: session=%s, logical_id=%s",
            request.session_uuid,
            request.camera_image.logical_id,
        )
        camera_image = request.camera_image
        image = Image.open(BytesIO(bytes(camera_image.image_bytes)))
        session = self._sessions[request.session_uuid]
        if camera_image.logical_id not in session.desired_cameras_logical_ids:
            raise ValueError(f"Camera {camera_image.logical_id} not in desired cameras")

        rectified_image = session.rectify_image(camera_image.logical_id, image)
        self._maybe_save_rectification_debug_image(
            image,
            rectified_image,
            session.debug_scene_id,
            camera_image.logical_id,
            camera_image.frame_end_us,
        )
        session.add_image(
            camera_image.logical_id,
            np.array(rectified_image),
            camera_image.frame_end_us,
        )

    def submit_egomotion_observation(self, request: RolloutEgoTrajectory) -> None:
        logger.debug(
            "submit_egomotion_observation called: session=%s",
            request.session_uuid,
        )
        session = self._sessions[request.session_uuid]

        if len(request.trajectory.poses) != 1:
            raise ValueError(
                f"Expected exactly 1 pose in egomotion trajectory, got {len(request.trajectory.poses)}. "
                "The driver assumes dynamic_state corresponds to the single pose's timestamp. "
                "If multi-pose trajectories are intentional, update the driver to handle them correctly."
            )

        session.add_egoposes(request.trajectory)

        if request.dynamic_state is not None and request.trajectory.poses:
            latest_timestamp_us = max(
                pose.timestamp_us for pose in request.trajectory.poses
            )
            session.add_dynamic_state(latest_timestamp_us, request.dynamic_state)

    def submit_route(self, request: RouteRequest) -> None:
        logger.debug(
            "submit_route called: session=%s, waypoint_count=%s",
            request.session_uuid,
            len(request.route.waypoints),
        )
        if self._cfg.route is not None:
            self._sessions[request.session_uuid].update_command_from_route(
                request.route,
                self._cfg.route.use_waypoint_commands,
                self._cfg.route.command_distance_threshold,
                self._cfg.route.min_lookahead_distance,
            )
        else:
            self._sessions[request.session_uuid].update_command_from_route(
                request.route,
                use_waypoint_commands=False,
            )

    def submit_recording_ground_truth(self, request: GroundTruthRequest) -> None:
        logger.debug("Ground truth received but not used by driver")

    def _check_frames_ready(self, session: Session) -> bool:
        """Check if all cameras have enough frames for inference."""
        return session.all_cameras_ready()

    async def drive(self, request: DriveRequest) -> DriveResponse:
        logger.debug(
            "drive called: session=%s, time_now_us=%s",
            request.session_uuid,
            request.time_now_us,
        )
        if request.session_uuid not in self._sessions:
            raise KeyError(f"Session {request.session_uuid} not found")

        session = self._sessions[request.session_uuid]

        if not self._check_frames_ready(session):
            empty_traj = Trajectory(poses=[])
            min_required = next(
                iter(session.frame_caches.values())
            ).min_frames_required()
            logger.debug(
                "Drive request received with insufficient frames: "
                "got %s min frames across cameras, need at least %s frames "
                "(context_length=%s, subsample_factor=%s). Returning empty trajectory",
                session.min_frame_count(),
                min_required,
                self._context_length,
                self._cfg.inference.subsample_factor,
            )
            return DriveResponse(trajectory=empty_traj, debug_info=DriveResponseDebugInfo())

        pose_snapshot = session.poses[-1] if session.poses else None
        logger.debug(f"pose_snapshot: {pose_snapshot}")
        if pose_snapshot is None:
            empty_traj = Trajectory(poses=[])
            logger.debug(
                "Drive request received with no pose snapshot available "
                "(poses list length: %s). Returning empty trajectory",
                len(session.poses),
            )
            return DriveResponse(trajectory=empty_traj, debug_info=DriveResponseDebugInfo())

        future: asyncio.Future[ModelPrediction] = self._loop.create_future()
        job = DriveJob(
            session_id=request.session_uuid,
            session=session,
            command=session.current_command,
            pose=pose_snapshot,
            timestamp_us=request.time_now_us,
            result=future,
        )
        self._job_queue.put_nowait(job)

        prediction = await future

        alpasim_traj: Trajectory = self._convert_prediction_to_alpasim_trajectory(
            prediction, job.pose, job.timestamp_us
        )
        reasoning_text: str | None = prediction.reasoning_text

        debug_data = {
            "command": int(session.current_command),
            "command_name": session.current_command.name,
            "num_frames": {
                cam_id: cache.frame_count()
                for cam_id, cache in session.frame_caches.items()
            },
            "num_cameras": len(session.frame_caches),
            "num_poses": len(session.poses),
            "trajectory_points": len(alpasim_traj.poses),
            "reasoning_text": reasoning_text,
        }
        debug_info = DriveResponseDebugInfo(
            unstructured_debug_info=list(pickle.dumps(debug_data))
        )
        response = DriveResponse(trajectory=alpasim_traj, debug_info=debug_info)

        logger.debug(
            "drive returning response: session=%s, time_now_us=%s, trajectory_points=%d",
            request.session_uuid,
            request.time_now_us,
            len(alpasim_traj.poses),
        )
        return response

    def _convert_prediction_to_alpasim_trajectory(
        self,
        prediction: ModelPrediction,
        current_pose: PoseAtTime,
        time_now_us: int,
    ) -> Trajectory:
        """Convert model prediction to Alpasim trajectory format."""
        trajectory_poses = [current_pose]

        model_trajectory = prediction.trajectory_xy
        if model_trajectory is None or len(model_trajectory) == 0:
            return Trajectory(poses=trajectory_poses)

        curr_z = current_pose.pose.vec.z
        frequency_hz = self._model.output_frequency_hz
        time_delta_us = int(1_000_000 / frequency_hz)
        time_step = 1.0 / frequency_hz

        optimized_trajectory = model_trajectory
        if self._trajectory_optimizer is not None and len(model_trajectory) >= 2:
            rig_trajectory = add_heading_to_trajectory(model_trajectory)

            opt_cfg = self._cfg.trajectory_optimizer
            result = self._trajectory_optimizer.optimize(
                trajectory=rig_trajectory,
                time_step=time_step,
                vehicle_constraints=self._vehicle_constraints,
                retime_in_frenet=opt_cfg.retime_in_frenet,
                retime_alpha=opt_cfg.retime_alpha,
            )

            if result.success:
                optimized_trajectory = result.trajectory[:, :2]
                logger.debug(
                    "Trajectory optimization succeeded: iterations=%s, cost=%.4f",
                    result.iterations,
                    result.final_cost,
                )
            else:
                logger.warning("Trajectory optimization failed: %s", result.message)

        local_positions = _rig_est_offsets_to_local_positions(
            current_pose, optimized_trajectory
        )
        num_positions = local_positions.shape[0]

        if num_positions == 0:
            return Trajectory(poses=trajectory_poses)

        steps = np.arange(1, num_positions + 1, dtype=np.int64)
        timestamps_us = (time_now_us + steps * time_delta_us).tolist()

        current_yaw = _quat_to_yaw(current_pose.pose.quat)
        local_yaws = prediction.headings + current_yaw

        for local_xy, yaw, timestamp_us in zip(
            local_positions, local_yaws, timestamps_us, strict=True
        ):
            local_x, local_y = map(float, local_xy)

            trajectory_poses.append(
                PoseAtTime(
                    pose=Pose(
                        vec=Vec3(x=local_x, y=local_y, z=curr_z),
                        quat=_yaw_to_quat(float(yaw)),
                    ),
                    timestamp_us=timestamp_us,
                )
            )

        return Trajectory(poses=trajectory_poses)

    def shut_down(self, request) -> None:
        logger.info("shut_down requested")
        self._stop.set()

    async def run(self):
        """모든 endpoint의 serve 루프를 동시에 실행."""
        await asyncio.gather(
            self._endpoints.session_start.serve(self.start_session, self._stop),
            self._endpoints.session_close.serve(self.close_session, self._stop),
            self._endpoints.image.serve(self.submit_image_observation, self._stop),
            self._endpoints.egomotion.serve(self.submit_egomotion_observation, self._stop),
            self._endpoints.route.serve(self.submit_route, self._stop),
            self._endpoints.ground_truth.serve(self.submit_recording_ground_truth, self._stop),
            self._endpoints.drive.serve(self.drive, self._stop),
            self._endpoints.version.serve(self.get_version, self._stop),
            self._endpoints.shutdown.serve(self.shut_down, self._stop),
        )


async def serve(cfg: DriverConfig) -> None:
    """Start the DDS driver service."""
    loop = asyncio.get_running_loop()
    participant = get_participant()
    endpoints = DriverServerEndpoints(participant)

    service = EgoDriverService(
        cfg=cfg,
        loop=loop,
        endpoints=endpoints,
    )

    external_ip = _get_external_ip()
    logger.info(
        "Starting %s driver (DDS, external IP: %s)",
        cfg.model.model_type.value,
        external_ip,
    )

    try:
        await service.run()
    finally:
        await service.stop_worker()


def _run_dds_in_thread(cfg: DriverConfig, ready_event: threading.Event) -> None:
    """Run the DDS server in a background thread (for ManualModel GUI)."""

    async def serve_with_signal() -> None:
        loop = asyncio.get_running_loop()
        participant = get_participant()
        endpoints = DriverServerEndpoints(participant)

        service = EgoDriverService(
            cfg=cfg,
            loop=loop,
            endpoints=endpoints,
        )

        external_ip = _get_external_ip()
        logger.info(
            "Starting %s driver (DDS, external IP: %s)",
            cfg.model.model_type.value,
            external_ip,
        )

        ready_event.set()

        try:
            await service.run()
        finally:
            await service.stop_worker()

    asyncio.run(serve_with_signal())


@hydra.main(
    version_base=None,
    config_path="../../configs",
    config_name="driver",
)
def main(hydra_cfg: DriverConfig) -> None:
    """Main entry point for the driver service."""
    schema = OmegaConf.structured(DriverConfig)
    cfg = cast(DriverConfig, OmegaConf.merge(schema, hydra_cfg))

    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s.%(msecs)03d %(levelname)s:\t%(message)s",
        datefmt="%H:%M:%S",
    )

    if cfg.output_dir:
        os.makedirs(cfg.output_dir, exist_ok=True)
        config_filename = f"{cfg.model.model_type.value}-driver.yaml"
        OmegaConf.save(cfg, os.path.join(cfg.output_dir, config_filename), resolve=True)

    if cfg.model.model_type == ModelType.MANUAL:
        logger.info("Starting DDS server in background thread (GUI mode)")

        ready_event = threading.Event()
        dds_thread = threading.Thread(
            target=_run_dds_in_thread,
            args=(cfg, ready_event),
            name="dds-server",
            daemon=True,
        )
        dds_thread.start()

        ready_event.wait(timeout=30.0)

        if ManualModel._gui_instance is not None:
            ManualModel._gui_instance.run_main_loop()
        else:
            logger.warning("ManualModel GUI not initialized, waiting for DDS thread")
            dds_thread.join()

        return

    asyncio.run(serve(cfg))


if __name__ == "__main__":
    main()
