"""Driver service implementation (DDS)."""

from __future__ import annotations

import logging
from typing import Any, List, Optional

import numpy as np
from alpasim_dds.endpoints.driver import DriverEndpoints
from alpasim_dds.types.camera import AvailableCamera
from alpasim_dds.types.common import DynamicState
from alpasim_dds.types.egodriver import (
    CameraImage,
    DebugInfo,
    DriveRequest,
    DriveResponse,
    DriveSessionCloseRequest,
    DriveSessionRequest,
    GroundTruth,
    GroundTruthRequest,
    RolloutCameraImage,
    RolloutEgoTrajectory,
    RolloutSpec,
    RouteRequest,
    VehicleDefinition,
)
from alpasim_grpc.v0.logging_pb2 import LogEntry
from alpasim_runtime.broadcaster import MessageBroadcaster
from alpasim_runtime.services.service_base import (
    DDSServiceBase,
    WILDCARD_SCENE_ID,
    SessionInfo,
)
from alpasim_utils.dds_to_proto import (
    drive_request_to_proto,
    drive_response_to_proto,
    drive_session_request_to_proto,
    ground_truth_request_to_proto,
    rollout_camera_image_to_proto,
    rollout_ego_trajectory_to_proto,
    route_request_to_proto,
)
from alpasim_utils.polyline import Polyline
from alpasim_utils.qvec import QVec
from alpasim_utils.trajectory import Trajectory
from alpasim_utils.types import ImageWithMetadata

logger = logging.getLogger(__name__)


class DriverService(DDSServiceBase):
    """Driver service — DDS 기반. 자율주행 정책과의 통신을 담당."""

    endpoints_class = DriverEndpoints

    def session(  # type: ignore[override]
        self,
        uuid: str,
        broadcaster: MessageBroadcaster,
        random_seed: int,
        sensorsim_cameras: list[AvailableCamera],
        scene_id: Optional[str] = None,
    ) -> "DriverService":
        """Create a driver session with typed parameters."""
        return super().session(
            uuid=uuid,
            broadcaster=broadcaster,
            random_seed=random_seed,
            sensorsim_cameras=sensorsim_cameras,
            scene_id=scene_id,
        )

    async def _initialize_session(
        self, session_info: SessionInfo, **kwargs: Any
    ) -> None:
        await super()._initialize_session(session_info=session_info)

        random_seed: int = session_info.additional_args["random_seed"]
        scene_id: str | None = session_info.additional_args.get("scene_id")
        sensorsim_cameras: list[AvailableCamera] = session_info.additional_args[
            "sensorsim_cameras"
        ]

        request = DriveSessionRequest(
            session_uuid=self.session_info.uuid,
            random_seed=random_seed,
            debug_info=DebugInfo(scene_id=scene_id or ""),
            rollout_spec=RolloutSpec(
                vehicle=VehicleDefinition(
                    available_cameras=sensorsim_cameras,
                ),
            ),
        )

        await session_info.broadcaster.broadcast(
            LogEntry(driver_session_request=drive_session_request_to_proto(request))
        )

        if self.skip:
            return

        await self.endpoints.session_start.request(request)

    async def _cleanup_session(self, session_info: SessionInfo, **kwargs: Any) -> None:
        if self.skip:
            return

        self.endpoints.session_close.send(
            DriveSessionCloseRequest(session_uuid=self.session_info.uuid)
        )

    async def get_available_scenes(self) -> List[str]:
        return [WILDCARD_SCENE_ID]

    async def submit_image(self, image: ImageWithMetadata) -> None:
        """Submit an image observation for the current session."""
        request = RolloutCameraImage(
            session_uuid=self.session_info.uuid,
            camera_image=CameraImage(
                frame_start_us=image.start_timestamp_us,
                frame_end_us=image.end_timestamp_us,
                image_bytes=list(image.image_bytes),
                logical_id=image.camera_logical_id,
            ),
        )

        await self.session_info.broadcaster.broadcast(
            LogEntry(driver_camera_image=rollout_camera_image_to_proto(request))
        )

        if self.skip:
            return

        self.endpoints.image.send(request)

    async def submit_trajectory(
        self,
        trajectory: Trajectory,
        dynamic_state: DynamicState,
    ) -> None:
        """Submit an egomotion trajectory for the current session."""
        request = RolloutEgoTrajectory(
            session_uuid=self.session_info.uuid,
            trajectory=trajectory.to_dds(),
            dynamic_state=dynamic_state,
        )

        await self.session_info.broadcaster.broadcast(
            LogEntry(driver_ego_trajectory=rollout_ego_trajectory_to_proto(request))
        )

        if self.skip:
            return

        self.endpoints.egomotion.send(request)

    async def submit_route(
        self, timestamp_us: int, route_polyline_in_rig: Polyline
    ) -> None:
        """Submit a route for the current session."""
        request = RouteRequest(
            session_uuid=self.session_info.uuid,
            route=route_polyline_in_rig.to_dds_route(timestamp_us),
        )

        await self.session_info.broadcaster.broadcast(
            LogEntry(route_request=route_request_to_proto(request))
        )

        if self.skip:
            return

        self.endpoints.route.send(request)

    async def submit_recording_ground_truth(
        self, timestamp_us: int, trajectory: Trajectory
    ) -> None:
        """Submit ground truth from recording for the current session."""
        request = GroundTruthRequest(
            session_uuid=self.session_info.uuid,
            ground_truth=GroundTruth(
                timestamp_us=timestamp_us,
                trajectory=trajectory.to_dds(),
            ),
        )

        await self.session_info.broadcaster.broadcast(
            LogEntry(ground_truth_request=ground_truth_request_to_proto(request))
        )

        if self.skip:
            return

        self.endpoints.ground_truth.send(request)

    async def drive(
        self, time_now_us: int, time_query_us: int, renderer_data: Optional[bytes]
    ) -> Trajectory:
        """Request a drive decision for the current session."""

        request = DriveRequest(
            session_uuid=self.session_info.uuid,
            time_now_us=time_now_us,
            time_query_us=time_query_us,
            renderer_data=list(renderer_data) if renderer_data else [],
        )

        await self.session_info.broadcaster.broadcast(
            LogEntry(driver_request=drive_request_to_proto(request))
        )

        if self.skip:
            num_points = 50
            interval_us = 100_000  # 100ms
            timestamps = np.array(
                [time_now_us + i * interval_us for i in range(num_points)],
                dtype=np.uint64,
            )
            poses = QVec.stack(
                [
                    QVec(
                        vec3=np.array([i * 0.5, 0.0, 0.0]),
                        quat=np.array([0.0, 0.0, 0.0, 1.0]),
                    )
                    for i in range(num_points)
                ]
            )
            skip_trajectory = Trajectory(timestamps_us=timestamps, poses=poses)
            return skip_trajectory

        response = await self.endpoints.drive.request(request)

        await self.session_info.broadcaster.broadcast(
            LogEntry(driver_return=drive_response_to_proto(response))
        )

        return Trajectory.from_dds(response.trajectory)
