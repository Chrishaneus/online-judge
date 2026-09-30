"""App factory. Layers (dependencies point downward only):

transport/     gRPC JudgeService servicer + RabbitMQ consumers: decode, call ONE service method, map errors
services/      business logic on proto messages; raises app.errors; no grpc/aio-pika imports
repositories/  all I/O: oj-dao over gRPC, RabbitMQ over AMQP
gen/           code generated from oj-proto - never edit
"""

import asyncio
import logging

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from .config import Settings
from .gen.oj.v1 import judge_pb2, judge_pb2_grpc
from .repositories import DaoRepository, JobQueue
from .services import (
    LanguageService,
    ProblemService,
    RunService,
    Services,
    StatusService,
    SubmissionService,
)
from .services.ports import Dao
from .transport import JudgeConsumers, JudgeServicer, LoggingInterceptor

log = logging.getLogger("app")

MAX_MESSAGE_BYTES = 64 * 1024 * 1024
SERVER_OPTIONS = [
    ("grpc.max_send_message_length", MAX_MESSAGE_BYTES),
    ("grpc.max_receive_message_length", MAX_MESSAGE_BYTES),
]
JUDGE_SERVICE = judge_pb2.DESCRIPTOR.services_by_name["JudgeService"].full_name
BROKER_RETRY_S = 3.0


class App:
    """Owns the gRPC server, the repositories and the consumers. start() / stop() run it."""

    def __init__(self, settings: Settings, dao, queue, services: Services):
        self.settings = settings
        self.dao = dao
        self.queue = queue
        self.services = services
        self.consumers = JudgeConsumers(services.submissions)
        self.health = health.aio.HealthServicer()
        self.server: grpc.aio.Server | None = None
        self.port: int | None = None
        self._recovery: asyncio.Task | None = None

    async def start(self, *, recover: bool = True) -> None:
        await self._start_queue()
        await self.queue.consume(self.queue.events_queue, self.consumers.on_job_event)
        await self.queue.consume(self.queue.dead_queue, self.consumers.on_dead_job)

        self.server = grpc.aio.server(interceptors=[LoggingInterceptor()], options=SERVER_OPTIONS)
        judge_pb2_grpc.add_JudgeServiceServicer_to_server(JudgeServicer(self.services), self.server)
        health_pb2_grpc.add_HealthServicer_to_server(self.health, self.server)
        self.port = self.server.add_insecure_port(self.settings.grpc_addr)
        await self.server.start()
        for name in ("", JUDGE_SERVICE):
            await self.health.set(name, health_pb2.HealthCheckResponse.SERVING)
        log.info("JudgeService listening on %s (dao=%s)", self.settings.grpc_addr, self.settings.dao_addr)

        if recover:
            self._recovery = asyncio.create_task(self._recover())

    async def _start_queue(self) -> None:
        while True:
            try:
                await self.queue.start()
                return
            except Exception as exc:  # noqa: BLE001 - broker not up yet: retry; health stays NOT_SERVING
                log.warning("RabbitMQ not reachable (%s); retrying in %.0fs", exc, BROKER_RETRY_S)
                await asyncio.sleep(BROKER_RETRY_S)

    async def _recover(self) -> None:
        try:
            await self.services.submissions.recover()
        except Exception:
            log.exception("recovery of unfinished submissions failed")

    async def stop(self, grace: float = 5.0) -> None:
        await self.health.enter_graceful_shutdown()
        if self._recovery is not None:
            self._recovery.cancel()
        if self.server is not None:
            await self.server.stop(grace)
        await self.queue.close()
        await self.dao.close()


def create_app(settings: Settings | None = None, dao: Dao | None = None, queue=None) -> App:
    settings = settings or Settings.from_env()
    dao = dao or DaoRepository(settings.dao_addr, settings.dao_timeout_s)
    queue = queue or JobQueue(
        settings.rabbitmq_url,
        jobs_queue=settings.jobs_queue,
        dead_queue=settings.dead_queue,
        events_queue=settings.events_queue,
        reply_queue_prefix=settings.reply_queue_prefix,
        prefetch=settings.prefetch,
        requeue_delay_s=settings.requeue_delay_s,
    )
    services = Services(
        languages=LanguageService(),
        problems=ProblemService(dao),
        submissions=SubmissionService(
            dao, queue, max_queue_depth=settings.max_queue_depth, recover_after_s=settings.recover_after_s
        ),
        runs=RunService(dao, queue, run_timeout_s=settings.run_timeout_s),
        status=StatusService(dao, queue),
    )
    return App(settings, dao, queue, services)
