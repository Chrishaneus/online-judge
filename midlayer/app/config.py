from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    dao_url: str = "http://localhost:8001"
    runner_url: str = "http://localhost:8002"
    judge_workers: int = 4
    runner_timeout_s: float = 600.0
    dao_timeout_s: float = 10.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            dao_url=os.getenv("DAO_URL", cls.dao_url),
            runner_url=os.getenv("RUNNER_URL", cls.runner_url),
            judge_workers=_int("JUDGE_WORKERS", cls.judge_workers),
            runner_timeout_s=float(os.getenv("RUNNER_TIMEOUT_S", cls.runner_timeout_s)),
            dao_timeout_s=float(os.getenv("DAO_TIMEOUT_S", cls.dao_timeout_s)),
        )
