"""SubmissionService with fake repositories: submit, public shaping, the judge.events / dead-letter
pipeline (incl. compare-and-set) and startup recovery."""

from datetime import UTC, datetime, timedelta

import pytest
from google.protobuf.timestamp_pb2 import Timestamp

from app.errors import NotFound, ResourceExhausted, Unavailable, ValidationError
from app.gen.oj.v1 import judge_pb2, runner_pb2, types_pb2
from app.services.judging import MAX_MESSAGE_CHARS
from app.services.submission_service import DEAD_LETTER_MESSAGE, SubmissionService
from tests.fakes import seed_problem

T = types_pb2
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def service(dao, queue):
    return SubmissionService(dao, queue, max_queue_depth=10, recover_after_s=300, clock=lambda: NOW)


@pytest.fixture
async def problem(dao):
    return await seed_problem(dao)


def submit_req(problem_id, **kw):
    return judge_pb2.SubmitRequest(
        problem_id=problem_id,
        language=kw.get("language", T.LANGUAGE_PYTHON),
        source=kw.get("source", "print(int(input())*2)"),
        username=kw.get("username", "alice"),
    )


# ---------- submit ----------


async def test_submit_creates_pending_and_publishes_job(service, dao, queue, problem):
    p, cases = problem
    res = await service.submit(submit_req(p.id))
    sub = res.submission
    assert sub.status == T.SUBMISSION_STATUS_PENDING
    assert (sub.username, sub.problem_id) == ("alice", p.id)
    [job] = queue.published
    assert job.job_id == f"submission-{sub.id}"
    assert job.submission_id == sub.id
    assert job.language == T.LANGUAGE_PYTHON
    assert job.source == "print(int(input())*2)"
    assert [(t.id, t.stdin) for t in job.tests] == [(str(c.id), c.input) for c in cases]
    assert (job.time_limit_ms, job.memory_limit_mb) == (1000, 64)


async def test_submit_empty_username_is_anonymous(service, dao, problem):
    res = await service.submit(submit_req(problem[0].id, username=""))
    assert res.submission.username == "anonymous"


@pytest.mark.parametrize(
    "kw,field",
    [
        ({"language": T.LANGUAGE_UNSPECIFIED}, "language"),
        ({"source": ""}, "source"),
        ({"username": "has space"}, "username"),
    ],
)
async def test_submit_validation(service, dao, queue, problem, kw, field):
    with pytest.raises(ValidationError, match=field):
        await service.submit(submit_req(problem[0].id, **kw))
    assert dao.submissions == {} and queue.published == []


async def test_submit_requires_problem_id(service):
    with pytest.raises(ValidationError, match="problem_id"):
        await service.submit(submit_req(0))


async def test_submit_unknown_problem(service, dao):
    with pytest.raises(NotFound):
        await service.submit(submit_req(999))
    assert dao.submissions == {}


async def test_submit_queue_full_is_rejected_before_creating(service, dao, queue, problem):
    queue.depth = 10
    with pytest.raises(ResourceExhausted):
        await service.submit(submit_req(problem[0].id))
    assert dao.submissions == {}


async def test_submit_broker_down_before_creating(service, dao, queue, problem):
    queue.down = True
    with pytest.raises(Unavailable):
        await service.submit(submit_req(problem[0].id))
    assert dao.submissions == {}


async def test_submit_publish_failure_marks_failed(service, dao, queue, problem):
    async def fail(job):
        raise Unavailable("RabbitMQ unavailable: publish failed")

    queue.publish_submission_job = fail
    with pytest.raises(Unavailable):
        await service.submit(submit_req(problem[0].id))
    [sub] = dao.submissions.values()
    assert (sub.status, sub.verdict) == (T.SUBMISSION_STATUS_FAILED, T.VERDICT_INTERNAL_ERROR)


async def test_submit_problem_without_tests_fails_immediately(service, dao, queue):
    p, _ = await seed_problem(dao, slug="empty", cases=())
    res = await service.submit(submit_req(p.id))
    assert res.submission.status == T.SUBMISSION_STATUS_FAILED
    assert res.submission.message == "Problem has no test cases"
    assert queue.published == []


# ---------- public shaping ----------


async def test_list_summaries_clears_private_fields(service, dao, problem):
    sub = dao.submissions[(await service.submit(submit_req(problem[0].id))).submission.id]
    sub.message = "Wrong Answer on test 2"
    sub.results.add(test=1, verdict=T.VERDICT_ACCEPTED)
    res = await service.list_submission_summaries(judge_pb2.ListSubmissionSummariesRequest())
    [summary] = res.submissions
    assert summary.id == sub.id
    assert (summary.source, summary.message, len(summary.results)) == ("", "", 0)
    assert dao.list_requests[-1].limit == 50
    # The stored submission is untouched.
    assert dao.submissions[sub.id].source


