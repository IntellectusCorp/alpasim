from cyclonedds.domain import DomainParticipant

_participant: DomainParticipant | None = None


def get_participant(domain_id: int = 0) -> DomainParticipant:
    global _participant
    if _participant is None:
        _participant = DomainParticipant(domain_id)
    return _participant
