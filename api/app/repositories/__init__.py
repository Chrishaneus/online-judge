"""All I/O: Postgres (SQLAlchemy Core + psycopg) and RabbitMQ (pika). No business rules."""

from dataclasses import dataclass

from .database import Database
from .job_queue import JobQueue
from .problem_repository import ProblemRepository
from .records import SubmissionFilter, SubmissionUpdate
from .submission_repository import SubmissionRepository


@dataclass(frozen=True)
class Repositories:
    """What create_app / the worker inject into services. Tests pass fakes."""

    database: Database
    problems: ProblemRepository
    submissions: SubmissionRepository
    queue: JobQueue

    @classmethod
    def from_settings(cls, settings) -> "Repositories":
        db = Database(settings.database_url, pool_size=settings.api_threads)
        return cls(
            database=db,
            problems=ProblemRepository(db),
            submissions=SubmissionRepository(db),
            queue=JobQueue(
                settings.rabbitmq_url,
                jobs_queue=settings.jobs_queue,
                dead_queue=settings.dead_queue,
                events_queue=settings.events_queue,
                reply_queue_prefix=settings.reply_queue_prefix,
            ),
        )


__all__ = [
    "Database",
    "JobQueue",
    "ProblemRepository",
    "Repositories",
    "SubmissionFilter",
    "SubmissionRepository",
    "SubmissionUpdate",
]
