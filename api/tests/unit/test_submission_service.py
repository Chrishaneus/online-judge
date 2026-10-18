"""SubmissionService with fake repositories: submit, public shaping, the judge.events / dead-letter
pipeline (incl. compare-and-set) and startup recovery."""

from datetime import UTC, datetime, timedelta

import pytest
from google.protobuf.timestamp_pb2 import Timestamp

from app.errors import NotFound, QueueFull, Unavailable, ValidationError
from app.gen.oj.v1 import judge_pb2, runner_pb2, types_pb2
from app.services.judging import MAX_MESSAGE_CHARS
from app.services.submission_service import DEAD_LETTER_MESSAGE, SubmissionService
from tests.fakes import seed_problem

T = types_pb2
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def service(store, queue):
    return SubmissionService(store, store, queue, max_queue_depth=10, recover_after_s=300, clock=lambda: NOW)


@pytest.fixture
def problem(store):
    return seed_problem(store)


def submit_req(problem_id, **kw):
    return judge_pb2.SubmitRequest(
        problem_id=problem_id,
        language=kw.get("language", T.LANGUAGE_PYTHON),
        source=kw.get("source", "print(int(input())*2)"),
        username=kw.get("username", "alice"),
    )


# ---------- submit ----------


def test_submit_creates_pending_and_publishes_job(service, store, queue, problem):
    p, cases = problem
    res = service.submit(submit_req(p.id))
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


def test_submit_empty_username_is_anonymous(service, store, problem):
    res = service.submit(submit_req(problem[0].id, username=""))
    assert res.submission.username == "anonymous"


@pytest.mark.parametrize(
    "kw,field",
    [
        ({"language": T.LANGUAGE_UNSPECIFIED}, "language"),
        ({"source": ""}, "source"),
        ({"username": "has space"}, "username"),
    ],
)
def test_submit_validation(service, store, queue, problem, kw, field):
    with pytest.raises(ValidationError, match=field):
        service.submit(submit_req(problem[0].id, **kw))
    assert store.submissions == {} and queue.published == []


def test_submit_requires_problem_id(service):
    with pytest.raises(ValidationError, match="problem_id"):
        service.submit(submit_req(0))


def test_submit_unknown_problem(service, store):
    with pytest.raises(NotFound):
        service.submit(submit_req(999))
    assert store.submissions == {}


def test_submit_queue_full_is_rejected_before_creating(service, store, queue, problem):
    queue.depth = 10
    with pytest.raises(QueueFull):
        service.submit(submit_req(problem[0].id))
    assert store.submissions == {}


def test_submit_broker_down_before_creating(service, store, queue, problem):
    queue.down = True
    with pytest.raises(Unavailable):
        service.submit(submit_req(problem[0].id))
    assert store.submissions == {}


def test_submit_publish_failure_marks_failed(service, store, queue, problem):
    def fail(job):
        raise Unavailable("RabbitMQ unavailable: publish failed")

    queue.publish_submission_job = fail
    with pytest.raises(Unavailable):
        service.submit(submit_req(problem[0].id))
    [sub] = store.submissions.values()
    assert (sub.status, sub.verdict) == (T.SUBMISSION_STATUS_FAILED, T.VERDICT_INTERNAL_ERROR)


def test_submit_problem_without_tests_fails_immediately(service, store, queue):
    p, _ = seed_problem(store, slug="empty", cases=())
    res = service.submit(submit_req(p.id))
    assert res.submission.status == T.SUBMISSION_STATUS_FAILED
    assert res.submission.message == "Problem has no test cases"
    assert queue.published == []


# ---------- public shaping ----------


def test_list_summaries_clears_private_fields(service, store, problem):
    sub = store.submissions[(service.submit(submit_req(problem[0].id))).submission.id]
    sub.message = "Wrong Answer on test 2"
    sub.results.add(test=1, verdict=T.VERDICT_ACCEPTED)
    res = service.list_submission_summaries(judge_pb2.ListSubmissionSummariesRequest())
    [summary] = res.submissions
    assert summary.id == sub.id
    assert (summary.source, summary.message, len(summary.results)) == ("", "", 0)
    assert store.list_requests[-1].limit == 50
    # The stored submission is untouched.
    assert store.submissions[sub.id].source


