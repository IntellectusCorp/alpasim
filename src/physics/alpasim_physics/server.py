# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 NVIDIA Corporation

import argparse
import asyncio
import functools
import logging

from alpasim_dds.endpoints.physics_server import PhysicsServerEndpoints
from alpasim_dds.participant import get_participant
from alpasim_dds.types.common import APIVersion, AvailableScenesResponse, VersionResponse
from alpasim_dds.types.physics import PhysicsGroundIntersectionRequest, PhysicsGroundIntersectionReturn
from alpasim_grpc import API_VERSION_MESSAGE
from alpasim_physics import VERSION_MESSAGE
from alpasim_physics.backend import PhysicsBackend
from alpasim_physics.utils import aabb_dds_to_ndarray, pose_dds_to_ndarray, pose_status_to_dds
from alpasim_utils.artifact import Artifact

logger = logging.getLogger(__name__)


class PhysicsSimService:
    def __init__(
        self,
        endpoints: PhysicsServerEndpoints,
        artifact_glob: str,
        cache_size: int = 2,
        use_ground_mesh: bool = False,
        visualize: bool = False,
    ) -> None:
        self.endpoints = endpoints
        self.artifacts = Artifact.discover_from_glob(
            artifact_glob, use_ground_mesh=use_ground_mesh
        )
        self.visualize = visualize
        self._stop = asyncio.Event()

        logger.info(f"Available scenes: {list(self.artifacts.keys())}.")

        @functools.lru_cache(maxsize=cache_size)
        def get_backend(scene_id: str) -> PhysicsBackend:
            if scene_id not in self.artifacts:
                raise KeyError(f"Scene {scene_id=} not available.")
            artifact = self.artifacts[scene_id]
            logger.info(f"Cache miss, loading {artifact.scene_id=}")
            mesh_ply = artifact.mesh_ply
            logger.info("Mesh PLY loaded, creating PhysicsBackend...")
            artifact.clear_cache()
            backend = PhysicsBackend(mesh_ply, visualize=self.visualize)
            logger.info("PhysicsBackend created successfully")
            return backend

        self.get_backend = get_backend

    def ground_intersection(
        self, request: PhysicsGroundIntersectionRequest
    ) -> PhysicsGroundIntersectionReturn:
        logger.info(f"ground_intersection request: scene_id={request.scene_id}, ego_data={'present' if request.ego_data is not None else 'None'}, other_objects={len(request.other_objects) if request.other_objects else 0}")
        backend = self.get_backend(request.scene_id)

        other_updates = []
        for other in request.other_objects:
            other_updates.append(
                backend.update_pose(
                    pose_dds_to_ndarray(other.pose_pair.future_pose),
                    aabb_dds_to_ndarray(other.aabb),
                    request.future_us,
                )
            )

        if request.ego_data is not None:
            predicted_pose = pose_dds_to_ndarray(
                request.ego_data.pose_pair.future_pose
            )
            ego_aabb = aabb_dds_to_ndarray(request.ego_data.aabb)

            updated_ego_pose, updated_ego_status = backend.update_pose(
                predicted_pose, ego_aabb, request.future_us
            )

            result = PhysicsGroundIntersectionReturn(
                ego_pose=pose_status_to_dds(updated_ego_pose, updated_ego_status),
                other_poses=[
                    pose_status_to_dds(pose, status) for pose, status in other_updates
                ],
            )
            logger.info(f"ground_intersection response: ego_pose={'present' if result.ego_pose else 'None'}, other_poses={len(result.other_poses) if result.other_poses else 0}")
            return result
        else:
            result = PhysicsGroundIntersectionReturn(
                other_poses=[
                    pose_status_to_dds(pose, status) for pose, status in other_updates
                ],
            )
            logger.info(f"ground_intersection response: ego_pose=None, other_poses={len(result.other_poses) if result.other_poses else 0}")
            return result

    def get_available_scenes(self, request) -> AvailableScenesResponse:
        logger.info("get_available_scenes")
        return AvailableScenesResponse(
            scene_ids=list(self.artifacts.keys()),
        )

    def get_version(self, request) -> VersionResponse:
        logger.info("get_version")
        return VersionResponse(
            version_id=VERSION_MESSAGE.version_id,
            git_hash=VERSION_MESSAGE.git_hash,
            api_version=APIVersion(
                major=API_VERSION_MESSAGE.major,
                minor=API_VERSION_MESSAGE.minor,
                patch=API_VERSION_MESSAGE.patch,
            ),
        )

    def shut_down(self, request) -> None:
        logger.info("shut_down")
        self._stop.set()

    async def run(self):
        """모든 endpoint의 serve 루프를 동시에 실행."""
        await asyncio.gather(
            self.endpoints.ground_intersection.serve(
                self.ground_intersection, self._stop
            ),
            self.endpoints.available_scenes.serve(
                self.get_available_scenes, self._stop
            ),
            self.endpoints.version.serve(self.get_version, self._stop),
            self.endpoints.shutdown.serve(self.shut_down, self._stop),
        )


def parse_args(
    arg_list: list[str] | None = None,
) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-glob",
        type=str,
        help="Glob expression to find artifacts. Must end in .usdz to find relevant files.",
        required=True,
    )
    parser.add_argument("--use-ground-mesh", type=bool, default=False)
    parser.add_argument("--visualize", type=bool, default=False)
    parser.add_argument(
        "--cache-size",
        type=int,
        default=16,
        help="Number of scene backends to keep in LRU cache.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    parser.add_argument(
        "--domain-id",
        type=int,
        default=0,
        help="DDS domain ID",
    )
    args, overrides = parser.parse_known_args(arg_list)
    return args, overrides


def main(arg_list: list[str] | None = None) -> None:
    args, _ = parse_args(arg_list)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s.%(msecs)03d %(levelname)s:\t%(message)s",
        datefmt="%H:%M:%S",
    )

    participant = get_participant(args.domain_id)
    endpoints = PhysicsServerEndpoints(participant)

    service = PhysicsSimService(
        endpoints,
        args.artifact_glob,
        cache_size=args.cache_size,
        use_ground_mesh=args.use_ground_mesh,
        visualize=args.visualize,
    )

    logger.info("Physics DDS service starting...")
    asyncio.run(service.run())


if __name__ == "__main__":
    main()
