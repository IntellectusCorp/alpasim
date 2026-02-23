from cyclonedds.domain import DomainParticipant

from alpasim_dds.qos import SESSION_QOS
from alpasim_dds.transport import DDSServerTransport
from alpasim_dds.types.common import SessionRequestStatus, ShutDownRequest, VersionRequest, VersionResponse
from alpasim_dds.types.controller import (
    RunControllerAndVehicleModelRequest,
    RunControllerAndVehicleModelResponse,
    VDCSessionCloseRequest,
    VDCSessionRequest,
)


class ControllerServerEndpoints:
    """Controller 서버의 모든 DDSServerTransport."""

    def __init__(self, participant: DomainParticipant):
        self.session_start = DDSServerTransport(
            participant, "controller/session_start",
            VDCSessionRequest, SessionRequestStatus, qos=SESSION_QOS,
        )
        self.session_close = DDSServerTransport(
            participant, "controller/session_close",
            VDCSessionCloseRequest,
        )
        self.run = DDSServerTransport(
            participant, "controller/run",
            RunControllerAndVehicleModelRequest, RunControllerAndVehicleModelResponse,
        )
        self.version = DDSServerTransport(
            participant, "controller/version",
            VersionRequest, VersionResponse,
        )
        self.shutdown = DDSServerTransport(
            participant, "controller/shutdown",
            ShutDownRequest,
        )
