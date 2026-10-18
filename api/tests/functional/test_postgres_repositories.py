"""Problem/Submission repositories and migrations against a real Postgres (ported from dao's store tests).

Set TEST_DATABASE_URL to a THROWAWAY database (its tables are truncated and dropped), e.g.
postgresql+psycopg://oj:oj@127.0.0.1:55432/oj_test
"""

import json
import os
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.errors import Conflict, NotFound, PreconditionFailed, Unavailable, ValidationError
from app.gen.oj.v1 import types_pb2 as T
from app.repositories import Database, ProblemRepository, SubmissionRepository
from app.repositories.database import MIGRATION_LOCK_ID, MIGRATIONS_DIR
from app.repositories.records import SubmissionFilter, SubmissionUpdate
from app.repositories.submission_repository import DEFAULT_LIST_LIMIT

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

VERSIONS = ["001_init.sql", "002_seed.sql", "003_submissions_status_updated_idx.sql"]


@pytest.fixture(scope="module")
def db():
    database = Database(URL, pool_size=25)
    database.migrate()
    yield database
    database.dispose()


@pytest.fixture
def clean(db):
    with db.begin() as conn:
        conn.execute(text("TRUNCATE problems, test_cases, submissions RESTART IDENTITY CASCADE"))
    return db


@pytest.fixture
def problems(clean):
    return ProblemRepository(clean)


@pytest.fixture
def submissions(clean):
    return SubmissionRepository(clean)


def make_problem(problems, slug, *cases):
    return problems.create_problem(
        T.Problem(
            slug=slug,
            title="T",
            statement="S",
            difficulty=T.DIFFICULTY_EASY,
            time_limit_ms=1000,
            memory_limit_mb=64,
        ),
        list(cases),
    )


def make_submission(submissions, problem_id, user):
    return submissions.create_submission(
        T.Submission(problem_id=problem_id, username=user, language=T.LANGUAGE_PYTHON, source="print(1)")
    )


def ts(msg) -> datetime:
    return msg.ToDatetime(tzinfo=UTC)


# ---------- problems and test cases ----------


def test_create_problem_with_test_cases(problems):
    p, tcs = make_problem(
        problems,
        "sum",
        T.TestCase(input="1 2", expected_output="3", is_sample=True, ordinal=7, problem_id=99),
        T.TestCase(input="2 2", expected_output="4"),
        T.TestCase(input="", expected_output=""),
    )
    assert p.id > 0 and p.HasField("create_time")
    assert (p.difficulty, p.time_limit_ms, p.memory_limit_mb) == (T.DIFFICULTY_EASY, 1000, 64)
    assert [(tc.ordinal, tc.problem_id) for tc in tcs] == [(1, p.id), (2, p.id), (3, p.id)]
    assert all(tc.id > 0 for tc in tcs)
    listed = problems.list_test_cases(p.id)
    assert len(listed) == 3 and listed[0].input == "1 2" and listed[0].is_sample
    assert len(problems.list_test_cases(p.id, samples_only=True)) == 1

    with pytest.raises(Conflict, match="sum"):
        make_problem(problems, "sum", T.TestCase(input="x"))
    assert len(problems.list_test_cases(p.id)) == 3  # the failed create added nothing


def test_problem_update_delete_cascade(problems, submissions):
    p, _ = make_problem(problems, "a", T.TestCase(input="1"))
    make_problem(problems, "b")
    sub = make_submission(submissions, p.id, "alice")

    p.title, p.difficulty, p.time_limit_ms = "New", T.DIFFICULTY_HARD, 500
    upd = problems.update_problem(p)
    assert (upd.title, upd.difficulty, upd.time_limit_ms) == ("New", T.DIFFICULTY_HARD, 500)
    assert upd.create_time == p.create_time
    p.slug = "b"
    with pytest.raises(Conflict):
        problems.update_problem(p)
    with pytest.raises(NotFound):
        problems.update_problem(T.Problem(id=999, slug="zz", difficulty=T.DIFFICULTY_EASY))

    problems.delete_problem(p.id)
    with pytest.raises(NotFound):
        problems.delete_problem(p.id)
    with pytest.raises(NotFound):
        submissions.get_submission(sub.id)  # cascaded
    with pytest.raises(NotFound):
        problems.list_test_cases(p.id)
    with pytest.raises(NotFound):
        problems.get_problem(p.id)
    assert [x.slug for x in problems.list_problems()] == ["b"]