async def test_list_summaries_filters_and_validates(service, dao, problem):
    await service.submit(submit_req(problem[0].id, username="bob"))
    await service.submit(submit_req(problem[0].id, username="carol"))
    res = await service.list_submission_summaries(
        judge_pb2.ListSubmissionSummariesRequest(username="bob", problem_id=problem[0].id, limit=5)
    )
    assert [s.username for s in res.submissions] == ["bob"]
    with pytest.raises(ValidationError, match="limit"):
        await service.list_submission_summaries(judge_pb2.ListSubmissionSummariesRequest(limit=201))


async def test_get_submission_detail(service, problem):
    sub = (await service.submit(submit_req(problem[0].id))).submission
    res = await service.get_submission_detail(judge_pb2.GetSubmissionDetailRequest(id=sub.id))
    assert res.submission.source == sub.source
    with pytest.raises(ValidationError):
        await service.get_submission_detail(judge_pb2.GetSubmissionDetailRequest())
    with pytest.raises(NotFound):
        await service.get_submission_detail(judge_pb2.GetSubmissionDetailRequest(id=999))


# ---------- judge.events ----------


def started(sid):
    return runner_pb2.JobEvent(
        job_id=f"submission-{sid}", submission_id=sid, runner_id="r1", started=runner_pb2.JobStarted()
    )


def finished(sid, result):
    return runner_pb2.JobEvent(job_id=f"submission-{sid}", submission_id=sid, runner_id="r1", finished=result)


def ok_result(cases, outputs):
    return runner_pb2.ExecuteResult(
        status=runner_pb2.EXECUTE_STATUS_OK,
        results=[
            runner_pb2.TestRun(
                id=str(c.id), status=T.RUN_STATUS_OK, stdout=out, time_ms=10 * i, memory_kb=500
            )
            for i, (c, out) in enumerate(zip(cases, outputs, strict=True), start=1)
        ],
    )


@pytest.fixture
async def submitted(service, problem):
    p, cases = problem
    sub = (await service.submit(submit_req(p.id))).submission
    return sub.id, cases


async def test_started_marks_judging(service, dao, submitted):
    sid, _ = submitted
    await service.handle_job_event(started(sid))
    assert dao.submissions[sid].status == T.SUBMISSION_STATUS_JUDGING
    assert list(dao.updates[-1].expected_statuses) == [T.SUBMISSION_STATUS_PENDING]


@pytest.mark.parametrize(
    "outputs,verdict,passed,message",
    [
        (["2\n", "10  \n\n"], T.VERDICT_ACCEPTED, 2, "All tests passed"),
        (["2", "11"], T.VERDICT_WRONG_ANSWER, 1, "Wrong Answer on test 2"),
    ],
)
async def test_finished_stores_verdict(service, dao, submitted, outputs, verdict, passed, message):
    sid, cases = submitted
    await service.handle_job_event(started(sid))
    await service.handle_job_event(finished(sid, ok_result(cases, outputs)))
    sub = dao.submissions[sid]
    assert (sub.status, sub.verdict, sub.passed, sub.total) == (
        T.SUBMISSION_STATUS_FINISHED,
        verdict,
        passed,
        2,
    )
    assert sub.time_ms == 20
    assert sub.message == message
    assert [(r.test, r.sample) for r in sub.results] == [(1, True), (2, False)]
    assert list(dao.updates[-1].expected_statuses) == [
        T.SUBMISSION_STATUS_PENDING,
        T.SUBMISSION_STATUS_JUDGING,
    ]


async def test_finished_without_started_is_accepted(service, dao, submitted):
    sid, cases = submitted
    await service.handle_job_event(finished(sid, ok_result(cases, ["2", "10"])))
    assert dao.submissions[sid].verdict == T.VERDICT_ACCEPTED


async def test_compilation_error_message_truncated(service, dao, submitted):
    sid, _ = submitted
    result = runner_pb2.ExecuteResult(
        status=runner_pb2.EXECUTE_STATUS_COMPILATION_ERROR, compile_output="e" * 5000
    )
    await service.handle_job_event(finished(sid, result))
    sub = dao.submissions[sid]
    assert (sub.status, sub.verdict, sub.total) == (
        T.SUBMISSION_STATUS_FINISHED,
        T.VERDICT_COMPILATION_ERROR,
        2,
    )
    assert sub.message == "e" * MAX_MESSAGE_CHARS


