from cyclonedds.domain import DomainParticipant

from alpasim_dds.qos import SESSION_QOS
from alpasim_dds.transport import DDSServerTransport
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


class DriverServerEndpoints:
    """Driver 서버의 모든 DDSServerTransport."""

    def __init__(self, participant: DomainParticipant):
        self.session_start = DDSServerTransport(
            participant, "driver/session_start",
            DriveSessionRequest, SessionRequestStatus, qos=SESSION_QOS,
        )
        self.session_close = DDSServerTransport(
            participant, "driver/session_close",
            DriveSessionCloseRequest,
        )
        self.image = DDSServerTransport(
            participant, "driver/image_observation",
            RolloutCameraImage,
        )
        self.egomotion = DDSServerTransport(
            participant, "driver/egomotion",
            RolloutEgoTrajectory,
        )
        self.route = DDSServerTransport(
            participant, "driver/route",
            RouteRequest,
        )
        self.ground_truth = DDSServerTransport(
            participant, "driver/ground_truth",
            GroundTruthRequest,
        )
        self.drive = DDSServerTransport(
            participant, "driver/drive",
            DriveRequest, DriveResponse,
        )
        self.version = DDSServerTransport(
            participant, "driver/version",
            VersionRequest, VersionResponse,
        )
        self.shutdown = DDSServerTransport(
            participant, "driver/shutdown",
            ShutDownRequest,
        )