def test_difficulty_must_be_storable(problems):
    with pytest.raises(ValidationError, match="difficulty"):
        problems.create_problem(T.Problem(slug="x", title="x"), [])


def test_create_test_case_ordinals(problems):
    p, _ = make_problem(problems, "tc", T.TestCase(input="1"), T.TestCase(input="2"))
    tc = problems.create_test_case(T.TestCase(problem_id=p.id, input="3", ordinal=42))
    assert (tc.ordinal, tc.problem_id) == (3, p.id)
    problems.delete_test_case(p.id, tc.id)
    with pytest.raises(NotFound):
        problems.delete_test_case(p.id, tc.id)
    assert problems.create_test_case(T.TestCase(problem_id=p.id, input="3")).ordinal == 3
    with pytest.raises(NotFound):
        problems.create_test_case(T.TestCase(problem_id=999))
    other, _ = make_problem(problems, "other")
    with pytest.raises(NotFound):
        problems.delete_test_case(other.id, tc.id)  # wrong problem


def test_concurrent_test_case_ordinals_are_distinct(problems):
    p, _ = make_problem(problems, "conc")
    ordinals, errors = [], []

    def add():
        try:
            ordinals.append(problems.create_test_case(T.TestCase(problem_id=p.id, input="x")).ordinal)
        except Exception as exc:  # noqa: BLE001 - collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=add) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert sorted(ordinals) == list(range(1, 21))


def test_create_problem_is_atomic(problems):
    # PostgreSQL rejects NUL bytes in TEXT, so the second insert fails.
    with pytest.raises(Exception):  # noqa: B017 - any driver error; what matters is the rollback
        problems.create_problem(
            T.Problem(slug="atomic", title="A", difficulty=T.DIFFICULTY_EASY),
            [T.TestCase(input="ok"), T.TestCase(input="bad\x00")],
        )
    assert problems.list_problems() == []
    with problems.db.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM test_cases")).scalar_one() == 0


# ---------- submissions ----------


def test_create_submission_defaults(problems, submissions):
    p, _ = make_problem(problems, "p")
    sub = submissions.create_submission(
        T.Submission(
            problem_id=p.id,
            username="bob",
            language=T.LANGUAGE_CPP,
            source="int main(){}",
            status=T.SUBMISSION_STATUS_FINISHED,
            verdict=T.VERDICT_ACCEPTED,
            passed=3,
            results=[T.TestResult(test=1)],
        )
    )
    assert (sub.status, sub.verdict, sub.passed, list(sub.results)) == (
        T.SUBMISSION_STATUS_PENDING,
        T.VERDICT_UNSPECIFIED,
        0,
        [],
    )
    assert sub.HasField("create_time") and sub.create_time == sub.update_time
    got = submissions.get_submission(sub.id)
    assert (got.source, got.language, got.username) == ("int main(){}", T.LANGUAGE_CPP, "bob")
    with pytest.raises(NotFound, match="problem 999"):
        submissions.create_submission(T.Submission(problem_id=999, language=T.LANGUAGE_C, source="x"))
    with pytest.raises(NotFound):
        submissions.get_submission(999)


