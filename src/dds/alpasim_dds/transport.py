import asyncio
import time
from uuid import uuid4

from cyclonedds.domain import DomainParticipant
from cyclonedds.pub import DataWriter
from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic

from alpasim_dds.qos import RELIABLE_QOS


class DDSTransport:
    """서비스 간 통신을 추상화하는 단일 클래스.

    - resp_type이 있으면 양방향 (request → response)
    - resp_type이 없으면 단방향 (send, fire-and-forget)
    """

    def __init__(self, participant, name, req_type, resp_type=None, qos=RELIABLE_QOS):
        self.writer = DataWriter(
            participant, Topic(participant, f"{name}/req", req_type), qos=qos
        )
        if resp_type is not None:
            self.reader = DataReader(
                participant, Topic(participant, f"{name}/resp", resp_type), qos=qos
            )
        else:
            self.reader = None

    def send(self, data):
        """단방향 — 보내고 끝 (fire-and-forget)."""
        self.writer.write(data)

    async def request(self, data, timeout_s=5.0):
        """양방향 — 보내고 응답 대기 (take() polling)."""
        assert self.reader is not None, "양방향 transport가 아님 (resp_type 미지정)"
        correlation_id = str(uuid4())
        data.correlation_id = correlation_id
        self.writer.write(data)
        return await self._wait_for_response(correlation_id, timeout_s)

    async def _wait_for_response(self, correlation_id, timeout_s):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for sample in self.reader.take():
                if sample.correlation_id == correlation_id:
                    return sample
            await asyncio.sleep(0.001)
        raise TimeoutError(
            f"correlation_id={correlation_id} 응답 없음 ({timeout_s}s 초과)"
        )
