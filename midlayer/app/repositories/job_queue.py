"""RabbitMQ I/O (aio-pika): topology, publishing ExecuteJobs, the custom-run RPC and consumers.

Topology and message properties follow the header of oj-proto's oj/v1/runner.proto exactly.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustChannel, AbstractRobustConnection
from aio_pika.connection import make_url
from google.protobuf.message import DecodeError

from app.errors import DeadlineExceeded, Unavailable
from app.gen.oj.v1 import runner_pb2

log = logging.getLogger(__name__)

CONTENT_TYPE = "application/x-protobuf"
EXECUTE_JOB_TYPE = "oj.v1.ExecuteJob"
JOB_EVENT_TYPE = "oj.v1.JobEvent"
BROKER_TIMEOUT_S = 10.0

# Returns True to ack, False to requeue (after a delay); an exception drops the message.
MessageHandler = Callable[[bytes], Awaitable[bool]]


def jobs_queue_arguments(dead_queue: str) -> dict:
    return {
        "x-queue-type": "quorum",
        "x-delivery-limit": 3,
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": dead_queue,
    }


QUORUM = {"x-queue-type": "quorum"}


class JobQueue:
    """Owns one robust connection: a publisher-confirms channel and a consumer channel.

    Reconnects automatically (connect_robust); queues and consumers are restored on reconnect.
    """

    def __init__(
        self,
        url: str,
        *,
        jobs_queue: str = "judge.jobs",
        dead_queue: str = "judge.jobs.dead",
        events_queue: str = "judge.events",
        reply_queue_prefix: str = "judge.rpc.",
        prefetch: int = 16,
        requeue_delay_s: float = 2.0,
    ):
        self.url = url
        self.jobs_queue = jobs_queue
        self.dead_queue = dead_queue
        self.events_queue = events_queue
        # Named by us (not server-named) so connect_robust can re-declare it after a reconnect.
        self.reply_queue = f"{reply_queue_prefix}{uuid.uuid4().hex}"
        self.prefetch = prefetch
        self.requeue_delay_s = requeue_delay_s
        self._connection: AbstractRobustConnection | None = None
        self._publish_channel: AbstractRobustChannel | None = None
        self._consume_channel: AbstractRobustChannel | None = None
        self._stats_channel = None
        self._queues: dict[str, aio_pika.abc.AbstractQueue] = {}
        self._pending: dict[str, asyncio.Future[runner_pb2.ExecuteResult]] = {}

    # ---------- lifecycle ----------

    async def start(self) -> None:
        """Connect, declare the topology and the RPC reply queue. Raises if the broker is unreachable."""
        # Same as aio_pika.connect_robust, but a failed first attempt is closed instead of being
        # left behind reconnecting in the background.
        connection = aio_pika.RobustConnection(make_url(self.url))
        try:
            await connection.connect(timeout=BROKER_TIMEOUT_S)
        except BaseException:
            await connection.close()
            raise
        self._connection = connection
        self._publish_channel = await self._connection.channel(publisher_confirms=True, on_return_raises=True)
        self._consume_channel = await self._connection.channel()
        await self._consume_channel.set_qos(prefetch_count=self.prefetch)
        await self.declare_topology()
        reply = await self._consume_channel.declare_queue(self.reply_queue, exclusive=True)
        await reply.consume(self._on_reply, no_ack=True)

    async def declare_topology(self) -> None:
        ch = self._consume_channel
        self._queues[self.dead_queue] = await ch.declare_queue(
            self.dead_queue, durable=True, arguments=QUORUM
        )
        self._queues[self.events_queue] = await ch.declare_queue(
            self.events_queue, durable=True, arguments=QUORUM
        )
        self._queues[self.jobs_queue] = await ch.declare_queue(
            self.jobs_queue, durable=True, arguments=jobs_queue_arguments(self.dead_queue)
        )

    async def close(self) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    # ---------- publishing ----------

    def _job_message(self, job: runner_pb2.ExecuteJob, reply_to: str, expiration_s: float | None):
        return aio_pika.Message(
            job.SerializeToString(),
            content_type=CONTENT_TYPE,
            type=EXECUTE_JOB_TYPE,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            correlation_id=job.job_id,
            reply_to=reply_to,
            expiration=expiration_s,
        )

    async def _publish(self, message: aio_pika.Message) -> None:
        if self._publish_channel is None or self._publish_channel.is_closed:
            raise Unavailable("RabbitMQ unavailable: not connected")
        try:
            await self._publish_channel.default_exchange.publish(
                message, routing_key=self.jobs_queue, mandatory=True, timeout=BROKER_TIMEOUT_S
            )
        except Exception as exc:  # broker errors come in many shapes (aiormq, asyncio, OSError)
            raise Unavailable(f"RabbitMQ unavailable: publish failed ({type(exc).__name__})") from exc

    async def publish_submission_job(self, job: runner_pb2.ExecuteJob) -> None:
        """Publish a persistent job whose JobEvents go to judge.events. Waits for the publisher confirm."""
        await self._publish(self._job_message(job, self.events_queue, None))

    async def run_job(self, job: runner_pb2.ExecuteJob, timeout_s: float) -> runner_pb2.ExecuteResult:
        """RPC: publish to judge.jobs with reply_to = our reply queue and wait for the `finished` event."""
        fut: asyncio.Future[runner_pb2.ExecuteResult] = asyncio.get_running_loop().create_future()
        self._pending[job.job_id] = fut
        try:
            await self._publish(self._job_message(job, self.reply_queue, timeout_s))
            async with asyncio.timeout(timeout_s):
                return await fut
        except TimeoutError as exc:
            raise DeadlineExceeded(f"No runner answered within {timeout_s:g}s") from exc
        finally:
            self._pending.pop(job.job_id, None)

    async def _on_reply(self, message: AbstractIncomingMessage) -> None:
        try:
            event = runner_pb2.JobEvent.FromString(message.body)
        except DecodeError:
            log.warning("dropping undecodable message on reply queue (type=%s)", message.type)
            return
        if event.WhichOneof("event") != "finished":
            return
        fut = self._pending.get(message.correlation_id or event.job_id)
        if fut is not None and not fut.done():
            fut.set_result(event.finished)

    # ---------- consuming ----------

    async def consume(self, queue: str, handler: MessageHandler) -> None:
        """Consume a declared queue. Ack when the handler returns True; on False wait
        requeue_delay_s and nack with requeue; if it raises, log and drop the message."""

        async def on_message(message: AbstractIncomingMessage) -> None:
            try:
                ok = await handler(message.body)
            except Exception:
                log.exception("dropping message from %s after handler error", queue)
                await message.reject(requeue=False)
                return
            if ok:
                await message.ack()
            else:
                await asyncio.sleep(self.requeue_delay_s)
                await message.nack(requeue=True)

        await self._queues[queue].consume(on_message)

    # ---------- stats ----------

    async def queue_stats(self) -> tuple[int, int]:
        """(messages ready in judge.jobs, consumers of judge.jobs) via a passive declare."""
        if self._connection is None or self._connection.is_closed:
            raise Unavailable("RabbitMQ unavailable: not connected")
        try:
            async with asyncio.timeout(BROKER_TIMEOUT_S):
                if self._stats_channel is None or self._stats_channel.is_closed:
                    self._stats_channel = await self._connection.channel()
                # robust=False: a robust channel would return a cached queue with stale counts.
                q = await self._stats_channel.declare_queue(self.jobs_queue, passive=True, robust=False)
        except Exception as exc:
            raise Unavailable(f"RabbitMQ unavailable: {type(exc).__name__}") from exc
        result = q.declaration_result
        return result.message_count or 0, result.consumer_count or 0
