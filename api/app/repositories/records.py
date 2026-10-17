"""Plain records passed to repositories (the inputs that have no proto message of their own)."""

from dataclasses import dataclass, field
from datetime import datetime

from app.gen.oj.v1 import types_pb2


@dataclass
class SubmissionFilter:
    """Selects submissions; zero values mean "any". Results are newest first."""

    problem_id: int = 0
    username: str = ""
    # Any of these SubmissionStatus values.
    statuses: list[int] = field(default_factory=list)
    # Keeps submissions whose update_time is strictly before it.
    updated_before: datetime | None = None
    # 0 means DEFAULT_LIST_LIMIT.
    limit: int = 0
    offset: int = 0


@dataclass
class SubmissionUpdate:
    """Partial update of a submission: None fields are left unchanged; update_time is always bumped.

    `results` replaces the stored results when not None (an empty list clears them).
    `expected_statuses`, when non-empty, makes the update an atomic compare-and-set: it applies only if
    the current status is one of them, else PreconditionFailed and nothing changes.
    """

    id: int
    status: int | None = None
    verdict: int | None = None
    passed: int | None = None
    total: int | None = None
    time_ms: int | None = None
    message: str | None = None
    results: list[types_pb2.TestResult] | None = None
    expected_statuses: list[int] = field(default_factory=list)
