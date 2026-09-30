"""JudgeService through a real in-process grpc.aio server (free port) with fake repositories."""

import asyncio
import logging

import grpc
import pytest
from grpc_health.v1 import health_pb2, health_pb2_grpc

from app import SERVER_OPTIONS, create_app
from app.config import Settings
from app.errors import DeadlineExceeded
from app.gen.oj.v1 import judge_pb2, judge_pb2_grpc, runner_pb2, types_pb2
from app.healthcheck import check
from tests.fakes import seed_problem

SC = grpc.StatusCode


@pytest.fixture
async def server(dao, queue):
    app = create_app(Settings(grpc_addr="127.0.0.1:0"), dao=dao, queue=queue)
    await app.start(recover=False)
    yield app
    await app.stop(grace=0)


@pytest.fixture
async def channel(server):
    async with grpc.aio.insecure_channel(f"127.0.0.1:{server.port}", options=SERVER_OPTIONS) as ch:
        yield ch


@pytest.fixture
def stub(channel):
    return judge_pb2_grpc.JudgeServiceStub(channel)


async def expect_code(call, code: grpc.StatusCode) -> str:
    with pytest.raises(grpc.aio.AioRpcError) as exc:
        await call
    assert exc.value.code() == code, exc.value.details()
    return exc.value.details()


async def test_wiring_starts_queue_and_consumers(server, queue):
    assert queue.started
    assert set(queue.handlers) == {"judge.events", "judge.jobs.dead"}


async def test_health_serving(server, channel):
    health = health_pb2_grpc.HealthStub(channel)
    for service in ("", "oj.v1.JudgeService"):
        res = await health.Check(health_pb2.HealthCheckRequest(service=service))
        assert res.status == health_pb2.HealthCheckResponse.SERVING
    assert await asyncio.to_thread(check, f"127.0.0.1:{server.port}") is True


async def test_healthcheck_fails_when_nothing_listens():
    assert await asyncio.to_thread(check, "127.0.0.1:1", 0.5) is False


async def test_status_and_languages(stub, queue):
    queue.depth, queue.consumers = 3, 2
    res = await stub.GetStatus(judge_pb2.GetStatusRequest())
    assert (res.healthy, res.queue_depth, res.runners) == (True, 3, 2)
    queue.down = True
    res = await stub.GetStatus(judge_pb2.GetStatusRequest())
    assert not res.healthy and res.broker.startswith("error")
    langs = await stub.ListLanguages(judge_pb2.ListLanguagesRequest())
    assert len(langs.languages) == 4


async def test_problem_crud_and_error_codes(stub, dao):
    req = judge_pb2.AddProblemRequest(slug="sum", title="Sum")
    req.test_cases.add(input="1 2", expected_output="3", is_sample=True)
    req.test_cases.add(input="2 2", expected_output="4")
    created = (await stub.AddProblem(req)).problem
    assert [s.output for s in created.samples] == ["3"]

    detail = (await stub.GetProblemDetail(judge_pb2.GetProblemDetailRequest(id=created.id))).problem
    assert len(detail.samples) == 1
    summaries = await stub.ListProblemSummaries(judge_pb2.ListProblemSummariesRequest())
    assert [p.slug for p in summaries.problems] == ["sum"]

    await expect_code(stub.AddProblem(req), SC.ALREADY_EXISTS)
    bad = judge_pb2.AddProblemRequest()
    bad.CopyFrom(req)
    bad.slug = "Bad Slug"
    assert "slug" in await expect_code(stub.AddProblem(bad), SC.INVALID_ARGUMENT)
    await expect_code(stub.GetProblemDetail(judge_pb2.GetProblemDetailRequest(id=999)), SC.NOT_FOUND)

    tc = await stub.AddTestCase(
        judge_pb2.AddTestCaseRequest(
            problem_id=created.id, test_case=judge_pb2.NewTestCase(input="5 5", expected_output="10")
        )
    )
    assert tc.test_case.ordinal == 3
    cases = await stub.ListProblemTestCases(judge_pb2.ListProblemTestCasesRequest(problem_id=created.id))
    assert len(cases.test_cases) == 3
    await stub.RemoveTestCase(judge_pb2.RemoveTestCaseRequest(problem_id=created.id, id=tc.test_case.id))
    edited = await stub.EditProblem(judge_pb2.EditProblemRequest(id=created.id, slug="sum2", title="Sum 2"))
    assert edited.problem.slug == "sum2"
    await stub.RemoveProblem(judge_pb2.RemoveProblemRequest(id=created.id))
    await expect_code(stub.RemoveProblem(judge_pb2.RemoveProblemRequest(id=created.id)), SC.NOT_FOUND)


