"""Problems and their test cases in Postgres. Takes and returns proto messages. No business rules."""

from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy import Connection, text

from app.errors import Conflict, NotFound
from app.gen.oj.v1 import types_pb2

from . import codecs
from .database import Database

PROBLEM_COLS = "id, slug, title, statement, difficulty, time_limit_ms, memory_limit_mb, created_at"
TEST_CASE_COLS = "id, problem_id, input, expected_output, is_sample, ordinal"


def timestamp(dt) -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


def to_problem(row) -> types_pb2.Problem:
    m = row._mapping
    return types_pb2.Problem(
        id=m["id"],
        slug=m["slug"],
        title=m["title"],
        statement=m["statement"],
        difficulty=codecs.difficulty_from_db(m["difficulty"]),
        time_limit_ms=m["time_limit_ms"],
        memory_limit_mb=m["memory_limit_mb"],
        create_time=timestamp(m["created_at"]),
    )


def to_test_case(row) -> types_pb2.TestCase:
    m = row._mapping
    return types_pb2.TestCase(
        id=m["id"],
        problem_id=m["problem_id"],
        input=m["input"],
        expected_output=m["expected_output"],
        is_sample=m["is_sample"],
        ordinal=m["ordinal"],
    )


def _problem_params(p: types_pb2.Problem) -> dict:
    return {
        "slug": p.slug,
        "title": p.title,
        "statement": p.statement,
        "difficulty": codecs.difficulty_to_db(p.difficulty),
        "time_limit_ms": p.time_limit_ms,
        "memory_limit_mb": p.memory_limit_mb,
    }


def _slug_taken(slug: str) -> Conflict:
    return Conflict(f"a problem with slug {slug!r} already exists")


class ProblemRepository:
    def __init__(self, db: Database):
        self.db = db

    # ---------- problems ----------

    def list_problems(self) -> list[types_pb2.Problem]:
        with self.db.begin() as conn:
            rows = conn.execute(text(f"SELECT {PROBLEM_COLS} FROM problems ORDER BY id"))
            return [to_problem(r) for r in rows]

    def _get_problem(self, conn: Connection, problem_id: int) -> types_pb2.Problem:
        row = conn.execute(
            text(f"SELECT {PROBLEM_COLS} FROM problems WHERE id = :id"), {"id": problem_id}
        ).first()
        if row is None:
            raise NotFound(f"problem {problem_id} not found")
        return to_problem(row)

    def get_problem(self, problem_id: int) -> types_pb2.Problem:
        with self.db.begin() as conn:
            return self._get_problem(conn, problem_id)

    def create_problem(
        self, problem: types_pb2.Problem, test_cases: list[types_pb2.TestCase]
    ) -> tuple[types_pb2.Problem, list[types_pb2.TestCase]]:
        """Problem + test cases in one transaction; test case ordinals are 1..n in list order
        (their id, problem_id and ordinal fields are ignored)."""
        try:
            with self.db.begin() as conn:
                created = to_problem(
                    conn.execute(
                        text(
                            "INSERT INTO problems (slug, title, statement, difficulty, time_limit_ms,"
                            " memory_limit_mb) VALUES (:slug, :title, :statement, :difficulty,"
                            f" :time_limit_ms, :memory_limit_mb) RETURNING {PROBLEM_COLS}"
                        ),
                        _problem_params(problem),
                    ).one()
                )
                cases = [
                    to_test_case(
                        conn.execute(
                            text(
                                "INSERT INTO test_cases (problem_id, input, expected_output, is_sample, ordinal)"
                                " VALUES (:problem_id, :input, :expected_output, :is_sample, :ordinal)"
                                f" RETURNING {TEST_CASE_COLS}"
                            ),
                            {
                                "problem_id": created.id,
                                "input": tc.input,
                                "expected_output": tc.expected_output,
                                "is_sample": tc.is_sample,
                                "ordinal": i,
                            },
                        ).one()
                    )
                    for i, tc in enumerate(test_cases, start=1)
                ]
                return created, cases
        except Conflict as err:
            raise _slug_taken(problem.slug) from err

    def update_problem(self, problem: types_pb2.Problem) -> types_pb2.Problem:
        """Replaces slug, title, statement, difficulty and limits of problem.id."""
        try:
            with self.db.begin() as conn:
                row = conn.execute(
                    text(
                        "UPDATE problems SET slug = :slug, title = :title, statement = :statement,"
                        " difficulty = :difficulty, time_limit_ms = :time_limit_ms,"
                        f" memory_limit_mb = :memory_limit_mb WHERE id = :id RETURNING {PROBLEM_COLS}"
                    ),
                    {"id": problem.id, **_problem_params(problem)},
                ).first()
        except Conflict as err:
            raise _slug_taken(problem.slug) from err
        if row is None:
            raise NotFound(f"problem {problem.id} not found")
        return to_problem(row)

    def delete_problem(self, problem_id: int) -> None:
        """Cascades to test cases and submissions."""
        with self.db.begin() as conn:
            res = conn.execute(text("DELETE FROM problems WHERE id = :id"), {"id": problem_id})
        if res.rowcount == 0:
            raise NotFound(f"problem {problem_id} not found")

    # ---------- test cases ----------

    def list_test_cases(self, problem_id: int, samples_only: bool = False) -> list[types_pb2.TestCase]:
        """Ordered by ordinal. NotFound if the problem does not exist."""
        with self.db.begin() as conn:
            self._get_problem(conn, problem_id)
            rows = conn.execute(
                text(
                    f"SELECT {TEST_CASE_COLS} FROM test_cases"
                    " WHERE problem_id = :pid AND (NOT :samples_only OR is_sample) ORDER BY ordinal, id"
                ),
                {"pid": problem_id, "samples_only": samples_only},
            )
            return [to_test_case(r) for r in rows]

    def create_test_case(self, test_case: types_pb2.TestCase) -> types_pb2.TestCase:
        """Appends a test case with ordinal = max + 1. The problem row is locked (FOR NO KEY UPDATE,
        which does not block submission inserts) so concurrent appends get distinct ordinals."""
        with self.db.begin() as conn:
            locked = conn.execute(
                text("SELECT id FROM problems WHERE id = :pid FOR NO KEY UPDATE"),
                {"pid": test_case.problem_id},
            ).first()
            if locked is None:
                raise NotFound(f"problem {test_case.problem_id} not found")
            row = conn.execute(
                text(
                    "INSERT INTO test_cases (problem_id, input, expected_output, is_sample, ordinal)"
                    " SELECT :pid, :input, :expected_output, :is_sample, COALESCE(MAX(ordinal), 0) + 1"
                    f" FROM test_cases WHERE problem_id = :pid RETURNING {TEST_CASE_COLS}"
                ),
                {
                    "pid": test_case.problem_id,
                    "input": test_case.input,
                    "expected_output": test_case.expected_output,
                    "is_sample": test_case.is_sample,
                },
            ).one()
            return to_test_case(row)

    def delete_test_case(self, problem_id: int, test_case_id: int) -> None:
        with self.db.begin() as conn:
            res = conn.execute(
                text("DELETE FROM test_cases WHERE id = :id AND problem_id = :pid"),
                {"id": test_case_id, "pid": problem_id},
            )
        if res.rowcount == 0:
            raise NotFound(f"test case {test_case_id} of problem {problem_id} not found")
