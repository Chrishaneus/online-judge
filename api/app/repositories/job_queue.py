"""RabbitMQ I/O (pika, synchronous): topology, publishing ExecuteJobs, the custom-run RPC, queue stats and
the worker's consumer loop.

Topology and message properties follow the header of proto's oj/v1/runner.proto exactly.

pika's BlockingConnection is not thread-safe, so every thread (each gunicorn gthread worker thread, the
worker's recovery thread) gets its own connection + publisher-confirms channel + exclusive RPC reply
queue, created lazily and re-created after a failure. Those connections run without AMQP heartbeats:
an idle blocking connection cannot answer them, and a dead TCP connection is detected on the next use
(each operation retries once on a fresh connection).
"""

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import pika
import pika.exceptions
from google.protobuf.message import DecodeError
from pika.adapters.blocking_connection import BlockingChannel

from app.errors import Timeout, Unavailable
from app.gen.oj.v1 import runner_pb2

log = logging.getLogger(__name__)

CONTENT_TYPE = "application/x-protobuf"
EXECUTE_JOB_TYPE = "oj.v1.ExecuteJob"
JOB_EVENT_TYPE = "oj.v1.JobEvent"
PERSISTENT = 2
BROKER_TIMEOUT_S = 10.0
RECONNECT_DELAY_S = 3.0

QUORUM = {"x-queue-type": "quorum"}

# Returns True to ack, False to requeue (after a delay); an exception drops the message.
MessageHandler = Callable[[bytes], bool]

BROKER_ERRORS = (pika.exceptions.AMQPError, OSError)


def jobs_queue_arguments(dead_queue: str) -> dict:
    return {
        "x-queue-type": "quorum",
        "x-delivery-limit": 3,
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": dead_queue,
    }


@dataclass
class _Session:
    """One thread's connection. Only ever touched by the thread that created it."""

    connection: pika.BlockingConnection
    channel: BlockingChannel
    reply_queue: str | None = None
    waiting: set[str] = field(default_factory=set)
    results: dict[str, runner_pb2.ExecuteResult] = field(default_factory=dict)