def test_list_summaries_filters_and_validates(service, store, problem):
    service.submit(submit_req(problem[0].id, username="bob"))
    service.submit(submit_req(problem[0].id, username="carol"))
    res = service.list_submission_summaries(
        judge_pb2.ListSubmissionSummariesRequest(username="bob", problem_id=problem[0].id, limit=5)
    )
    assert [s.username for s in res.submissions] == ["bob"]
    with pytest.raises(ValidationError, match="limit"):
        service.list_submission_summaries(judge_pb2.ListSubmissionSummariesRequest(limit=201))


def test_get_submission_detail(service, problem):
    sub = (service.submit(submit_req(problem[0].id))).submission
    res = service.get_submission_detail(judge_pb2.GetSubmissionDetailRequest(id=sub.id))
    assert res.submission.source == sub.source
    with pytest.raises(ValidationError):
        service.get_submission_detail(judge_pb2.GetSubmissionDetailRequest())
    with pytest.raises(NotFound):
        service.get_submission_detail(judge_pb2.GetSubmissionDetailRequest(id=999))


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
def submitted(service, problem):
    p, cases = problem
    sub = (service.submit(submit_req(p.id))).submission
    return sub.id, cases


def test_started_marks_judging(service, store, submitted):
    sid, _ = submitted
    service.handle_job_event(started(sid))
    assert store.submissions[sid].status == T.SUBMISSION_STATUS_JUDGING
    assert list(store.updates[-1].expected_statuses) == [T.SUBMISSION_STATUS_PENDING]


@pytest.mark.parametrize(
    "outputs,verdict,passed,message",
    [
        (["2\n", "10  \n\n"], T.VERDICT_ACCEPTED, 2, "All tests passed"),
        (["2", "11"], T.VERDICT_WRONG_ANSWER, 1, "Wrong Answer on test 2"),
    ],
)
def test_finished_stores_verdict(service, store, submitted, outputs, verdict, passed, message):
    sid, cases = submitted
    service.handle_job_event(started(sid))
    service.handle_job_event(finished(sid, ok_result(cases, outputs)))
    sub = store.submissions[sid]
    assert (sub.status, sub.verdict, sub.passed, sub.total) == (
        T.SUBMISSION_STATUS_FINISHED,
        verdict,
        passed,
        2,
    )
    assert sub.time_ms == 20
    assert sub.message == message
    assert [(r.test, r.sample) for r in sub.results] == [(1, True), (2, False)]
    assert list(store.updates[-1].expected_statuses) == [
        T.SUBMISSION_STATUS_PENDING,
        T.SUBMISSION_STATUS_JUDGING,
    ]


def test_finished_without_started_is_accepted(service, store, submitted):
    sid, cases = submitted
    service.handle_job_event(finished(sid, ok_result(cases, ["2", "10"])))
    assert store.submissions[sid].verdict == T.VERDICT_ACCEPTED


def test_compilation_error_message_truncated(service, store, submitted):
    sid, _ = submitted
    result = runner_pb2.ExecuteResult(
        status=runner_pb2.EXECUTE_STATUS_COMPILATION_ERROR, compile_output="e" * 5000
    )
    service.handle_job_event(finished(sid, result))
    sub = store.submissions[sid]
    assert (sub.status, sub.verdict, sub.total) == (
        T.SUBMISSION_STATUS_FINISHED,
        T.VERDICT_COMPILATION_ERROR,
        2,
    )
    assert sub.message == "e" * MAX_MESSAGE_CHARS


@pytest.mark.parametrize(
    "status", [runner_pb2.EXECUTE_STATUS_REJECTED, runner_pb2.EXECUTE_STATUS_INTERNAL_ERROR]
)
def test_runner_failure_marks_failed(service, store, submitted, status):
    sid, _ = submitted
    service.handle_job_event(finished(sid, runner_pb2.ExecuteResult(status=status, error="sandbox broke")))
    sub = store.submissions[sid]
    assert (sub.status, sub.verdict) == (T.SUBMISSION_STATUS_FAILED, T.VERDICT_INTERNAL_ERROR)
    assert sub.message == "Judging failed: sandbox broke"


