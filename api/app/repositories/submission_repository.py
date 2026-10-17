"""Submissions in Postgres. Takes and returns proto messages (plus the records in records.py)."""

import json

from sqlalchemy import text

from app.errors import NotFound, PreconditionFailed
from app.gen.oj.v1 import types_pb2

from . import codecs
from .database import Database
from .problem_repository import timestamp
from .records import SubmissionFilter, SubmissionUpdate

DEFAULT_LIST_LIMIT = 50

SUBMISSION_COLS = (
    "id, problem_id, username, language, source, status, verdict,"
    " passed, total, time_ms, message, results, created_at, updated_at"
)


def to_submission(row) -> types_pb2.Submission:
    m = row._mapping
    return types_pb2.Submission(
        id=m["id"],
        problem_id=m["problem_id"],
        username=m["username"],
        language=codecs.language_from_db(m["language"]),
        source=m["source"],
        status=codecs.status_from_db(m["status"]),
        verdict=codecs.verdict_from_db(m["verdict"]),
        passed=m["passed"],
        total=m["total"],
        time_ms=m["time_ms"],
        message=m["message"],
        results=codecs.results_from_db(m["id"], m["results"]),
        create_time=timestamp(m["created_at"]),
        update_time=timestamp(m["updated_at"]),
    )


class SubmissionRepository:
    def __init__(self, db: Database):
        self.db = db

    def create_submission(self, submission: types_pb2.Submission) -> types_pb2.Submission:
        """Stores a new PENDING submission (only problem_id, username, language and source are used).
        NotFound if the problem does not exist."""
        try:
            with self.db.begin() as conn:
                row = conn.execute(
                    text(
                        "INSERT INTO submissions (problem_id, username, language, source, status)"
                        " VALUES (:problem_id, :username, :language, :source, :status)"
                        f" RETURNING {SUBMISSION_COLS}"
                    ),
                    {
                        "problem_id": submission.problem_id,
                        "username": submission.username,
                        "language": codecs.language_to_db(submission.language),
                        "source": submission.source,
                        "status": codecs.status_to_db(types_pb2.SUBMISSION_STATUS_PENDING),
                    },
                ).one()
        except NotFound as err:  # foreign key violation
            raise NotFound(f"problem {submission.problem_id} not found") from err
        return to_submission(row)

    def get_submission(self, submission_id: int) -> types_pb2.Submission:
        with self.db.begin() as conn:
            row = conn.execute(
                text(f"SELECT {SUBMISSION_COLS} FROM submissions WHERE id = :id"), {"id": submission_id}
            ).first()
        if row is None:
            raise NotFound(f"submission {submission_id} not found")
        return to_submission(row)

    def list_submissions(self, f: SubmissionFilter) -> list[types_pb2.Submission]:
        """Complete rows matching every set filter, newest first."""
        where: list[str] = []
        params: dict = {"limit": f.limit if f.limit > 0 else DEFAULT_LIST_LIMIT, "offset": f.offset}
        if f.problem_id:
            where.append("problem_id = :problem_id")
            params["problem_id"] = f.problem_id
        if f.username:
            where.append("username = :username")
            params["username"] = f.username
        if f.statuses:
            where.append("status = ANY(CAST(:statuses AS text[]))")
            params["statuses"] = [codecs.status_to_db(s) for s in f.statuses]
        if f.updated_before is not None:
            where.append("updated_at < :updated_before")
            params["updated_before"] = f.updated_before
        sql = f"SELECT {SUBMISSION_COLS} FROM submissions"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT :limit OFFSET :offset"
        with self.db.begin() as conn:
            return [to_submission(r) for r in conn.execute(text(sql), params)]

    def update_submission(self, u: SubmissionUpdate) -> types_pb2.Submission:
        """One UPDATE statement whose WHERE clause holds the compare-and-set, so it is atomic. When no row
        matches, a follow-up query tells NotFound apart from PreconditionFailed."""
        sets = ["updated_at = now()"]
        params: dict = {"id": u.id}
        scalar = {
            "status": codecs.status_to_db(u.status) if u.status is not None else None,
            "verdict": codecs.verdict_to_db(u.verdict) if u.verdict is not None else None,
            "passed": u.passed,
            "total": u.total,
            "time_ms": u.time_ms,
            "message": u.message,
        }
        for column, value in scalar.items():
            if value is not None:
                sets.append(f"{column} = :{column}")
                params[column] = value
        if u.results is not None:
            sets.append("results = CAST(:results AS jsonb)")
            params["results"] = json.dumps(codecs.results_to_db(u.results))
        sql = f"UPDATE submissions SET {', '.join(sets)} WHERE id = :id"
        if u.expected_statuses:
            sql += " AND status = ANY(CAST(:expected AS text[]))"
            params["expected"] = [codecs.status_to_db(s) for s in u.expected_statuses]
        sql += f" RETURNING {SUBMISSION_COLS}"

        with self.db.begin() as conn:
            row = conn.execute(text(sql), params).first()
            if row is not None:
                return to_submission(row)
            exists = (
                u.expected_statuses
                and conn.execute(
                    text("SELECT EXISTS (SELECT 1 FROM submissions WHERE id = :id)"), {"id": u.id}
                ).scalar_one()
            )
        if exists:
            raise PreconditionFailed(f"submission {u.id}: status does not match expected_statuses")
        raise NotFound(f"submission {u.id} not found")
