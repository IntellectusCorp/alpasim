from cyclonedds.domain import DomainParticipant

from alpasim_dds.qos import SESSION_QOS
from alpasim_dds.transport import DDSTransport
from alpasim_dds.types.common import SessionRequestStatus, ShutDownRequest, VersionRequest, VersionResponse
from alpasim_dds.types.egodriver import (
    DriveRequest,
    DriveResponse,
    DriveSessionCloseRequest,
    DriveSessionRequest,
    GroundTruthRequest,
    RolloutCameraImage,
    RolloutEgoTrajectory,
    RouteRequest,
)


class DriverEndpoints:
    """Driver 서비스의 모든 DDSTransport를 static으로 생성."""

    def __init__(self, participant: DomainParticipant):
        self.session_start = DDSTransport(
            participant, "driver/session_start",
            DriveSessionRequest, SessionRequestStatus, qos=SESSION_QOS,
        )
        self.session_close = DDSTransport(
            participant, "driver/session_close",
            DriveSessionCloseRequest,
        )
        self.image = DDSTransport(
            participant, "driver/image_observation",
            RolloutCameraImage,
        )
        self.egomotion = DDSTransport(
            participant, "driver/egomotion",
            RolloutEgoTrajectory,
        )
        self.route = DDSTransport(
            participant, "driver/route",
            RouteRequest,
        )
        self.ground_truth = DDSTransport(
            participant, "driver/ground_truth",
            GroundTruthRequest,
        )
        self.drive = DDSTransport(
            participant, "driver/drive",
            DriveRequest, DriveResponse,
        )
        self.version = DDSTransport(
            participant, "driver/version",
            VersionRequest, VersionResponse,
        )
        self.shutdown = DDSTransport(
            participant, "driver/shutdown",
            ShutDownRequest,
        )
