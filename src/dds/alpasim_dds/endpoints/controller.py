from cyclonedds.domain import DomainParticipant

from alpasim_dds.qos import SESSION_QOS
from alpasim_dds.transport import DDSTransport
from alpasim_dds.types.common import SessionRequestStatus, ShutDownRequest, VersionRequest, VersionResponse
from alpasim_dds.types.controller import (
    RunControllerAndVehicleModelRequest,
    RunControllerAndVehicleModelResponse,
    VDCSessionCloseRequest,
    VDCSessionRequest,
)


class ControllerEndpoints:
    """Controller 서비스의 모든 DDSTransport를 static으로 생성."""

    def __init__(self, participant: DomainParticipant):
        self.session_start = DDSTransport(
            participant, "controller/session_start",
            VDCSessionRequest, SessionRequestStatus, qos=SESSION_QOS,
        )
        self.session_close = DDSTransport(
            participant, "controller/session_close",
            VDCSessionCloseRequest,
        )
        self.run = DDSTransport(
            participant, "controller/run",
            RunControllerAndVehicleModelRequest, RunControllerAndVehicleModelResponse,
        )
        self.version = DDSTransport(
            participant, "controller/version",
            VersionRequest, VersionResponse,
        )
        self.shutdown = DDSTransport(
            participant, "controller/shutdown",
            ShutDownRequest,
        )
