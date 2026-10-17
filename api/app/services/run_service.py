"""Custom runs: execute code against custom input through RabbitMQ (RPC), no judging."""

import uuid

from app.errors import Unavailable, ValidationError
from app.gen.oj.v1 import judge_pb2, runner_pb2, types_pb2

from . import validation
from .ports import Problems, Queue

DEFAULT_TIME_LIMIT_MS = 2000
DEFAULT_MEMORY_LIMIT_MB = 256


def to_response(result: runner_pb2.ExecuteResult) -> judge_pb2.RunCodeResponse:
    if result.status == runner_pb2.EXECUTE_STATUS_COMPILATION_ERROR:
        return judge_pb2.RunCodeResponse(
            status=types_pb2.RUN_STATUS_COMPILATION_ERROR, compile_output=result.compile_output
        )
    if result.status == runner_pb2.EXECUTE_STATUS_REJECTED:
        raise ValidationError(f"Rejected by the runner: {result.error or 'invalid job'}")
    if result.status != runner_pb2.EXECUTE_STATUS_OK:
        raise Unavailable(f"Runner failed: {result.error or runner_pb2.ExecuteStatus.Name(result.status)}")
    if not result.results:
        raise Unavailable("Runner returned no results")
    run = result.results[0]
    return judge_pb2.RunCodeResponse(
        status=run.status,
        stdout=run.stdout,
        stderr=run.stderr,
        exit_code=run.exit_code,
        time_ms=run.time_ms,
        memory_kb=run.memory_kb,
    )


class RunService:
    def __init__(self, problems: Problems, queue: Queue, *, run_timeout_s: float = 30.0):
        self.problems = problems
        self.queue = queue
        self.run_timeout_s = run_timeout_s

    def run_code(self, req: judge_pb2.RunCodeRequest) -> judge_pb2.RunCodeResponse:
        language = validation.language(req.language)
        source = validation.source(req.source)
        stdin = validation.stdin(req.stdin)
        problem_id = validation.optional_id(req.problem_id, "problem_id")

        time_limit_ms, memory_limit_mb = DEFAULT_TIME_LIMIT_MS, DEFAULT_MEMORY_LIMIT_MB
        if problem_id:
            problem = self.problems.get_problem(problem_id)
            time_limit_ms, memory_limit_mb = problem.time_limit_ms, problem.memory_limit_mb

        job = runner_pb2.ExecuteJob(
            job_id=str(uuid.uuid4()),
            language=language,
            source=source,
            tests=[runner_pb2.TestInput(id="custom", stdin=stdin)],
            time_limit_ms=time_limit_ms,
            memory_limit_mb=memory_limit_mb,
        )
        return to_response(self.queue.run_job(job, self.run_timeout_s))
