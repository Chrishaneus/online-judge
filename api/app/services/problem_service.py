"""Problems and test cases (public views and admin operations)."""

from app.gen.oj.v1 import judge_pb2, types_pb2

from . import validation
from .ports import Problems


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
    """Only sample tests are exposed; hidden tests never leave the api."""
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
    def __init__(self, problems: Problems):
        self.problems = problems

    def list_problem_summaries(
        self, _: judge_pb2.ListProblemSummariesRequest
    ) -> judge_pb2.ListProblemSummariesResponse:
        return judge_pb2.ListProblemSummariesResponse(
            problems=[to_summary(p) for p in self.problems.list_problems()]
        )

    def get_problem_detail(
        self, req: judge_pb2.GetProblemDetailRequest
    ) -> judge_pb2.GetProblemDetailResponse:
        pid = validation.require_id(req.id)
        problem = self.problems.get_problem(pid)
        samples = self.problems.list_test_cases(pid, samples_only=True)
        return judge_pb2.GetProblemDetailResponse(problem=to_detail(problem, samples))

    def add_problem(self, req: judge_pb2.AddProblemRequest) -> judge_pb2.AddProblemResponse:
        problem = validation.problem(
            req.slug, req.title, req.statement, req.difficulty, req.time_limit_ms, req.memory_limit_mb
        )
        test_cases = validation.test_cases(req.test_cases)
        created, created_cases = self.problems.create_problem(problem, test_cases)
        return judge_pb2.AddProblemResponse(problem=to_detail(created, created_cases))

    def edit_problem(self, req: judge_pb2.EditProblemRequest) -> judge_pb2.EditProblemResponse:
        problem = validation.problem(
            req.slug, req.title, req.statement, req.difficulty, req.time_limit_ms, req.memory_limit_mb
        )
        problem.id = validation.require_id(req.id)
        return judge_pb2.EditProblemResponse(problem=to_summary(self.problems.update_problem(problem)))

    def remove_problem(self, req: judge_pb2.RemoveProblemRequest) -> judge_pb2.RemoveProblemResponse:
        self.problems.delete_problem(validation.require_id(req.id))
        return judge_pb2.RemoveProblemResponse()

    def list_problem_test_cases(
        self, req: judge_pb2.ListProblemTestCasesRequest
    ) -> judge_pb2.ListProblemTestCasesResponse:
        pid = validation.require_id(req.problem_id, "problem_id")
        # NotFound for an unknown problem rather than an empty list.
        return judge_pb2.ListProblemTestCasesResponse(test_cases=self.problems.list_test_cases(pid))

    def add_test_case(self, req: judge_pb2.AddTestCaseRequest) -> judge_pb2.AddTestCaseResponse:
        test_case = validation.test_case(req.test_case)
        test_case.problem_id = validation.require_id(req.problem_id, "problem_id")
        return judge_pb2.AddTestCaseResponse(test_case=self.problems.create_test_case(test_case))

    def remove_test_case(self, req: judge_pb2.RemoveTestCaseRequest) -> judge_pb2.RemoveTestCaseResponse:
        self.problems.delete_test_case(
            validation.require_id(req.problem_id, "problem_id"), validation.require_id(req.id)
        )
        return judge_pb2.RemoveTestCaseResponse()