def test_duplicate_finished_is_ignored(service, store, submitted):
    sid, cases = submitted
    service.handle_job_event(finished(sid, ok_result(cases, ["2", "10"])))
    # A redelivered job produced a different (late) result: CAS rejects it, no error.
    service.handle_job_event(finished(sid, ok_result(cases, ["0", "0"])))
    assert store.submissions[sid].verdict == T.VERDICT_ACCEPTED
    assert len(store.updates) == 1


def test_late_started_does_not_reopen(service, store, submitted):
    sid, cases = submitted
    service.handle_job_event(finished(sid, ok_result(cases, ["2", "10"])))
    service.handle_job_event(started(sid))
    assert store.submissions[sid].status == T.SUBMISSION_STATUS_FINISHED


def test_event_for_deleted_submission_is_ignored(service, store, submitted):
    sid, cases = submitted
    del store.submissions[sid]
    service.handle_job_event(started(sid))
    service.handle_job_event(finished(sid, ok_result(cases, ["2", "10"])))


def test_event_without_submission_is_ignored(service, store):
    service.handle_job_event(runner_pb2.JobEvent(job_id="x", started=runner_pb2.JobStarted()))
    assert store.updates == []


def test_dao_down_propagates_unavailable(service, store, submitted):
    sid, cases = submitted
    store.down = True
    with pytest.raises(Unavailable):
        service.handle_job_event(finished(sid, ok_result(cases, ["2", "10"])))
    with pytest.raises(Unavailable):
        service.handle_job_event(started(sid))


# ---------- judge.jobs.dead ----------


def test_dead_job_marks_failed(service, store, queue, submitted):
    sid, _ = submitted
    service.handle_dead_job(queue.published[0])
    sub = store.submissions[sid]
    assert (sub.status, sub.verdict, sub.message) == (
        T.SUBMISSION_STATUS_FAILED,
        T.VERDICT_INTERNAL_ERROR,
        DEAD_LETTER_MESSAGE,
    )


def test_dead_job_after_finish_is_ignored(service, store, queue, submitted):
    sid, cases = submitted
    service.handle_job_event(finished(sid, ok_result(cases, ["2", "10"])))
    service.handle_dead_job(queue.published[0])
    assert store.submissions[sid].status == T.SUBMISSION_STATUS_FINISHED


def test_dead_custom_run_is_dropped(service, store):
    service.handle_dead_job(runner_pb2.ExecuteJob(job_id="0b9f-uuid"))
    assert store.updates == []


# ---------- recovery ----------


def at(dt):
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


def test_recover_republishes_stale_open_submissions(service, store, queue, problem):
    p, _ = problem
    subs = [(service.submit(submit_req(p.id))).submission for _ in range(4)]
    queue.published.clear()
    stale, fresh = at(NOW - timedelta(seconds=301)), at(NOW - timedelta(seconds=10))
    store.submissions[subs[0].id].update_time.CopyFrom(stale)  # PENDING, stale
    store.submissions[subs[1].id].update_time.CopyFrom(stale)
    store.submissions[subs[1].id].status = T.SUBMISSION_STATUS_JUDGING  # JUDGING, stale
    store.submissions[subs[2].id].update_time.CopyFrom(fresh)  # PENDING, recent: still in flight
    store.submissions[subs[3].id].update_time.CopyFrom(stale)
    store.submissions[subs[3].id].status = T.SUBMISSION_STATUS_FINISHED

    assert service.recover() == 2
    assert sorted(j.submission_id for j in queue.published) == sorted([subs[0].id, subs[1].id])
    req = store.list_requests[-1]
    assert list(req.statuses) == [T.SUBMISSION_STATUS_PENDING, T.SUBMISSION_STATUS_JUDGING]
    assert req.updated_before == NOW - timedelta(seconds=300)


def test_recover_dao_down_raises(service, store):
    store.down = True
    with pytest.raises(Unavailable):
        service.recover()
