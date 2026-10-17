"""Settings read from environment variables (see README.md). Shared by the HTTP app and the worker."""

import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    return os.environ.get(name) or default


@dataclass(frozen=True)
class Settings:
    port: int = 8000
    database_url: str = "postgresql+psycopg://oj:oj@localhost:5432/oj"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    # Empty disables the admin API (403).
    admin_token: str = ""
    cors_origins: tuple[str, ...] = ("*",)
    rate_limit_per_min: int = 20
    rate_limit_burst: int = 5
    trust_proxy_headers: bool = False
    run_timeout_s: float = 30.0
    max_queue_depth: int = 1000
    recover_after_s: float = 300.0
    api_threads: int = 16
    worker_health_file: str = "/tmp/worker-healthy"
    # Topology names. Fixed by proto's runner.proto; only overridden by tests that share a broker.
    jobs_queue: str = "judge.jobs"
    dead_queue: str = "judge.jobs.dead"
    events_queue: str = "judge.events"
    reply_queue_prefix: str = "judge.rpc."
    # Worker tuning.
    prefetch: int = 16
    requeue_delay_s: float = 2.0

    @classmethod
    def from_env(cls) -> "Settings":
        d = cls()
        return cls(
            port=int(_env("PORT", str(d.port))),
            database_url=_env("DATABASE_URL", d.database_url),
            rabbitmq_url=_env("RABBITMQ_URL", d.rabbitmq_url),
            admin_token=os.environ.get("ADMIN_TOKEN", ""),
            cors_origins=tuple(o.strip() for o in _env("CORS_ORIGINS", "*").split(",") if o.strip()),
            rate_limit_per_min=int(_env("RATE_LIMIT_PER_MIN", str(d.rate_limit_per_min))),
            rate_limit_burst=int(_env("RATE_LIMIT_BURST", str(d.rate_limit_burst))),
            trust_proxy_headers=os.environ.get("TRUST_PROXY_HEADERS", "").lower() == "true",
            run_timeout_s=float(_env("RUN_TIMEOUT_S", str(d.run_timeout_s))),
            max_queue_depth=int(_env("MAX_QUEUE_DEPTH", str(d.max_queue_depth))),
            recover_after_s=float(_env("RECOVER_AFTER_S", str(d.recover_after_s))),
            api_threads=int(_env("API_THREADS", str(d.api_threads))),
            worker_health_file=_env("WORKER_HEALTH_FILE", d.worker_health_file),
            jobs_queue=_env("JOBS_QUEUE", d.jobs_queue),
            dead_queue=_env("DEAD_QUEUE", d.dead_queue),
            events_queue=_env("EVENTS_QUEUE", d.events_queue),
            reply_queue_prefix=_env("REPLY_QUEUE_PREFIX", d.reply_queue_prefix),
        )