def test_list_submissions_filters(problems, submissions):
    p1, _ = make_problem(problems, "p1")
    p2, _ = make_problem(problems, "p2")
    a = make_submission(submissions, p1.id, "alice")
    time.sleep(0.002)
    b = make_submission(submissions, p1.id, "bob")
    time.sleep(0.002)
    c = make_submission(submissions, p2.id, "alice")
    submissions.update_submission(SubmissionUpdate(id=b.id, status=T.SUBMISSION_STATUS_JUDGING))
    submissions.update_submission(SubmissionUpdate(id=c.id, status=T.SUBMISSION_STATUS_FINISHED))

    def ids(**kw):
        return [s.id for s in submissions.list_submissions(SubmissionFilter(**kw))]

    assert ids() == [c.id, b.id, a.id]  # newest first
    assert ids(problem_id=p1.id) == [b.id, a.id]
    assert ids(username="alice") == [c.id, a.id]
    assert ids(statuses=[T.SUBMISSION_STATUS_PENDING, T.SUBMISSION_STATUS_JUDGING]) == [b.id, a.id]
    assert ids(statuses=[T.SUBMISSION_STATUS_FINISHED]) == [c.id]
    assert ids(problem_id=p1.id, username="alice", statuses=[T.SUBMISSION_STATUS_PENDING]) == [a.id]
    assert ids(limit=1) == [c.id]
    assert ids(limit=1, offset=1) == [b.id]
    assert ids(offset=10) == []

    # updated_before is strict: a's update time is earlier than b's.
    a, b = submissions.get_submission(a.id), submissions.get_submission(b.id)
    assert ts(a.update_time) < ts(b.update_time)
    assert ids(updated_before=ts(b.update_time)) == [a.id]
    assert ids(updated_before=datetime.now(UTC) + timedelta(hours=1)) == [c.id, b.id, a.id]
    # Complete rows (the service strips them for the public list).
    assert submissions.list_submissions(SubmissionFilter())[0].source == "print(1)"


def test_list_submissions_default_limit(problems, submissions):
    p, _ = make_problem(problems, "many")
    for _ in range(DEFAULT_LIST_LIMIT + 5):
        make_submission(submissions, p.id, "u")
    assert len(submissions.list_submissions(SubmissionFilter())) == DEFAULT_LIST_LIMIT
    assert len(submissions.list_submissions(SubmissionFilter(limit=500))) == DEFAULT_LIST_LIMIT + 5


def test_update_submission_partial(problems, submissions):
    p, _ = make_problem(problems, "upd")
    sub = make_submission(submissions, p.id, "alice")
    time.sleep(0.002)
    results = [
        T.TestResult(test=1, verdict=T.VERDICT_ACCEPTED, time_ms=12, memory_kb=9000, sample=True),
        T.TestResult(test=2, verdict=T.VERDICT_WRONG_ANSWER, time_ms=3, memory_kb=1),
    ]
    upd = submissions.update_submission(
        SubmissionUpdate(
            id=sub.id,
            status=T.SUBMISSION_STATUS_FINISHED,
            verdict=T.VERDICT_WRONG_ANSWER,
            passed=1,
            total=2,
            time_ms=12,
            message="Wrong Answer on test 2",
            results=results,
        )
    )
    assert (upd.status, upd.verdict, upd.passed, upd.total, upd.time_ms, upd.message) == (
        T.SUBMISSION_STATUS_FINISHED,
        T.VERDICT_WRONG_ANSWER,
        1,
        2,
        12,
        "Wrong Answer on test 2",
    )
    assert list(upd.results) == results
    assert (upd.language, upd.source) == (T.LANGUAGE_PYTHON, "print(1)")
    assert ts(upd.update_time) > ts(sub.update_time) and upd.create_time == sub.create_time

    # Empty update: only update_time moves; results=None keeps the old ones.
    time.sleep(0.002)
    again = submissions.update_submission(SubmissionUpdate(id=sub.id))
    assert again.verdict == T.VERDICT_WRONG_ANSWER and len(again.results) == 2
    assert ts(again.update_time) > ts(upd.update_time)
    # An empty list clears them.
    assert list(submissions.update_submission(SubmissionUpdate(id=sub.id, results=[])).results) == []
    with pytest.raises(NotFound):
        submissions.update_submission(SubmissionUpdate(id=999, status=T.SUBMISSION_STATUS_JUDGING))


