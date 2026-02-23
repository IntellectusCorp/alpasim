"""Controller service implementation (DDS)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List

import numpy as np
from alpasim_dds.endpoints.controller import ControllerEndpoints
from alpasim_dds.types.common import DynamicState, StateAtTime, Vec3
from alpasim_dds.types.controller import (
    RunControllerAndVehicleModelRequest,
    VDCSessionCloseRequest,
    VDCSessionRequest,
)
from alpasim_grpc.v0.logging_pb2 import LogEntry
from alpasim_runtime.services.service_base import DDSServiceBase, SessionInfo, WILDCARD_SCENE_ID
from alpasim_utils.dds_to_proto import (
    run_controller_request_to_proto,
    run_controller_response_to_proto,
)
from alpasim_utils.qvec import QVec
from alpasim_utils.trajectory import Trajectory

logger = logging.getLogger(__name__)


@dataclass
class PropagatedPoses:
    """
    A pair of poses and dynamic states, one representing the true predicted output from
    the vehicle model, and the other representing the estimate used by the controller in the loop.
    """

    pose_local_to_rig: QVec
    pose_local_to_rig_estimate: QVec
    dynamic_state: DynamicState
    dynamic_state_estimated: DynamicState


class ControllerService(DDSServiceBase):
    """Controller service — DDS 기반."""

    endpoints_class = ControllerEndpoints

    @staticmethod
    def create_run_controller_and_vehicle_request(
        session_uuid: str,
        now_us: int,
        pose_local_to_rig: QVec,
        rig_linear_velocity_in_rig: np.ndarray,
        rig_angular_velocity_in_rig: np.ndarray,
        rig_reference_trajectory_in_rig: Trajectory,
        future_us: int,
        force_gt: bool,
    ) -> RunControllerAndVehicleModelRequest:
        """Helper method to generate a RunControllerAndVehicleModelRequest."""
        return RunControllerAndVehicleModelRequest(
            session_uuid=session_uuid,
            state=StateAtTime(
                timestamp_us=now_us,
                pose=pose_local_to_rig.as_dds_pose(),
                state=DynamicState(
                    linear_velocity=Vec3(
                        x=float(rig_linear_velocity_in_rig[0]),
                        y=float(rig_linear_velocity_in_rig[1]),
                        z=float(rig_linear_velocity_in_rig[2]),
                    ),
                    angular_velocity=Vec3(
                        x=float(rig_angular_velocity_in_rig[0]),
                        y=float(rig_angular_velocity_in_rig[1]),
                        z=float(rig_angular_velocity_in_rig[2]),
                    ),
                ),
            ),
            planned_trajectory_in_rig=rig_reference_trajectory_in_rig.to_dds(),
            future_time_us=future_us,
            coerce_dynamic_state=force_gt,
        )

    async def _initialize_session(
        self, session_info: SessionInfo, **kwargs: Any
    ) -> None:
        if self.skip:
            logger.info("Skip mode: session cannot be initialized")
            return

        await self.endpoints.session_start.request(
            VDCSessionRequest(session_uuid=session_info.uuid)
        )

    async def _cleanup_session(self, session_info: SessionInfo, **kwargs: Any) -> None:
        if self.skip:
            logger.info("Skip mode: session cannot be cleaned up")
            return

        self.endpoints.session_close.send(
            VDCSessionCloseRequest(session_uuid=session_info.uuid)
        )

    async def run_controller_and_vehicle(
        self,
        now_us: int,
        pose_local_to_rig: QVec,
        rig_linear_velocity_in_rig: np.ndarray,
        rig_angular_velocity_in_rig: np.ndarray,
        rig_reference_trajectory_in_rig: Trajectory,
        future_us: int,
        force_gt: bool,
        fallback_pose_local_to_rig_future: QVec,
    ) -> PropagatedPoses:
        """Run controller and vehicle model to get future pose."""

        if self.skip:
            logger.debug("Skip mode: controller returning fallback pose")
            return PropagatedPoses(
                pose_local_to_rig=fallback_pose_local_to_rig_future,
                pose_local_to_rig_estimate=fallback_pose_local_to_rig_future,
                dynamic_state=DynamicState(),
                dynamic_state_estimated=DynamicState(),
            )

        request = self.create_run_controller_and_vehicle_request(
            session_uuid=self.session_info.uuid,
            now_us=now_us,
            pose_local_to_rig=pose_local_to_rig,
            rig_linear_velocity_in_rig=rig_linear_velocity_in_rig,
            rig_angular_velocity_in_rig=rig_angular_velocity_in_rig,
            rig_reference_trajectory_in_rig=rig_reference_trajectory_in_rig,
            future_us=future_us,
            force_gt=force_gt,
        )

        await self.session_info.broadcaster.broadcast(
            LogEntry(controller_request=run_controller_request_to_proto(request))
        )

        response = await self.endpoints.run.request(request)

        await self.session_info.broadcaster.broadcast(
            LogEntry(controller_return=run_controller_response_to_proto(response))
        )

        return PropagatedPoses(
            pose_local_to_rig=QVec.from_dds_pose(response.pose_local_to_rig.pose),
            pose_local_to_rig_estimate=QVec.from_dds_pose(
                response.pose_local_to_rig_estimated.pose
            ),
            dynamic_state=response.dynamic_state,
            dynamic_state_estimated=response.dynamic_state_estimated,
        )

    async def get_available_scenes(self) -> List[str]:
        return [WILDCARD_SCENE_ID]
