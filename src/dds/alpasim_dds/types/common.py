from dataclasses import dataclass, field

from cyclonedds.idl import IdlStruct
from cyclonedds.idl.types import float32, uint32, uint64, sequence


# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------


@dataclass
class Quat(IdlStruct):
    w: float32 = 0.0
    x: float32 = 0.0
    y: float32 = 0.0
    z: float32 = 0.0


@dataclass
class Vec3(IdlStruct):
    x: float32 = 0.0
    y: float32 = 0.0
    z: float32 = 0.0


@dataclass
class Pose(IdlStruct):
    vec: Vec3 = field(default_factory=Vec3)
    quat: Quat = field(default_factory=Quat)


@dataclass
class DynamicState(IdlStruct):
    angular_velocity: Vec3 = field(default_factory=Vec3)
    linear_velocity: Vec3 = field(default_factory=Vec3)
    linear_acceleration: Vec3 = field(default_factory=Vec3)
    angular_acceleration: Vec3 = field(default_factory=Vec3)


@dataclass
class AABB(IdlStruct):
    size_x: float32 = 0.0
    size_y: float32 = 0.0
    size_z: float32 = 0.0


@dataclass
class PoseAtTime(IdlStruct):
    pose: Pose = field(default_factory=Pose)
    timestamp_us: uint64 = 0


@dataclass
class StateAtTime(IdlStruct):
    timestamp_us: uint64 = 0
    pose: Pose = field(default_factory=Pose)
    state: DynamicState = field(default_factory=DynamicState)


@dataclass
class Trajectory(IdlStruct):
    poses: sequence[PoseAtTime] = ()


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


@dataclass
class APIVersion(IdlStruct):
    major: uint32 = 0
    minor: uint32 = 0
    patch: uint32 = 0


# Bidirectional: get_version
@dataclass
class VersionRequest(IdlStruct):
    correlation_id: str = ""


@dataclass
class VersionResponse(IdlStruct):
    correlation_id: str = ""
    version_id: str = ""
    git_hash: str = ""
    api_version: APIVersion = field(default_factory=APIVersion)


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


# Bidirectional response for start_session (empty in proto, just correlation_id for DDS)
@dataclass
class SessionRequestStatus(IdlStruct):
    correlation_id: str = ""


# ---------------------------------------------------------------------------
# Available scenes (Physics)
# ---------------------------------------------------------------------------


@dataclass
class AvailableScenesRequest(IdlStruct):
    correlation_id: str = ""


@dataclass
class AvailableScenesResponse(IdlStruct):
    correlation_id: str = ""
    scene_ids: sequence[str] = ()


# ---------------------------------------------------------------------------
# Shut down (fire-and-forget, common to all services)
# ---------------------------------------------------------------------------


@dataclass
class ShutDownRequest(IdlStruct):
    timestamp_us: uint64 = 0
