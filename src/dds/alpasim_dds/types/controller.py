from dataclasses import dataclass

from cyclonedds.idl import IdlStruct
from cyclonedds.idl.types import int64, uint64, sequence

from alpasim_dds.types.common import DynamicState, PoseAtTime, StateAtTime, Trajectory


# ---------------------------------------------------------------------------
# start_session (bidirectional)
# Response: common.SessionRequestStatus
# ---------------------------------------------------------------------------


@dataclass
class VehicleAndControllerParams(IdlStruct):
    rig_file: str = ""
    amend_files: sequence[str] = None


@dataclass
class VDCSessionRequest(IdlStruct):
    correlation_id: str = ""
    session_uuid: str = ""
    vehicle_and_controller_params: VehicleAndControllerParams = None


# ---------------------------------------------------------------------------
# close_session (fire-and-forget)
# ---------------------------------------------------------------------------


@dataclass
class VDCSessionCloseRequest(IdlStruct):
    session_uuid: str = ""


# ---------------------------------------------------------------------------
# run_controller_and_vehicle (bidirectional)
# ---------------------------------------------------------------------------


@dataclass
class RunControllerAndVehicleModelRequest(IdlStruct):
    correlation_id: str = ""
    session_uuid: str = ""
    state: StateAtTime = None
    planned_trajectory_in_rig: Trajectory = None
    future_time_us: int64 = 0
    coerce_dynamic_state: bool = False


@dataclass
class RunControllerAndVehicleModelResponse(IdlStruct):
    correlation_id: str = ""
    pose_local_to_rig: PoseAtTime = None
    pose_local_to_rig_estimated: PoseAtTime = None
    dynamic_state: DynamicState = None
    dynamic_state_estimated: DynamicState = None