def test_update_submission_compare_and_set(problems, submissions):
    p, _ = make_problem(problems, "cas")
    sub = make_submission(submissions, p.id, "alice")
    got = submissions.update_submission(
        SubmissionUpdate(
            id=sub.id, status=T.SUBMISSION_STATUS_JUDGING, expected_statuses=[T.SUBMISSION_STATUS_PENDING]
        )
    )
    assert got.status == T.SUBMISSION_STATUS_JUDGING
    open_ = [T.SUBMISSION_STATUS_PENDING, T.SUBMISSION_STATUS_JUDGING]
    got = submissions.update_submission(
        SubmissionUpdate(
            id=sub.id,
            status=T.SUBMISSION_STATUS_FINISHED,
            verdict=T.VERDICT_ACCEPTED,
            expected_statuses=open_,
        )
    )
    assert got.status == T.SUBMISSION_STATUS_FINISHED
    # A late duplicate result must not overwrite the finished submission.
    with pytest.raises(PreconditionFailed):
        submissions.update_submission(
            SubmissionUpdate(
                id=sub.id,
                status=T.SUBMISSION_STATUS_FAILED,
                verdict=T.VERDICT_INTERNAL_ERROR,
                expected_statuses=open_,
            )
        )
    cur = submissions.get_submission(sub.id)
    assert (cur.status, cur.verdict, cur.update_time) == (
        T.SUBMISSION_STATUS_FINISHED,
        T.VERDICT_ACCEPTED,
        got.update_time,
    )
    with pytest.raises(NotFound):
        submissions.update_submission(
            SubmissionUpdate(id=999, expected_statuses=[T.SUBMISSION_STATUS_PENDING])
        )


def test_update_submission_cas_is_atomic(problems, submissions):
    p, _ = make_problem(problems, "race")
    sub = make_submission(submissions, p.id, "alice")
    wins, errors = [], []

    def race():
        try:
            submissions.update_submission(
                SubmissionUpdate(
                    id=sub.id,
                    status=T.SUBMISSION_STATUS_JUDGING,
                    expected_statuses=[T.SUBMISSION_STATUS_PENDING],
                )
            )
            wins.append(1)
        except PreconditionFailed:
            pass
        except Exception as exc:  # noqa: BLE001 - collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=race) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(wins) == 1


def test_results_row_format_and_legacy_rows(problems, submissions):
    p, _ = make_problem(problems, "fmt")
    sub = make_submission(submissions, p.id, "u")
    rs = [T.TestResult(test=1, verdict=T.VERDICT_ACCEPTED, time_ms=12, memory_kb=9000, sample=True)]
    submissions.update_submission(SubmissionUpdate(id=sub.id, results=rs))
    with submissions.db.begin() as conn:
        raw = conn.execute(
            text("SELECT results::text FROM submissions WHERE id = :id"), {"id": sub.id}
        ).scalar_one()
    assert json.loads(raw) == [{"test": 1, "verdict": "AC", "time_ms": 12, "memory_kb": 9000, "sample": True}]

    # Rows from older versions that don't match the format are read as empty.
    with submissions.db.begin() as conn:
        conn.execute(
            text("UPDATE submissions SET results = CAST(:r AS jsonb) WHERE id = :id"),
            {"r": '{"weird": true}', "id": sub.id},
        )
    assert list(submissions.get_submission(sub.id).results) == []
    # Unknown stored enum strings read as UNSPECIFIED instead of failing.
    with submissions.db.begin() as conn:
        conn.execute(
            text("UPDATE submissions SET language = 'cobol', verdict = 'XX' WHERE id = :id"), {"id": sub.id}
        )
    got = submissions.get_submission(sub.id)
    assert (got.language, got.verdict) == (T.LANGUAGE_UNSPECIFIED, T.VERDICT_UNSPECIFIED)


