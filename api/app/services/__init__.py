"""Business logic on proto messages. Raises app.errors.*; no Flask, SQL or pika."""

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


def build_services(settings, repositories) -> Services:
    """Inject repositories (real or fake) into the services."""
    r = repositories
    return Services(
        languages=LanguageService(),
        problems=ProblemService(r.problems),
        submissions=SubmissionService(
            r.problems,
            r.submissions,
            r.queue,
            max_queue_depth=settings.max_queue_depth,
            recover_after_s=settings.recover_after_s,
        ),
        runs=RunService(r.problems, r.queue, run_timeout_s=settings.run_timeout_s),
        status=StatusService(r.database, r.queue),
    )


__all__ = [
    "LanguageService",
    "ProblemService",
    "RunService",
    "Services",
    "StatusService",
    "SubmissionService",
    "build_services",
]
