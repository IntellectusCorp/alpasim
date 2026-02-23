from cyclonedds.domain import DomainParticipant

from alpasim_dds.transport import DDSTransport
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


class PhysicsEndpoints:
    """Physics 서비스의 모든 DDSTransport를 static으로 생성."""

    def __init__(self, participant: DomainParticipant):
        self.ground_intersection = DDSTransport(
            participant, "physics/ground_intersection",
            PhysicsGroundIntersectionRequest, PhysicsGroundIntersectionReturn,
        )
        self.available_scenes = DDSTransport(
            participant, "physics/available_scenes",
            AvailableScenesRequest, AvailableScenesResponse,
        )
        self.version = DDSTransport(
            participant, "physics/version",
            VersionRequest, VersionResponse,
        )
        self.shutdown = DDSTransport(
            participant, "physics/shutdown",
            ShutDownRequest,
        )
