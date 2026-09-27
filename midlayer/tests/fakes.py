"""In-memory fakes of the repositories (DaoRepository, JobQueue). Mimic oj-dao's semantics incl. CAS."""

from google.protobuf.timestamp_pb2 import Timestamp

from app.errors import AlreadyExists, NotFound, PreconditionFailed, Unavailable
from app.gen.oj.v1 import dao_pb2, runner_pb2, types_pb2

UPDATABLE = ("status", "verdict", "passed", "total", "time_ms", "message")


class FakeDao:
    def __init__(self):
        self.problems: dict[int, types_pb2.Problem] = {}
        self.test_cases: dict[int, types_pb2.TestCase] = {}
        self.submissions: dict[int, types_pb2.Submission] = {}
        self.updates: list[dao_pb2.UpdateSubmissionRequest] = []
        self.list_requests: list[dao_pb2.ListSubmissionsRequest] = []
        self.down = False
        self._next = 0

    def _id(self) -> int:
        self._next += 1
        return self._next

    def _check(self):
        if self.down:
            raise Unavailable("oj-dao unavailable: fake is down")

    async def close(self):
        pass

    async def ping(self):
        self._check()

    # ---------- problems ----------

    async def list_problems(self):
        self._check()
        return [self.problems[k] for k in sorted(self.problems)]

    async def get_problem(self, problem_id):
        self._check()
        if problem_id not in self.problems:
            raise NotFound(f"problem {problem_id} not found")
        return self.problems[problem_id]

    async def create_problem(self, problem, test_cases):
        self._check()
        if any(p.slug == problem.slug for p in self.problems.values()):
            raise AlreadyExists(f"slug {problem.slug!r} already exists")
        p = types_pb2.Problem()
        p.CopyFrom(problem)
        p.id = self._id()
        self.problems[p.id] = p
        created = []
        for i, tc in enumerate(test_cases, start=1):
            t = types_pb2.TestCase()
            t.CopyFrom(tc)
            t.id, t.problem_id, t.ordinal = self._id(), p.id, i
            self.test_cases[t.id] = t
            created.append(t)
        return p, created

    async def update_problem(self, problem):
        await self.get_problem(problem.id)
        p = types_pb2.Problem()
        p.CopyFrom(problem)
        self.problems[p.id] = p
        return p

    async def delete_problem(self, problem_id):
        await self.get_problem(problem_id)
        del self.problems[problem_id]
        self.test_cases = {k: t for k, t in self.test_cases.items() if t.problem_id != problem_id}
        self.submissions = {k: s for k, s in self.submissions.items() if s.problem_id != problem_id}

    # ---------- test cases ----------

    async def list_test_cases(self, problem_id, samples_only=False):
        self._check()
        cases = [t for t in self.test_cases.values() if t.problem_id == problem_id]
        if samples_only:
            cases = [t for t in cases if t.is_sample]
        return sorted(cases, key=lambda t: t.ordinal)

    async def create_test_case(self, test_case):
        await self.get_problem(test_case.problem_id)
        t = types_pb2.TestCase()
        t.CopyFrom(test_case)
        t.id = self._id()
        t.ordinal = 1 + max((x.ordinal for x in await self.list_test_cases(t.problem_id)), default=0)
        self.test_cases[t.id] = t
        return t

    async def delete_test_case(self, problem_id, test_case_id):
        self._check()
        t = self.test_cases.get(test_case_id)
        if t is None or t.problem_id != problem_id:
            raise NotFound("test case not found")
        del self.test_cases[test_case_id]

    # ---------- submissions ----------

    async def create_submission(self, submission):
        await self.get_problem(submission.problem_id)
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

    async def get_submission(self, submission_id):
        self._check()
        if submission_id not in self.submissions:
            raise NotFound(f"submission {submission_id} not found")
        return self.submissions[submission_id]

    async def list_submissions(self, req):
        self._check()
        self.list_requests.append(req)
        subs = sorted(self.submissions.values(), key=lambda s: -s.id)
        if req.problem_id:
            subs = [s for s in subs if s.problem_id == req.problem_id]
        if req.username:
            subs = [s for s in subs if s.username == req.username]
        if req.statuses:
            subs = [s for s in subs if s.status in req.statuses]
        if req.HasField("updated_before"):
            subs = [s for s in subs if s.update_time.ToDatetime() < req.updated_before.ToDatetime()]
        return subs[req.offset : req.offset + (req.limit or 50)]

    async def update_submission(self, req):
        s = await self.get_submission(req.id)
        if req.expected_statuses and s.status not in req.expected_statuses:
            raise PreconditionFailed(f"status is {types_pb2.SubmissionStatus.Name(s.status)}")
        self.updates.append(req)
        for name in UPDATABLE:
            if req.HasField(name):
                setattr(s, name, getattr(req, name))
        if req.HasField("results"):
            del s.results[:]
            s.results.extend(req.results.results)
        return s


class FakeQueue:
    """Stands in for app.repositories.JobQueue."""

    events_queue = "judge.events"
    dead_queue = "judge.jobs.dead"

    def __init__(self):
        self.published: list[runner_pb2.ExecuteJob] = []
        self.run_jobs: list[tuple[runner_pb2.ExecuteJob, float]] = []
        self.run_result: runner_pb2.ExecuteResult | Exception = runner_pb2.ExecuteResult()
        self.depth = 0
        self.consumers = 2
        self.down = False
        self.handlers: dict[str, object] = {}
        self.started = self.closed = False

    async def start(self):
        self.started = True

    async def close(self):
        self.closed = True

    async def consume(self, queue, handler):
        self.handlers[queue] = handler

    async def publish_submission_job(self, job):
        if self.down:
            raise Unavailable("RabbitMQ unavailable: fake is down")
        self.published.append(job)

    async def run_job(self, job, timeout_s):
        if self.down:
            raise Unavailable("RabbitMQ unavailable: fake is down")
        self.run_jobs.append((job, timeout_s))
        if isinstance(self.run_result, Exception):
            raise self.run_result
        return self.run_result

    async def queue_stats(self):
        if self.down:
            raise Unavailable("RabbitMQ unavailable: fake is down")
        return self.depth, self.consumers


async def seed_problem(dao: FakeDao, *, cases=(("1", "2", True), ("5", "10", False)), **kwargs):
    problem = types_pb2.Problem(
        slug=kwargs.get("slug", "double"),
        title="Double",
        statement="Print 2x.",
        difficulty=types_pb2.DIFFICULTY_EASY,
        time_limit_ms=kwargs.get("time_limit_ms", 1000),
        memory_limit_mb=kwargs.get("memory_limit_mb", 64),
    )
    test_cases = [types_pb2.TestCase(input=i, expected_output=o, is_sample=s) for i, o, s in cases]
    return await dao.create_problem(problem, test_cases)
