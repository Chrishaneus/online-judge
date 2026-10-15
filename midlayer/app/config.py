"""Settings read from environment variables (see README.md)."""

import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    return os.environ.get(name) or default


@dataclass(frozen=True)
class Settings:
    grpc_addr: str = "[::]:50051"
    dao_addr: str = "localhost:50052"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    run_timeout_s: float = 30.0
    max_queue_depth: int = 1000
    recover_after_s: float = 300.0
    dao_timeout_s: float = 10.0
    # Topology names. Fixed by proto's runner.proto; only overridden by tests that share a broker.
    jobs_queue: str = "judge.jobs"
    dead_queue: str = "judge.jobs.dead"
    events_queue: str = "judge.events"
    reply_queue_prefix: str = "judge.rpc."
    # Consumer tuning.
    prefetch: int = 16
    requeue_delay_s: float = 2.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            grpc_addr=_env("GRPC_ADDR", cls.grpc_addr),
            dao_addr=_env("DAO_ADDR", cls.dao_addr),
            rabbitmq_url=_env("RABBITMQ_URL", cls.rabbitmq_url),
            run_timeout_s=float(_env("RUN_TIMEOUT_S", str(cls.run_timeout_s))),
            max_queue_depth=int(_env("MAX_QUEUE_DEPTH", str(cls.max_queue_depth))),
            recover_after_s=float(_env("RECOVER_AFTER_S", str(cls.recover_after_s))),
            dao_timeout_s=float(_env("DAO_TIMEOUT_S", str(cls.dao_timeout_s))),
        )
