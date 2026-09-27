"""Business logic on proto messages. Raises app.errors.*; no grpc or aio-pika imports."""

from dataclasses import dataclass

from .languages import LanguageService
from .problem_service import ProblemService
from .run_service import RunService
from .status_service import StatusService
from .submission_service import SubmissionService


@dataclass(frozen=True)
class Services:
    languages: LanguageService
    problems: ProblemService
    submissions: SubmissionService
    runs: RunService
    status: StatusService


__all__ = [
    "LanguageService",
    "ProblemService",
    "RunService",
    "Services",
    "StatusService",
    "SubmissionService",
]
