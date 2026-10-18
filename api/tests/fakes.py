"""In-memory fakes of the repositories. FakeStore mimics the Postgres repositories' semantics (incl. the
compare-and-set of update_submission); FakeQueue stands in for JobQueue."""

import threading
from datetime import UTC, datetime

from google.protobuf.timestamp_pb2 import Timestamp

from app.errors import Conflict, NotFound, PreconditionFailed, Unavailable
from app.gen.oj.v1 import runner_pb2, types_pb2
from app.repositories import Repositories
from app.repositories.records import SubmissionFilter, SubmissionUpdate

UPDATABLE = ("status", "verdict", "passed", "total", "time_ms", "message")


class FakeStore:
    """Implements Database (ping), ProblemRepository and SubmissionRepository."""

    def __init__(self):
        self.problems: dict[int, types_pb2.Problem] = {}
        self.test_cases: dict[int, types_pb2.TestCase] = {}
        self.submissions: dict[int, types_pb2.Submission] = {}
        self.updates: list[SubmissionUpdate] = []
        self.list_requests: list[SubmissionFilter] = []
        self.down = False
        self._next = 0
        self._lock = threading.RLock()  # the worker thread and the test thread share it

    def _id(self) -> int:
        self._next += 1
        return self._next

    def _check(self):
        if self.down:
            raise Unavailable("database unavailable: fake is down")

    def ping(self):
        self._check()

    # ---------- problems ----------

    def list_problems(self):
        self._check()
        return [self.problems[k] for k in sorted(self.problems)]

    def get_problem(self, problem_id):
        self._check()
        if problem_id not in self.problems:
            raise NotFound(f"problem {problem_id} not found")
        return self.problems[problem_id]

    def create_problem(self, problem, test_cases):
        self._check()
        if any(p.slug == problem.slug for p in self.problems.values()):
            raise Conflict(f"a problem with slug {problem.slug!r} already exists")
        p = types_pb2.Problem()
        p.CopyFrom(problem)
        p.id = self._id()
        p.create_time.FromSeconds(1_700_000_000)
        self.problems[p.id] = p
        created = []
        for i, tc in enumerate(test_cases, start=1):
            t = types_pb2.TestCase()
            t.CopyFrom(tc)
            t.id, t.problem_id, t.ordinal = self._id(), p.id, i
            self.test_cases[t.id] = t
            created.append(t)
        return p, created

    def update_problem(self, problem):
        old = self.get_problem(problem.id)
        if any(p.slug == problem.slug and p.id != problem.id for p in self.problems.values()):
            raise Conflict(f"a problem with slug {problem.slug!r} already exists")
        p = types_pb2.Problem()
        p.CopyFrom(problem)
        p.create_time.CopyFrom(old.create_time)
        self.problems[p.id] = p
        return p

    def delete_problem(self, problem_id):
        self.get_problem(problem_id)
        del self.problems[problem_id]
        self.test_cases = {k: t for k, t in self.test_cases.items() if t.problem_id != problem_id}
        self.submissions = {k: s for k, s in self.submissions.items() if s.problem_id != problem_id}

    # ---------- test cases ----------

    def list_test_cases(self, problem_id, samples_only=False):
        self.get_problem(problem_id)
        cases = [t for t in self.test_cases.values() if t.problem_id == problem_id]
        if samples_only:
            cases = [t for t in cases if t.is_sample]
        return sorted(cases, key=lambda t: t.ordinal)

    def create_test_case(self, test_case):
        cases = self.list_test_cases(test_case.problem_id)
        t = types_pb2.TestCase()
        t.CopyFrom(test_case)
        t.id = self._id()
        t.ordinal = 1 + max((x.ordinal for x in cases), default=0)
        self.test_cases[t.id] = t
        return t

    def delete_test_case(self, problem_id, test_case_id):
        self._check()
        t = self.test_cases.get(test_case_id)
        if t is None or t.problem_id != problem_id:
            raise NotFound("test case not found")
        del self.test_cases[test_case_id]

    # ---------- submissions ----------

    def create_submission(self, submission):
        self.get_problem(submission.problem_id)
        with self._lock:
            s = types_pb2.Submission(
                id=self._id(),
                problem_id=submission.problem_id,
                username=submission.username,
                language=submission.language,
                source=submission.source,
                status=types_pb2.SUBMISSION_STATUS_PENDING,
                create_time=Timestamp(seconds=1_700_000_000),
                update_time=Timestamp(seconds=1_700_000_000),
            )
            self.submissions[s.id] = s
            return s

    def get_submission(self, submission_id):
        self._check()
        if submission_id not in self.submissions:
            raise NotFound(f"submission {submission_id} not found")
        return self.submissions[submission_id]

    def list_submissions(self, f: SubmissionFilter):
        self._check()
        self.list_requests.append(f)
        subs = sorted(self.submissions.values(), key=lambda s: -s.id)
        if f.problem_id:
            subs = [s for s in subs if s.problem_id == f.problem_id]
        if f.username:
            subs = [s for s in subs if s.username == f.username]
        if f.statuses:
            subs = [s for s in subs if s.status in f.statuses]
        if f.updated_before is not None:
            subs = [s for s in subs if s.update_time.ToDatetime(tzinfo=UTC) < f.updated_before]
        return subs[f.offset : f.offset + (f.limit or 50)]

    def update_submission(self, u: SubmissionUpdate):
        with self._lock:
            s = self.get_submission(u.id)
            if u.expected_statuses and s.status not in u.expected_statuses:
                raise PreconditionFailed(f"status is {types_pb2.SubmissionStatus.Name(s.status)}")
            self.updates.append(u)
            for name in UPDATABLE:
                if getattr(u, name) is not None:
                    setattr(s, name, getattr(u, name))
            if u.results is not None:
                del s.results[:]
                s.results.extend(u.results)
            s.update_time.FromDatetime(datetime.now(UTC))
            return s


class FakeQueue:
    """Stands in for app.repositories.JobQueue."""

    def __init__(self):
        self.published: list[runner_pb2.ExecuteJob] = []
        self.run_jobs: list[tuple[runner_pb2.ExecuteJob, float]] = []
        self.run_result: runner_pb2.ExecuteResult | Exception = runner_pb2.ExecuteResult()
        self.depth = 0
        self.consumers = 2
        self.down = False

    def _check(self):
        if self.down:
            raise Unavailable("RabbitMQ unavailable: fake is down")

    def connect(self):
        self._check()

    def close(self):
        pass

    def publish_submission_job(self, job):
        self._check()
        self.published.append(job)

    def run_job(self, job, timeout_s):
        self._check()
        self.run_jobs.append((job, timeout_s))
        if isinstance(self.run_result, Exception):
            raise self.run_result
        return self.run_result

    def queue_stats(self):
        self._check()
        return self.depth, self.consumers


def fake_repositories(store: FakeStore, queue) -> Repositories:
    return Repositories(database=store, problems=store, submissions=store, queue=queue)


def seed_problem(store, *, cases=(("1", "2", True), ("5", "10", False)), **kwargs):
    problem = types_pb2.Problem(
        slug=kwargs.get("slug", "double"),
        title="Double",
        statement="Print 2x.",
        difficulty=types_pb2.DIFFICULTY_EASY,
        time_limit_ms=kwargs.get("time_limit_ms", 1000),
        memory_limit_mb=kwargs.get("memory_limit_mb", 64),
    )
    test_cases = [types_pb2.TestCase(input=i, expected_output=o, is_sample=s) for i, o, s in cases]
    return store.create_problem(problem, test_cases)
