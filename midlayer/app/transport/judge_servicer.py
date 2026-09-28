"""gRPC servicer for oj.v1.JudgeService: each RPC calls one service method; app.errors become status codes."""

import logging
from collections.abc import Awaitable, Callable

import grpc

from app import errors
from app.gen.oj.v1 import judge_pb2_grpc
from app.services import Services

log = logging.getLogger(__name__)

STATUS_CODES: dict[type[errors.AppError], grpc.StatusCode] = {
    errors.ValidationError: grpc.StatusCode.INVALID_ARGUMENT,
    errors.NotFound: grpc.StatusCode.NOT_FOUND,
    errors.AlreadyExists: grpc.StatusCode.ALREADY_EXISTS,
    errors.PreconditionFailed: grpc.StatusCode.FAILED_PRECONDITION,
    errors.ResourceExhausted: grpc.StatusCode.RESOURCE_EXHAUSTED,
    errors.DeadlineExceeded: grpc.StatusCode.DEADLINE_EXCEEDED,
    errors.Unavailable: grpc.StatusCode.UNAVAILABLE,
}


def status_code_for(err: errors.AppError) -> grpc.StatusCode:
    for cls in type(err).__mro__:
        if cls in STATUS_CODES:
            return STATUS_CODES[cls]
    return grpc.StatusCode.INTERNAL


async def _handle[Req, Res](
    call: Callable[[Req], Awaitable[Res]], request: Req, context: grpc.aio.ServicerContext
) -> Res:
    try:
        return await call(request)
    except errors.AppError as err:
        code = status_code_for(err)
        if code in (grpc.StatusCode.INTERNAL, grpc.StatusCode.UNAVAILABLE):
            log.error("%s: %s", code.name, err.message)
        message = err.message if code != grpc.StatusCode.INTERNAL else "internal error"
        await context.abort(code, message)
    except Exception:
        log.exception("unhandled error")
        await context.abort(grpc.StatusCode.INTERNAL, "internal error")
    raise AssertionError("unreachable")  # context.abort always raises


class JudgeServicer(judge_pb2_grpc.JudgeServiceServicer):
    def __init__(self, services: Services):
        self.s = services

    async def GetStatus(self, request, context):
        return await _handle(self.s.status.get_status, request, context)

    async def ListLanguages(self, request, context):
        return await _handle(self.s.languages.list_languages, request, context)

    async def ListProblemSummaries(self, request, context):
        return await _handle(self.s.problems.list_problem_summaries, request, context)

    async def GetProblemDetail(self, request, context):
        return await _handle(self.s.problems.get_problem_detail, request, context)

    async def Submit(self, request, context):
        return await _handle(self.s.submissions.submit, request, context)

    async def ListSubmissionSummaries(self, request, context):
        return await _handle(self.s.submissions.list_submission_summaries, request, context)

    async def GetSubmissionDetail(self, request, context):
        return await _handle(self.s.submissions.get_submission_detail, request, context)

    async def RunCode(self, request, context):
        return await _handle(self.s.runs.run_code, request, context)

    async def AddProblem(self, request, context):
        return await _handle(self.s.problems.add_problem, request, context)

    async def EditProblem(self, request, context):
        return await _handle(self.s.problems.edit_problem, request, context)

    async def RemoveProblem(self, request, context):
        return await _handle(self.s.problems.remove_problem, request, context)

    async def ListProblemTestCases(self, request, context):
        return await _handle(self.s.problems.list_problem_test_cases, request, context)

    async def AddTestCase(self, request, context):
        return await _handle(self.s.problems.add_test_case, request, context)

    async def RemoveTestCase(self, request, context):
        return await _handle(self.s.problems.remove_test_case, request, context)
