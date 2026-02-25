from dataclasses import dataclass
from typing import Optional

from cyclonedds.idl import IdlStruct
from cyclonedds.idl.types import uint8, uint64, sequence

from alpasim_dds.types.common import DynamicState, Trajectory, Vec3
from alpasim_dds.types.camera import AvailableCamera


# ---------------------------------------------------------------------------
# start_session (bidirectional)
# Response: common.SessionRequestStatus
# ---------------------------------------------------------------------------


@dataclass
class VehicleDefinition(IdlStruct):
    available_cameras: sequence[AvailableCamera] = ()


@dataclass
class RolloutSpec(IdlStruct):
    vehicle: VehicleDefinition = None


@dataclass
class DebugInfo(IdlStruct):
    scene_id: str = ""


@dataclass
class DriveSessionRequest(IdlStruct):
    correlation_id: str = ""
    session_uuid: str = ""
    random_seed: uint64 = 0
    debug_info: DebugInfo = None        # optional in proto
    rollout_spec: RolloutSpec = None


# ---------------------------------------------------------------------------
# close_session (fire-and-forget)
# ---------------------------------------------------------------------------


@dataclass
class DriveSessionCloseRequest(IdlStruct):
    session_uuid: str = ""


# ---------------------------------------------------------------------------
# submit_image_observation (fire-and-forget)
# ---------------------------------------------------------------------------


@dataclass
class CameraImage(IdlStruct):
    frame_start_us: uint64 = 0
    frame_end_us: uint64 = 0
    image_bytes: sequence[uint8] = ()
    logical_id: str = ""


@dataclass
class RolloutCameraImage(IdlStruct):
    session_uuid: str = ""
    camera_image: CameraImage = None


# ---------------------------------------------------------------------------
# submit_egomotion_observation (fire-and-forget)
# ---------------------------------------------------------------------------


@dataclass
class RolloutEgoTrajectory(IdlStruct):
    session_uuid: str = ""
    trajectory: Trajectory = None
    dynamic_state: DynamicState = None


# ---------------------------------------------------------------------------
# submit_route (fire-and-forget)
# ---------------------------------------------------------------------------


@dataclass
class Route(IdlStruct):
    timestamp_us: uint64 = 0
    waypoints: sequence[Vec3] = ()


@dataclass
class RouteRequest(IdlStruct):
    session_uuid: str = ""
    route: Route = None


# ---------------------------------------------------------------------------
# submit_recording_ground_truth (fire-and-forget)
# ---------------------------------------------------------------------------


@dataclass
class GroundTruth(IdlStruct):
    timestamp_us: uint64 = 0
    trajectory: Trajectory = None


@dataclass
class GroundTruthRequest(IdlStruct):
    session_uuid: str = ""
    ground_truth: GroundTruth = None


# ---------------------------------------------------------------------------
# drive (bidirectional)
# ---------------------------------------------------------------------------


@dataclass
class DriveRequest(IdlStruct):
    correlation_id: str = ""
    session_uuid: str = ""
    time_now_us: uint64 = 0
    time_query_us: uint64 = 0
    renderer_data: sequence[uint8] = ()


@dataclass
class DriveResponseDebugInfo(IdlStruct):
    unstructured_debug_info: sequence[uint8] = ()
    sampled_trajectories: sequence[Trajectory] = ()


@dataclass
class DriveResponse(IdlStruct):
    correlation_id: str = ""
    trajectory: Trajectory = None
    debug_info: DriveResponseDebugInfo = None
