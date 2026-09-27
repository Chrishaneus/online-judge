"""GetStatus: reachability of oj-dao and RabbitMQ plus queue metrics. Never raises for a down dependency."""

import asyncio
import logging

from app.gen.oj.v1 import judge_pb2

from .ports import Dao, Queue

log = logging.getLogger(__name__)


def _describe(exc: BaseException) -> str:
    return f"error: {getattr(exc, 'message', None) or type(exc).__name__}"


class StatusService:
    def __init__(self, dao: Dao, queue: Queue):
        self.dao = dao
        self.queue = queue

    async def get_status(self, _: judge_pb2.GetStatusRequest) -> judge_pb2.GetStatusResponse:
        dao_result, broker_result = await asyncio.gather(
            self.dao.ping(), self.queue.queue_stats(), return_exceptions=True
        )
        res = judge_pb2.GetStatusResponse(dao="ok", broker="ok")
        if isinstance(dao_result, Exception):
            res.dao = _describe(dao_result)
        if isinstance(broker_result, Exception):
            res.broker = _describe(broker_result)
        else:
            res.queue_depth, res.runners = broker_result
        res.healthy = res.dao == "ok" and res.broker == "ok"
        if not res.healthy:
            log.warning("status degraded: dao=%s broker=%s", res.dao, res.broker)
        return res
