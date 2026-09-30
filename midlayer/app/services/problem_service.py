"""Problems and test cases (public views and admin operations)."""

import asyncio

from app.gen.oj.v1 import judge_pb2, types_pb2

from . import validation
from .ports import Dao


def to_summary(p: types_pb2.Problem) -> judge_pb2.ProblemSummary:
    return judge_pb2.ProblemSummary(
        id=p.id,
        slug=p.slug,
        title=p.title,
        difficulty=p.difficulty,
        time_limit_ms=p.time_limit_ms,
        memory_limit_mb=p.memory_limit_mb,
    )


def to_detail(p: types_pb2.Problem, test_cases: list[types_pb2.TestCase]) -> judge_pb2.ProblemDetail:
    """Only sample tests are exposed; hidden tests never leave the midlayer."""
    return judge_pb2.ProblemDetail(
        id=p.id,
        slug=p.slug,
        title=p.title,
        difficulty=p.difficulty,
        time_limit_ms=p.time_limit_ms,
        memory_limit_mb=p.memory_limit_mb,
        statement=p.statement,
        samples=[
            types_pb2.Sample(input=t.input, output=t.expected_output) for t in test_cases if t.is_sample
        ],
    )


class ProblemService:
    def __init__(self, dao: Dao):
        self.dao = dao

    async def list_problem_summaries(
        self, _: judge_pb2.ListProblemSummariesRequest
    ) -> judge_pb2.ListProblemSummariesResponse:
        problems = await self.dao.list_problems()
        return judge_pb2.ListProblemSummariesResponse(problems=[to_summary(p) for p in problems])

    async def get_problem_detail(
        self, req: judge_pb2.GetProblemDetailRequest
    ) -> judge_pb2.GetProblemDetailResponse:
        pid = validation.require_id(req.id)
        problem, samples = await asyncio.gather(
            self.dao.get_problem(pid), self.dao.list_test_cases(pid, samples_only=True)
        )
        return judge_pb2.GetProblemDetailResponse(problem=to_detail(problem, samples))

    async def add_problem(self, req: judge_pb2.AddProblemRequest) -> judge_pb2.AddProblemResponse:
        problem = validation.problem(
            req.slug, req.title, req.statement, req.difficulty, req.time_limit_ms, req.memory_limit_mb
        )
        test_cases = validation.test_cases(req.test_cases)
        created, created_cases = await self.dao.create_problem(problem, test_cases)
        return judge_pb2.AddProblemResponse(problem=to_detail(created, created_cases))

    async def edit_problem(self, req: judge_pb2.EditProblemRequest) -> judge_pb2.EditProblemResponse:
        problem = validation.problem(
            req.slug, req.title, req.statement, req.difficulty, req.time_limit_ms, req.memory_limit_mb
        )
        problem.id = validation.require_id(req.id)
        updated = await self.dao.update_problem(problem)
        return judge_pb2.EditProblemResponse(problem=to_summary(updated))

    async def remove_problem(self, req: judge_pb2.RemoveProblemRequest) -> judge_pb2.RemoveProblemResponse:
        await self.dao.delete_problem(validation.require_id(req.id))
        return judge_pb2.RemoveProblemResponse()

    async def list_problem_test_cases(
        self, req: judge_pb2.ListProblemTestCasesRequest
    ) -> judge_pb2.ListProblemTestCasesResponse:
        pid = validation.require_id(req.problem_id, "problem_id")
        # GetProblem first so an unknown problem is NOT_FOUND rather than an empty list.
        await self.dao.get_problem(pid)
        return judge_pb2.ListProblemTestCasesResponse(test_cases=await self.dao.list_test_cases(pid))

    async def add_test_case(self, req: judge_pb2.AddTestCaseRequest) -> judge_pb2.AddTestCaseResponse:
        test_case = validation.test_case(req.test_case)
        test_case.problem_id = validation.require_id(req.problem_id, "problem_id")
        return judge_pb2.AddTestCaseResponse(test_case=await self.dao.create_test_case(test_case))

    async def remove_test_case(
        self, req: judge_pb2.RemoveTestCaseRequest
    ) -> judge_pb2.RemoveTestCaseResponse:
        await self.dao.delete_test_case(
            validation.require_id(req.problem_id, "problem_id"), validation.require_id(req.id)
        )
        return judge_pb2.RemoveTestCaseResponse()
