import asyncio
import inspect
import logging
from uuid import uuid4

from cyclonedds.domain import DomainParticipant
from cyclonedds.pub import DataWriter
from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic

from alpasim_dds.qos import RELIABLE_QOS

logger = logging.getLogger(__name__)


class DDSTransport:
    """서비스 간 통신을 추상화하는 단일 클래스.

    - resp_type이 있으면 양방향 (request → response)
    - resp_type이 없으면 단방향 (send, fire-and-forget)
    """

    def __init__(self, participant, name, req_type, resp_type=None, qos=RELIABLE_QOS):
        self.name = name
        self.writer = DataWriter(
            participant, Topic(participant, f"{name}/req", req_type), qos=qos
        )
        if resp_type is not None:
            self.reader = DataReader(
                participant, Topic(participant, f"{name}/resp", resp_type), qos=qos
            )
        else:
            self.reader = None
        self._pending: dict[str, asyncio.Future] = {}
        self._dispatch_task: asyncio.Task | None = None

    def send(self, data):
        """단방향 — 보내고 끝 (fire-and-forget)."""
        self.writer.write(data)

    async def request(self, data):
        """양방향 — 보내고 응답 대기 (concurrent-safe)."""
        assert self.reader is not None, "양방향 transport가 아님 (resp_type 미지정)"
        correlation_id = str(uuid4())
        data.correlation_id = correlation_id

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[correlation_id] = future

        if self._dispatch_task is None or self._dispatch_task.done():
            self._dispatch_task = asyncio.ensure_future(self._dispatch_responses())

        self.writer.write(data)
        logger.info("[%s] Request sent (correlation_id=%s, pending=%d)", self.name, correlation_id, len(self._pending))
        try:
            result = await future
            logger.info("[%s] Response received (correlation_id=%s)", self.name, correlation_id)
            return result
        finally:
            self._pending.pop(correlation_id, None)

    async def _dispatch_responses(self):
        """reader에서 샘플을 읽어 pending future에 분배."""
        while self._pending:
            for sample in self.reader.take():
                if type(sample).__name__ == "InvalidSample":
                    continue
                cid = getattr(sample, "correlation_id", None)
                if cid and cid in self._pending:
                    logger.info("[%s] Dispatching response (correlation_id=%s, remaining=%d)", self.name, cid, len(self._pending) - 1)
                    self._pending[cid].set_result(sample)
                else:
                    logger.info("[%s] Unmatched response (correlation_id=%s)", self.name, cid)
            await asyncio.sleep(0.001)


class DDSServerTransport:
    """서버 측 transport. 클라이언트의 반대 방향으로 동작.

    - req topic을 읽고, resp topic에 쓴다.
    - resp_type이 있으면 양방향 (handler 결과를 resp로 write)
    - resp_type이 없으면 단방향 (handler 호출만, 응답 없음)
    """

    def __init__(self, participant, name, req_type, resp_type=None, qos=RELIABLE_QOS):
        self.name = name
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
                if type(sample).__name__ == "InvalidSample":
                    logger.info("[%s] Skipping InvalidSample", self.name)
                    continue
                try:
                    if inspect.iscoroutinefunction(handler):
                        result = await handler(sample)
                    else:
                        result = handler(sample)
                except Exception:
                    logger.exception("[%s] Exception during handler execution", self.name)
                    continue
                if self.writer is not None and result is not None:
                    if hasattr(sample, "correlation_id"):
                        result.correlation_id = sample.correlation_id
                    try:
                        self.writer.write(result)
                        logger.info("[%s] Response written (correlation_id=%s)", self.name, getattr(result, "correlation_id", "N/A"))
                    except Exception:
                        logger.exception("[%s] Exception during response serialize/write", self.name)
            await asyncio.sleep(0.001)