class JobQueue:
    def __init__(
        self,
        url: str,
        *,
        jobs_queue: str = "judge.jobs",
        dead_queue: str = "judge.jobs.dead",
        events_queue: str = "judge.events",
        reply_queue_prefix: str = "judge.rpc.",
    ):
        self.url = url
        self.jobs_queue = jobs_queue
        self.dead_queue = dead_queue
        self.events_queue = events_queue
        self.reply_queue_prefix = reply_queue_prefix
        self._local = threading.local()
        self._lock = threading.Lock()
        self._sessions: list[_Session] = []

    # ---------- connections ----------

    def _parameters(self, heartbeat: int | None) -> pika.URLParameters:
        params = pika.URLParameters(self.url)
        params.connection_attempts = 1
        params.socket_timeout = 5
        params.stack_timeout = BROKER_TIMEOUT_S
        params.blocked_connection_timeout = BROKER_TIMEOUT_S
        if heartbeat is not None:
            params.heartbeat = heartbeat
        return params

    def declare_topology(self, channel: BlockingChannel) -> None:
        """Quorum queues with exactly the arguments of runner.proto (a mismatch is a broker error)."""
        channel.queue_declare(self.dead_queue, durable=True, arguments=QUORUM)
        channel.queue_declare(self.events_queue, durable=True, arguments=QUORUM)
        channel.queue_declare(self.jobs_queue, durable=True, arguments=jobs_queue_arguments(self.dead_queue))

    def _session(self) -> _Session:
        session: _Session | None = getattr(self._local, "session", None)
        if session is not None and session.connection.is_open and session.channel.is_open:
            return session
        self._discard()
        connection = pika.BlockingConnection(self._parameters(heartbeat=0))
        try:
            channel = connection.channel()
            channel.confirm_delivery()
            self.declare_topology(channel)
        except BaseException:
            _close_quietly(connection)
            raise
        session = _Session(connection, channel)
        self._local.session = session
        with self._lock:
            self._sessions.append(session)
        return session

    def _discard(self) -> None:
        session: _Session | None = getattr(self._local, "session", None)
        if session is None:
            return
        self._local.session = None
        with self._lock:
            if session in self._sessions:
                self._sessions.remove(session)
        _close_quietly(session.connection)

    def _call[R](self, what: str, fn: Callable[[_Session], R]) -> R:
        """Run fn on this thread's session; on a broker error retry once on a fresh connection."""
        for attempt in (1, 2):
            try:
                return fn(self._session())
            except BROKER_ERRORS as exc:
                self._discard()
                if attempt == 2:
                    raise Unavailable(f"RabbitMQ unavailable: {what} failed ({type(exc).__name__})") from exc
                log.info("RabbitMQ %s failed (%s); reconnecting", what, type(exc).__name__)
        raise AssertionError("unreachable")

    def connect(self) -> None:
        """Connect this thread and declare the topology. Raises Unavailable if the broker is unreachable."""
        self._call("connect", lambda _: None)

    def close(self) -> None:
        with self._lock:
            sessions, self._sessions = self._sessions, []
        for session in sessions:
            _close_quietly(session.connection)
        self._local.session = None

    # ---------- publishing ----------

    def _properties(self, job: runner_pb2.ExecuteJob, reply_to: str, expiration_s: float | None):
        return pika.BasicProperties(
            content_type=CONTENT_TYPE,
            type=EXECUTE_JOB_TYPE,
            delivery_mode=PERSISTENT,
            correlation_id=job.job_id,
            reply_to=reply_to,
            expiration=None if expiration_s is None else str(max(1, int(expiration_s * 1000))),
        )

    def _publish(self, session: _Session, job: runner_pb2.ExecuteJob, properties) -> None:
        # Publisher confirms + mandatory: returns once the broker has taken the message, raises
        # NackError / UnroutableError otherwise.
        session.channel.basic_publish(
            exchange="",
            routing_key=self.jobs_queue,
            body=job.SerializeToString(),
            properties=properties,
            mandatory=True,
        )

    def publish_submission_job(self, job: runner_pb2.ExecuteJob) -> None:
        """Persistent job whose JobEvents go to judge.events. Waits for the publisher confirm."""
        props = self._properties(job, self.events_queue, None)
        self._call("publish", lambda s: self._publish(s, job, props))

    # ---------- custom-run RPC ----------

    def _ensure_reply_queue(self, session: _Session) -> str:
        if session.reply_queue is None:
            # Client-named (judge.rpc.<uuid>) so the api user's permissions (^judge\..*$) cover it.
            name = f"{self.reply_queue_prefix}{uuid.uuid4().hex}"
            session.channel.queue_declare(name, exclusive=True)

            def on_reply(_ch, _method, props, body: bytes) -> None:
                try:
                    event = runner_pb2.JobEvent.FromString(body)
                except DecodeError:
                    log.warning("dropping undecodable message on reply queue (type=%s)", props.type)
                    return
                if event.WhichOneof("event") != "finished":
                    return
                key = props.correlation_id or event.job_id
                if key in session.waiting:
                    session.results[key] = event.finished

            session.channel.basic_consume(name, on_reply, auto_ack=True)
            session.reply_queue = name
        return session.reply_queue

    def run_job(self, job: runner_pb2.ExecuteJob, timeout_s: float) -> runner_pb2.ExecuteResult:
        """RPC: publish to judge.jobs with reply_to = this thread's reply queue and an AMQP expiration of
        timeout_s (a stale run is dropped instead of executed), then wait for the `finished` event."""
        deadline = time.monotonic() + timeout_s

        def publish(session: _Session) -> _Session:
            reply_to = self._ensure_reply_queue(session)
            session.waiting.add(job.job_id)
            self._publish(session, job, self._properties(job, reply_to, timeout_s))
            return session

        session = self._call("publish", publish)
        try:
            while job.job_id not in session.results:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Timeout(f"No runner answered within {timeout_s:g}s")
                session.connection.process_data_events(time_limit=min(remaining, 1.0))
            return session.results[job.job_id]
        except BROKER_ERRORS as exc:
            self._discard()
            raise Unavailable(f"RabbitMQ unavailable: lost connection ({type(exc).__name__})") from exc
        finally:
            session.waiting.discard(job.job_id)
            session.results.pop(job.job_id, None)

    # ---------- stats ----------

    def queue_stats(self) -> tuple[int, int]:
        """(messages ready in judge.jobs, consumers of judge.jobs) via a passive declare."""

        def stats(session: _Session) -> tuple[int, int]:
            ok = session.channel.queue_declare(self.jobs_queue, passive=True)
            return ok.method.message_count or 0, ok.method.consumer_count or 0

        return self._call("queue stats", stats)

    # ---------- consuming (worker) ----------

    def consume(
        self,
        handlers: dict[str, MessageHandler],
        *,
        stop: threading.Event,
        on_tick: Callable[[], None] = lambda: None,
        prefetch: int = 16,
        requeue_delay_s: float = 2.0,
        tick_s: float = 1.0,
    ) -> None:
        """Consume the given queues until `stop` is set, reconnecting after broker failures.

        A handler returning True acks; False waits requeue_delay_s and nacks with requeue (on RabbitMQ 4
        quorum queues nack(requeue=true) does not raise x-delivery-count, so a long database outage
        never drops events); an exception logs and rejects without requeue. on_tick runs at least
        every tick_s while the consumers are active (heartbeat file).
        """
        while not stop.is_set():
            connection = None
            try:
                connection = pika.BlockingConnection(self._parameters(heartbeat=None))
                channel = connection.channel()
                channel.basic_qos(prefetch_count=prefetch)
                self.declare_topology(channel)
                for queue, handler in handlers.items():
                    channel.basic_consume(queue, _on_message(queue, handler, requeue_delay_s))
                log.info("consuming %s", ", ".join(handlers))
                while not stop.is_set():
                    on_tick()
                    connection.process_data_events(time_limit=tick_s)
            except BROKER_ERRORS as exc:
                log.warning("RabbitMQ consumer error (%s: %s); reconnecting", type(exc).__name__, exc)
                stop.wait(RECONNECT_DELAY_S)
            finally:
                if connection is not None:
                    _close_quietly(connection)


def _on_message(queue: str, handler: MessageHandler, requeue_delay_s: float):
    def on_message(channel: BlockingChannel, method, _props, body: bytes) -> None:
        try:
            ok = handler(body)
        except Exception:
            log.exception("dropping message from %s after handler error", queue)
            channel.basic_reject(method.delivery_tag, requeue=False)
            return
        if ok:
            channel.basic_ack(method.delivery_tag)
        else:
            time.sleep(requeue_delay_s)
            channel.basic_nack(method.delivery_tag, requeue=True)

    return on_message


def _close_quietly(connection: pika.BlockingConnection) -> None:
    try:
        if connection.is_open:
            connection.close()
    except Exception:  # already broken: nothing left to release
        log.debug("error closing RabbitMQ connection", exc_info=True)
