from cyclonedds.domain import DomainParticipant

from alpasim_dds.qos import RELIABLE_QOS
from alpasim_dds.transport import DDSServerTransport
from alpasim_dds.types.common import (
    AvailableScenesRequest,
    AvailableScenesResponse,
    ShutDownRequest,
    VersionRequest,
    VersionResponse,
)
from alpasim_dds.types.physics import (
    PhysicsGroundIntersectionRequest,
    PhysicsGroundIntersectionReturn,
)


class PhysicsServerEndpoints:
    """Physics 서버의 모든 DDSServerTransport."""

    def __init__(self, participant: DomainParticipant):
        self.ground_intersection = DDSServerTransport(
            participant, "physics/ground_intersection",
            PhysicsGroundIntersectionRequest, PhysicsGroundIntersectionReturn,
        )
        self.available_scenes = DDSServerTransport(
            participant, "physics/available_scenes",
            AvailableScenesRequest, AvailableScenesResponse,
        )
        self.version = DDSServerTransport(
            participant, "physics/version",
            VersionRequest, VersionResponse,
        )
        self.shutdown = DDSServerTransport(
            participant, "physics/shutdown",
            ShutDownRequest,
        )
