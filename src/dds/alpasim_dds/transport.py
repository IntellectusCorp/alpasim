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


class DDSServerTransport:
    """서버 측 transport. 클라이언트의 반대 방향으로 동작.

    - req topic을 읽고, resp topic에 쓴다.
    - resp_type이 있으면 양방향 (handler 결과를 resp로 write)
    - resp_type이 없으면 단방향 (handler 호출만, 응답 없음)
    """

    def __init__(self, participant, name, req_type, resp_type=None, qos=RELIABLE_QOS):
        self.reader = DataReader(
            participant, Topic(participant, f"{name}/req", req_type), qos=qos
        )
        if resp_type is not None:
            self.writer = DataWriter(
                participant, Topic(participant, f"{name}/resp", resp_type), qos=qos
            )
        else:
            self.writer = None

    async def serve(self, handler, stop_event=None):
        """요청을 polling하고 handler 호출, 양방향이면 응답 write.

        handler는 async 또는 sync 함수. 반환값이 있으면 응답으로 write.
        stop_event가 set되면 루프를 종료.
        """
        while stop_event is None or not stop_event.is_set():
            for sample in self.reader.take():
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(sample)
                else:
                    result = handler(sample)
                if self.writer is not None and result is not None:
                    if hasattr(sample, "correlation_id"):
                        result.correlation_id = sample.correlation_id
                    self.writer.write(result)
            await asyncio.sleep(0.001)
