from dataclasses import dataclass, field

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
    amend_files: sequence[str] = ()


@dataclass
class VDCSessionRequest(IdlStruct):
    correlation_id: str = ""
    session_uuid: str = ""
    vehicle_and_controller_params: VehicleAndControllerParams = field(default_factory=VehicleAndControllerParams)


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
    state: StateAtTime = field(default_factory=StateAtTime)
    planned_trajectory_in_rig: Trajectory = field(default_factory=Trajectory)
    future_time_us: int64 = 0
    coerce_dynamic_state: bool = False


@dataclass
class RunControllerAndVehicleModelResponse(IdlStruct):
    correlation_id: str = ""
    pose_local_to_rig: PoseAtTime = field(default_factory=PoseAtTime)
    pose_local_to_rig_estimated: PoseAtTime = field(default_factory=PoseAtTime)
    dynamic_state: DynamicState = field(default_factory=DynamicState)
    dynamic_state_estimated: DynamicState = field(default_factory=DynamicState)