@pytest.mark.parametrize(
    "status", [runner_pb2.EXECUTE_STATUS_REJECTED, runner_pb2.EXECUTE_STATUS_INTERNAL_ERROR]
)
async def test_runner_failure_marks_failed(service, dao, submitted, status):
    sid, _ = submitted
    await service.handle_job_event(
        finished(sid, runner_pb2.ExecuteResult(status=status, error="sandbox broke"))
    )
    sub = dao.submissions[sid]
    assert (sub.status, sub.verdict) == (T.SUBMISSION_STATUS_FAILED, T.VERDICT_INTERNAL_ERROR)
    assert sub.message == "Judging failed: sandbox broke"


async def test_duplicate_finished_is_ignored(service, dao, submitted):
    sid, cases = submitted
    await service.handle_job_event(finished(sid, ok_result(cases, ["2", "10"])))
    # A redelivered job produced a different (late) result: CAS rejects it, no error.
    await service.handle_job_event(finished(sid, ok_result(cases, ["0", "0"])))
    assert dao.submissions[sid].verdict == T.VERDICT_ACCEPTED
    assert len(dao.updates) == 1


async def test_late_started_does_not_reopen(service, dao, submitted):
    sid, cases = submitted
    await service.handle_job_event(finished(sid, ok_result(cases, ["2", "10"])))
    await service.handle_job_event(started(sid))
    assert dao.submissions[sid].status == T.SUBMISSION_STATUS_FINISHED


async def test_event_for_deleted_submission_is_ignored(service, dao, submitted):
    sid, cases = submitted
    del dao.submissions[sid]
    await service.handle_job_event(started(sid))
    await service.handle_job_event(finished(sid, ok_result(cases, ["2", "10"])))


async def test_event_without_submission_is_ignored(service, dao):
    await service.handle_job_event(runner_pb2.JobEvent(job_id="x", started=runner_pb2.JobStarted()))
    assert dao.updates == []


async def test_dao_down_propagates_unavailable(service, dao, submitted):
    sid, cases = submitted
    dao.down = True
    with pytest.raises(Unavailable):
        await service.handle_job_event(finished(sid, ok_result(cases, ["2", "10"])))
    with pytest.raises(Unavailable):
        await service.handle_job_event(started(sid))


# ---------- judge.jobs.dead ----------


async def test_dead_job_marks_failed(service, dao, queue, submitted):
    sid, _ = submitted
    await service.handle_dead_job(queue.published[0])
    sub = dao.submissions[sid]
    assert (sub.status, sub.verdict, sub.message) == (
        T.SUBMISSION_STATUS_FAILED,
        T.VERDICT_INTERNAL_ERROR,
        DEAD_LETTER_MESSAGE,
    )


async def test_dead_job_after_finish_is_ignored(service, dao, queue, submitted):
    sid, cases = submitted
    await service.handle_job_event(finished(sid, ok_result(cases, ["2", "10"])))
    await service.handle_dead_job(queue.published[0])
    assert dao.submissions[sid].status == T.SUBMISSION_STATUS_FINISHED


async def test_dead_custom_run_is_dropped(service, dao):
    await service.handle_dead_job(runner_pb2.ExecuteJob(job_id="0b9f-uuid"))
    assert dao.updates == []


# ---------- recovery ----------


def at(dt):
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


async def test_recover_republishes_stale_open_submissions(service, dao, queue, problem):
    p, _ = problem
    subs = [(await service.submit(submit_req(p.id))).submission for _ in range(4)]
    queue.published.clear()
    stale, fresh = at(NOW - timedelta(seconds=301)), at(NOW - timedelta(seconds=10))
    dao.submissions[subs[0].id].update_time.CopyFrom(stale)  # PENDING, stale
    dao.submissions[subs[1].id].update_time.CopyFrom(stale)
    dao.submissions[subs[1].id].status = T.SUBMISSION_STATUS_JUDGING  # JUDGING, stale
    dao.submissions[subs[2].id].update_time.CopyFrom(fresh)  # PENDING, recent: still in flight
    dao.submissions[subs[3].id].update_time.CopyFrom(stale)
    dao.submissions[subs[3].id].status = T.SUBMISSION_STATUS_FINISHED

    assert await service.recover() == 2
    assert sorted(j.submission_id for j in queue.published) == sorted([subs[0].id, subs[1].id])
    req = dao.list_requests[-1]
    assert list(req.statuses) == [T.SUBMISSION_STATUS_PENDING, T.SUBMISSION_STATUS_JUDGING]
    assert req.updated_before.ToDatetime(tzinfo=UTC) == NOW - timedelta(seconds=300)


async def test_recover_dao_down_raises(service, dao):
    dao.down = True
    with pytest.raises(Unavailable):
        await service.recover()