async def test_submit_and_queue_errors(stub, dao, queue):
    p, _ = await seed_problem(dao)
    ok = judge_pb2.SubmitRequest(problem_id=p.id, language=types_pb2.LANGUAGE_PYTHON, source="print(1)")
    sub = (await stub.Submit(ok)).submission
    assert sub.status == types_pb2.SUBMISSION_STATUS_PENDING and sub.username == "anonymous"
    assert queue.published[0].job_id == f"submission-{sub.id}"

    listed = await stub.ListSubmissionSummaries(judge_pb2.ListSubmissionSummariesRequest())
    assert listed.submissions[0].source == ""
    detail = await stub.GetSubmissionDetail(judge_pb2.GetSubmissionDetailRequest(id=sub.id))
    assert detail.submission.source == "print(1)"

    unknown = judge_pb2.SubmitRequest()
    unknown.CopyFrom(ok)
    unknown.problem_id = 999
    await expect_code(stub.Submit(unknown), SC.NOT_FOUND)
    assert "language" in await expect_code(
        stub.Submit(judge_pb2.SubmitRequest(problem_id=p.id, source="x")), SC.INVALID_ARGUMENT
    )
    await expect_code(
        stub.ListSubmissionSummaries(judge_pb2.ListSubmissionSummariesRequest(limit=500)), SC.INVALID_ARGUMENT
    )

    queue.depth = 1000
    await expect_code(stub.Submit(ok), SC.RESOURCE_EXHAUSTED)
    queue.depth, queue.down = 0, True
    await expect_code(stub.Submit(ok), SC.UNAVAILABLE)
    queue.down, dao.down = False, True
    await expect_code(stub.Submit(ok), SC.UNAVAILABLE)


async def test_run_code(stub, queue):
    req = judge_pb2.RunCodeRequest(language=types_pb2.LANGUAGE_JAVASCRIPT, source="console.log(1)")
    queue.run_result = runner_pb2.ExecuteResult(
        status=runner_pb2.EXECUTE_STATUS_OK,
        results=[runner_pb2.TestRun(id="custom", status=types_pb2.RUN_STATUS_OK, stdout="1\n")],
    )
    res = await stub.RunCode(req)
    assert (res.status, res.stdout) == (types_pb2.RUN_STATUS_OK, "1\n")
    queue.run_result = DeadlineExceeded("No runner answered within 30s")
    await expect_code(stub.RunCode(req), SC.DEADLINE_EXCEEDED)


async def test_unexpected_error_is_internal_without_details(stub, dao):
    async def boom():
        raise RuntimeError("secret detail")

    dao.list_problems = boom
    details = await expect_code(
        stub.ListProblemSummaries(judge_pb2.ListProblemSummariesRequest()), SC.INTERNAL
    )
    assert "secret" not in details


async def test_access_log_has_method_code_and_request_id(stub, caplog):
    caplog.set_level(logging.INFO, logger="app.access")
    await expect_code(
        stub.GetProblemDetail(
            judge_pb2.GetProblemDetailRequest(id=5), metadata=(("x-request-id", "req-42"),)
        ),
        SC.NOT_FOUND,
    )
    await stub.ListLanguages(judge_pb2.ListLanguagesRequest())
    lines = [r.getMessage() for r in caplog.records if r.name == "app.access"]
    assert any(
        "/oj.v1.JudgeService/GetProblemDetail NOT_FOUND" in m and "request_id=req-42" in m for m in lines
    )
    assert any("/oj.v1.JudgeService/ListLanguages OK" in m for m in lines)


async def test_large_messages_up_to_64_mib(stub, dao):
    p, _ = await seed_problem(dao)
    big = "x" * (5 * 1024 * 1024)  # over gRPC's 4 MiB default
    req = judge_pb2.AddTestCaseRequest(
        problem_id=p.id, test_case=judge_pb2.NewTestCase(input=big, expected_output=big)
    )
    res = await stub.AddTestCase(req)
    assert len(res.test_case.input) == len(big)
