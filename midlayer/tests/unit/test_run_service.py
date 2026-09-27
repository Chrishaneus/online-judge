import pytest

from app.errors import DeadlineExceeded, NotFound, Unavailable, ValidationError
from app.gen.oj.v1 import judge_pb2, runner_pb2, types_pb2
from app.services import RunService
from tests.fakes import seed_problem


@pytest.fixture
def service(dao, queue):
    return RunService(dao, queue, run_timeout_s=7)


def req(**kw):
    return judge_pb2.RunCodeRequest(
        language=kw.pop("language", types_pb2.LANGUAGE_CPP), source=kw.pop("source", "int main(){}"), **kw
    )


async def test_run_ok_maps_first_test_run(service, queue):
    queue.run_result = runner_pb2.ExecuteResult(
        status=runner_pb2.EXECUTE_STATUS_OK,
        results=[
            runner_pb2.TestRun(
                id="custom",
                status=types_pb2.RUN_STATUS_RUNTIME_ERROR,
                stdout="out",
                stderr="err",
                exit_code=3,
                time_ms=12,
                memory_kb=3456,
            )
        ],
    )
    res = await service.run_code(req(stdin="1 2"))
    assert res == judge_pb2.RunCodeResponse(
        status=types_pb2.RUN_STATUS_RUNTIME_ERROR,
        stdout="out",
        stderr="err",
        exit_code=3,
        time_ms=12,
        memory_kb=3456,
    )
    [(job, timeout)] = queue.run_jobs
    assert timeout == 7
    assert job.submission_id == 0 and len(job.job_id) == 36  # UUID
    assert [(t.id, t.stdin) for t in job.tests] == [("custom", "1 2")]
    assert (job.time_limit_ms, job.memory_limit_mb) == (2000, 256)


async def test_run_uses_problem_limits(service, dao, queue):
    p, _ = await seed_problem(dao, time_limit_ms=300, memory_limit_mb=32)
    queue.run_result = runner_pb2.ExecuteResult(
        status=runner_pb2.EXECUTE_STATUS_OK, results=[runner_pb2.TestRun(status=types_pb2.RUN_STATUS_OK)]
    )
    await service.run_code(req(problem_id=p.id))
    job = queue.run_jobs[0][0]
    assert (job.time_limit_ms, job.memory_limit_mb) == (300, 32)
    with pytest.raises(NotFound):
        await service.run_code(req(problem_id=999))


async def test_run_compilation_error(service, queue):
    queue.run_result = runner_pb2.ExecuteResult(
        status=runner_pb2.EXECUTE_STATUS_COMPILATION_ERROR, compile_output="error: expected ';'"
    )
    res = await service.run_code(req())
    assert res.status == types_pb2.RUN_STATUS_COMPILATION_ERROR
    assert res.compile_output == "error: expected ';'"


@pytest.mark.parametrize(
    "result,error",
    [
        (runner_pb2.ExecuteResult(status=runner_pb2.EXECUTE_STATUS_REJECTED, error="bad"), ValidationError),
        (runner_pb2.ExecuteResult(status=runner_pb2.EXECUTE_STATUS_INTERNAL_ERROR, error="x"), Unavailable),
        (runner_pb2.ExecuteResult(status=runner_pb2.EXECUTE_STATUS_OK), Unavailable),
        (DeadlineExceeded("No runner answered within 7s"), DeadlineExceeded),
    ],
)
async def test_run_failures(service, queue, result, error):
    queue.run_result = result
    with pytest.raises(error):
        await service.run_code(req())


@pytest.mark.parametrize(
    "kw,field",
    [
        ({"language": types_pb2.LANGUAGE_UNSPECIFIED}, "language"),
        ({"source": ""}, "source"),
        ({"stdin": "x" * (1024 * 1024 + 1)}, "stdin"),
        ({"problem_id": -1}, "problem_id"),
    ],
)
async def test_run_validation(service, queue, kw, field):
    with pytest.raises(ValidationError, match=field):
        await service.run_code(req(**kw))
    assert queue.run_jobs == []
