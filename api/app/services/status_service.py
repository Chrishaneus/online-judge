"""GetStatus: reachability of Postgres and RabbitMQ plus queue metrics. Never raises for a down dependency."""

import logging

from app.gen.oj.v1 import judge_pb2

from .ports import Database, Queue

log = logging.getLogger(__name__)


def _describe(exc: BaseException) -> str:
    return f"error: {getattr(exc, 'message', None) or type(exc).__name__}"


class StatusService:
    def __init__(self, database: Database, queue: Queue):
        self.database = database
        self.queue = queue

    def get_status(self, _: judge_pb2.GetStatusRequest) -> judge_pb2.GetStatusResponse:
        res = judge_pb2.GetStatusResponse(database="ok", broker="ok")
        try:
            self.database.ping()
        except Exception as exc:  # noqa: BLE001 - any failure is reported, never raised
            res.database = _describe(exc)
        try:
            res.queue_depth, res.runners = self.queue.queue_stats()
        except Exception as exc:  # noqa: BLE001 - reported, never raised
            res.broker = _describe(exc)
        res.healthy = res.database == "ok" and res.broker == "ok"
        if not res.healthy:
            log.warning("status degraded: database=%s broker=%s", res.database, res.broker)
        return res
