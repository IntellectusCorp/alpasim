from dataclasses import dataclass, field
from typing import Optional

from cyclonedds.idl import IdlEnum, IdlStruct
from cyclonedds.idl.types import uint64, sequence

from alpasim_dds.types.common import AABB, Pose


# ---------------------------------------------------------------------------
# ground_intersection (bidirectional)
# ---------------------------------------------------------------------------


@dataclass
class PosePair(IdlStruct):
    now_pose: Pose = field(default_factory=Pose)
    future_pose: Pose = field(default_factory=Pose)


@dataclass
class EgoData(IdlStruct):
    aabb: AABB = field(default_factory=AABB)
    pose_pair: PosePair = field(default_factory=PosePair)


@dataclass
class OtherObject(IdlStruct):
    aabb: AABB = field(default_factory=AABB)
    pose_pair: PosePair = field(default_factory=PosePair)


@dataclass
class PhysicsGroundIntersectionRequest(IdlStruct):
    correlation_id: str = ""
    scene_id: str = ""
    now_us: uint64 = 0
    future_us: uint64 = 0
    ego_data: EgoData = field(default_factory=EgoData)
    other_objects: sequence[OtherObject] = ()


class GroundIntersectionStatus(IdlEnum):
    SUCCESSFUL_UPDATE = 1
    INSUFFICIENT_POINTS_FITPLANE = 2
    HIGH_TRANSLATION = 3
    HIGH_ROTATION = 4


@dataclass
class ReturnPose(IdlStruct):
    pose: Pose = field(default_factory=Pose)
    status: GroundIntersectionStatus = GroundIntersectionStatus.SUCCESSFUL_UPDATE


@dataclass
class PhysicsGroundIntersectionReturn(IdlStruct):
    correlation_id: str = ""
    ego_pose: ReturnPose = field(default_factory=ReturnPose)
    other_poses: sequence[ReturnPose] = ()
