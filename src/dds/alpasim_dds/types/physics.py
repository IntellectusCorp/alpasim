from dataclasses import dataclass
from typing import Optional

from cyclonedds.idl import IdlEnum, IdlStruct
from cyclonedds.idl.types import uint64, sequence

from alpasim_dds.types.common import AABB, Pose


# ---------------------------------------------------------------------------
# ground_intersection (bidirectional)
# ---------------------------------------------------------------------------


@dataclass
class PosePair(IdlStruct):
    now_pose: Pose = None
    future_pose: Pose = None


@dataclass
class EgoData(IdlStruct):
    aabb: AABB = None
    pose_pair: PosePair = None


@dataclass
class OtherObject(IdlStruct):
    aabb: AABB = None
    pose_pair: PosePair = None


@dataclass
class PhysicsGroundIntersectionRequest(IdlStruct):
    correlation_id: str = ""
    scene_id: str = ""
    now_us: uint64 = 0
    future_us: uint64 = 0
    ego_data: EgoData = None            # optional in proto
    other_objects: sequence[OtherObject] = None


class GroundIntersectionStatus(IdlEnum):
    SUCCESSFUL_UPDATE = 1
    INSUFFICIENT_POINTS_FITPLANE = 2
    HIGH_TRANSLATION = 3
    HIGH_ROTATION = 4


@dataclass
class ReturnPose(IdlStruct):
    pose: Pose = None
    status: GroundIntersectionStatus = GroundIntersectionStatus.SUCCESSFUL_UPDATE


@dataclass
class PhysicsGroundIntersectionReturn(IdlStruct):
    correlation_id: str = ""
    ego_pose: ReturnPose = None         # optional in proto
    other_poses: sequence[ReturnPose] = None
