from cyclonedds.domain import DomainParticipant

DEFAULT_DOMAIN_ID = 77

_participant: DomainParticipant | None = None


def get_participant(domain_id: int = DEFAULT_DOMAIN_ID) -> DomainParticipant:
    global _participant
    if _participant is None:
        _participant = DomainParticipant(domain_id)
    return _participant
