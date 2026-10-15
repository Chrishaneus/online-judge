"""dao's DaoService over grpc.aio. Translates gRPC status codes into app.errors."""

import logging
from collections.abc import Awaitable, Callable

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

from app.errors import AlreadyExists, AppError, NotFound, PreconditionFailed, Unavailable, ValidationError
from app.gen.oj.v1 import dao_pb2, dao_pb2_grpc, types_pb2

log = logging.getLogger(__name__)

MAX_MESSAGE_BYTES = 64 * 1024 * 1024
CHANNEL_OPTIONS = [
    ("grpc.max_send_message_length", MAX_MESSAGE_BYTES),
    ("grpc.max_receive_message_length", MAX_MESSAGE_BYTES),
]

_ERRORS: dict[grpc.StatusCode, type[AppError]] = {
    grpc.StatusCode.NOT_FOUND: NotFound,
    grpc.StatusCode.ALREADY_EXISTS: AlreadyExists,
    grpc.StatusCode.FAILED_PRECONDITION: PreconditionFailed,
    grpc.StatusCode.INVALID_ARGUMENT: ValidationError,
    grpc.StatusCode.UNAVAILABLE: Unavailable,
    grpc.StatusCode.DEADLINE_EXCEEDED: Unavailable,
}


def translate_rpc_error(err: grpc.RpcError) -> AppError:
    code = err.code() if hasattr(err, "code") else grpc.StatusCode.UNKNOWN
    details = (err.details() if hasattr(err, "details") else None) or code.name.lower()
    cls = _ERRORS.get(code, AppError)
    if cls is Unavailable:
        return Unavailable(f"dao unavailable: {details}")
    if cls is AppError:
        return AppError(f"dao error {code.name}: {details}")
    return cls(details)


class DaoRepository:
    """Thin async wrapper around DaoServiceStub. Takes and returns proto messages."""

    def __init__(self, addr: str, timeout_s: float = 10.0):
        self.addr = addr
        self.timeout_s = timeout_s
        self._channel: grpc.aio.Channel | None = None

    def _ensure_channel(self) -> None:
        # Created lazily so the channel binds to the running event loop.
        if self._channel is None:
            self._channel = grpc.aio.insecure_channel(self.addr, options=CHANNEL_OPTIONS)
            self._stub = dao_pb2_grpc.DaoServiceStub(self._channel)
            self._health = health_pb2_grpc.HealthStub(self._channel)

    @property
    def stub(self) -> dao_pb2_grpc.DaoServiceStub:
        self._ensure_channel()
        return self._stub

    @property
    def health(self) -> health_pb2_grpc.HealthStub:
        self._ensure_channel()
        return self._health

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None

    async def _call[R](self, method: Callable[..., Awaitable[R]], request) -> R:
        try:
            return await method(request, timeout=self.timeout_s)
        except grpc.RpcError as err:
            raise translate_rpc_error(err) from err

    async def ping(self) -> None:
        """Raises Unavailable unless dao's health service reports SERVING."""
        res = await self._call(self.health.Check, health_pb2.HealthCheckRequest(service=""))
        if res.status != health_pb2.HealthCheckResponse.SERVING:
            raise Unavailable(f"dao is {health_pb2.HealthCheckResponse.ServingStatus.Name(res.status)}")

    # ---------- problems ----------

    async def list_problems(self) -> list[types_pb2.Problem]:
        res = await self._call(self.stub.ListProblems, dao_pb2.ListProblemsRequest())
        return list(res.problems)

    async def get_problem(self, problem_id: int) -> types_pb2.Problem:
        res = await self._call(self.stub.GetProblem, dao_pb2.GetProblemRequest(id=problem_id))
        return res.problem

    async def create_problem(
        self, problem: types_pb2.Problem, test_cases: list[types_pb2.TestCase]
    ) -> tuple[types_pb2.Problem, list[types_pb2.TestCase]]:
        req = dao_pb2.CreateProblemRequest(problem=problem, test_cases=test_cases)
        res = await self._call(self.stub.CreateProblem, req)
        return res.problem, list(res.test_cases)

    async def update_problem(self, problem: types_pb2.Problem) -> types_pb2.Problem:
        res = await self._call(self.stub.UpdateProblem, dao_pb2.UpdateProblemRequest(problem=problem))
        return res.problem

    async def delete_problem(self, problem_id: int) -> None:
        await self._call(self.stub.DeleteProblem, dao_pb2.DeleteProblemRequest(id=problem_id))

    # ---------- test cases ----------

    async def list_test_cases(self, problem_id: int, samples_only: bool = False) -> list[types_pb2.TestCase]:
        req = dao_pb2.ListTestCasesRequest(problem_id=problem_id, samples_only=samples_only)
        res = await self._call(self.stub.ListTestCases, req)
        return list(res.test_cases)

    async def create_test_case(self, test_case: types_pb2.TestCase) -> types_pb2.TestCase:
        res = await self._call(self.stub.CreateTestCase, dao_pb2.CreateTestCaseRequest(test_case=test_case))
        return res.test_case

    async def delete_test_case(self, problem_id: int, test_case_id: int) -> None:
        req = dao_pb2.DeleteTestCaseRequest(problem_id=problem_id, id=test_case_id)
        await self._call(self.stub.DeleteTestCase, req)

    # ---------- submissions ----------

    async def create_submission(self, submission: types_pb2.Submission) -> types_pb2.Submission:
        req = dao_pb2.CreateSubmissionRequest(submission=submission)
        res = await self._call(self.stub.CreateSubmission, req)
        return res.submission

    async def get_submission(self, submission_id: int) -> types_pb2.Submission:
        res = await self._call(self.stub.GetSubmission, dao_pb2.GetSubmissionRequest(id=submission_id))
        return res.submission

    async def list_submissions(self, req: dao_pb2.ListSubmissionsRequest) -> list[types_pb2.Submission]:
        res = await self._call(self.stub.ListSubmissions, req)
        return list(res.submissions)

    async def update_submission(self, req: dao_pb2.UpdateSubmissionRequest) -> types_pb2.Submission:
        res = await self._call(self.stub.UpdateSubmission, req)
        return res.submission