def test_unreachable_database_is_unavailable():
    down = Database("postgresql+psycopg://u:p@127.0.0.1:1/db")
    try:
        with pytest.raises(Unavailable, match="database unavailable"):
            down.ping()
        with pytest.raises(Unavailable):
            ProblemRepository(down).get_problem(1)
        with pytest.raises(Unavailable):
            down.migrate(wait_s=0)
    finally:
        down.dispose()


# ---------- migrations ----------


def drop_everything(db):
    with db.begin() as conn:
        conn.execute(
            text("DROP TABLE IF EXISTS submissions, test_cases, problems, schema_migrations CASCADE")
        )


def schema_state(db):
    with db.begin() as conn:
        versions = conn.execute(
            text("SELECT version, applied_at FROM schema_migrations ORDER BY version")
        ).all()
        slugs = conn.execute(text("SELECT slug FROM problems ORDER BY id")).scalars().all()
        indexes = (
            conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = 'submissions' ORDER BY indexname")
            )
            .scalars()
            .all()
        )
    return versions, slugs, indexes


def test_migrations_from_scratch_are_idempotent(db):
    drop_everything(db)
    try:
        assert db.migrate() == VERSIONS
        versions, slugs, indexes = schema_state(db)
        assert [v for v, _ in versions] == VERSIONS
        assert slugs == ["a-plus-b", "reverse-string", "fibonacci"]
        assert "submissions_status_updated_idx" in indexes
        assert db.migrate() == []
        assert schema_state(db) == (versions, slugs, indexes)
    finally:
        db.migrate()


def test_migrations_recognise_a_dao_migrated_database(db):
    """A production database migrated by dao (same schema_migrations table and versions) is untouched."""
    drop_everything(db)
    try:
        with db.begin() as conn:
            # Exactly what dao's migrate.go creates and records.
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    " version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
                )
            )
        for version in VERSIONS:
            with db.begin() as conn:
                conn.exec_driver_sql((MIGRATIONS_DIR / version).read_text())
                conn.execute(
                    text(
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (:v, '2025-01-01T00:00:00Z')"
                    ),
                    {"v": version},
                )
        with db.begin() as conn:  # data written by the old services
            conn.execute(text("DELETE FROM problems WHERE slug = 'fibonacci'"))
        before = schema_state(db)

        assert db.migrate() == []
        assert schema_state(db) == before
        assert before[1] == ["a-plus-b", "reverse-string"]  # the seed is not re-applied
    finally:
        db.migrate()


def test_partially_migrated_database_gets_only_the_missing_versions(db):
    drop_everything(db)
    try:
        assert db.migrate(wait_s=0) == VERSIONS
        with db.begin() as conn:
            conn.execute(text("DROP INDEX submissions_status_updated_idx"))
            conn.execute(text("DELETE FROM schema_migrations WHERE version = :v"), {"v": VERSIONS[2]})
        assert db.migrate() == [VERSIONS[2]]
        assert "submissions_status_updated_idx" in schema_state(db)[2]
    finally:
        db.migrate()


def test_concurrent_migrations_apply_each_version_once(db):
    drop_everything(db)
    results, errors = [], []

    def run():
        try:
            results.append(db.migrate())
        except Exception as exc:  # noqa: BLE001 - collected and asserted below
            errors.append(exc)

    try:
        threads = [threading.Thread(target=run) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert sorted(results, key=len) == [[], [], [], VERSIONS]
        assert schema_state(db)[1] == ["a-plus-b", "reverse-string", "fibonacci"]
    finally:
        db.migrate()


def test_migrations_use_daos_advisory_lock(db):
    """While another session holds dao's lock id, migrate waits for it."""
    drop_everything(db)
    done = threading.Event()
    with db.engine.connect() as holder:
        holder.execute(text("SELECT pg_advisory_lock(:id)"), {"id": MIGRATION_LOCK_ID})
        t = threading.Thread(target=lambda: (db.migrate(), done.set()))
        t.start()
        try:
            assert not done.wait(0.5)
        finally:
            holder.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": MIGRATION_LOCK_ID})
            holder.commit()
        t.join(10)
    assert done.is_set()
