"""Physics service implementation (DDS)."""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from alpasim_dds.endpoints.physics import PhysicsEndpoints
from alpasim_dds.types.common import AvailableScenesRequest
from alpasim_dds.types.physics import (
    EgoData,
    OtherObject,
    PhysicsGroundIntersectionRequest,
    PosePair,
)
from alpasim_grpc.v0.logging_pb2 import LogEntry
from alpasim_runtime.config import PhysicsUpdateMode, ScenarioConfig
from alpasim_runtime.services.service_base import DDSServiceBase, WILDCARD_SCENE_ID
from alpasim_utils.dds_to_proto import physics_request_to_proto, physics_response_to_proto
from alpasim_utils.qvec import QVec
from alpasim_utils.scenario import AABB

logger = logging.getLogger(__name__)


class PhysicsService(DDSServiceBase):
    """Physics service — DDS 기반. ground intersection 계산을 담당."""

    endpoints_class = PhysicsEndpoints

    async def ground_intersection(
        self,
        scene_id: str,
        delta_start_us: int,
        delta_end_us: int,
        pose_now: QVec,
        pose_future: QVec,
        traffic_poses: Dict[str, QVec],
        ego_aabb: AABB,
        skip: bool = False,
    ) -> Tuple[QVec, Dict[str, QVec]]:
        """Calculate ground intersection for ego and traffic vehicles."""

        if self.skip or skip:
            return pose_future, traffic_poses

        assert traffic_poses is not None or (
            pose_now is not None and pose_future is not None
        ), "Either traffic_poses or pose_now and pose_future must be provided."

        traffic_poses = traffic_poses or {}

        request = self._prepare_request(
            scene_id,
            delta_start_us,
            delta_end_us,
            pose_now,
            pose_future,
            list(traffic_poses.values()),
            ego_aabb=ego_aabb,
        )

        await self.session_info.broadcaster.broadcast(
            LogEntry(physics_request=physics_request_to_proto(request))
        )

        response = await self.endpoints.ground_intersection.request(request)

        await self.session_info.broadcaster.broadcast(
            LogEntry(physics_return=physics_response_to_proto(response))
        )

        ego_response = QVec.from_dds_pose(response.ego_pose.pose)
        traffic_responses = {
            k: QVec.from_dds_pose(v.pose)
            for k, v in zip(traffic_poses.keys(), response.other_poses)
        }

        return ego_response, traffic_responses

    def _prepare_request(
        self,
        scene_id: str,
        delta_start_us: int,
        delta_end_us: int,
        pose_now: QVec,
        pose_future: QVec,
        other_poses: List[QVec],
        ego_aabb: AABB,
    ) -> PhysicsGroundIntersectionRequest:
        return PhysicsGroundIntersectionRequest(
            scene_id=scene_id,
            now_us=delta_start_us,
            future_us=delta_end_us,
            ego_data=EgoData(
                aabb=ego_aabb.to_dds(),
                pose_pair=PosePair(
                    now_pose=pose_now.as_dds_pose(),
                    future_pose=pose_future.as_dds_pose(),
                ),
            ),
            other_objects=[
                OtherObject(
                    # TODO[RDL] extract AABB from NRE reconstruction
                    aabb=ego_aabb.to_dds(),
                    pose_pair=PosePair(
                        now_pose=p.as_dds_pose(),
                        future_pose=p.as_dds_pose(),
                    ),
                )
                for p in other_poses
            ],
        )

    async def get_available_scenes(self) -> List[str]:
        if self.skip:
            return [WILDCARD_SCENE_ID]

        if self._available_scenes is None:
            response = await self.endpoints.available_scenes.request(
                AvailableScenesRequest()
            )
            self._available_scenes = list(response.scene_ids)

        return self._available_scenes

    async def find_scenario_incompatibilities(
        self, scenario: ScenarioConfig
    ) -> List[str]:
        incompatibilities = await super().find_scenario_incompatibilities(scenario)

        if not self.skip and scenario.physics_update_mode == PhysicsUpdateMode.NONE:
            incompatibilities.append("Physics is disabled for this scenario.")

        return incompatibilities
