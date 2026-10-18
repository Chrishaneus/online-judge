"""RabbitMQ consumer handlers (transport): decode, call the service, return ack (True) / requeue (False)."""

import pytest

from app.controllers.consumers import JudgeConsumers
from app.gen.oj.v1 import judge_pb2, runner_pb2, types_pb2
from app.services import SubmissionService
from tests.fakes import seed_problem


@pytest.fixture
def setup(store, queue):
    service = SubmissionService(store, store, queue)
    p, _ = seed_problem(store)
    sub = (
        service.submit(
            judge_pb2.SubmitRequest(problem_id=p.id, language=types_pb2.LANGUAGE_C, source="int main(){}")
        )
    ).submission
    return JudgeConsumers(service), sub.id


def event_body(sid, **kw):
    return runner_pb2.JobEvent(job_id=f"submission-{sid}", submission_id=sid, **kw).SerializeToString()


def test_event_acks_after_dao_write(setup, store):
    consumers, sid = setup
    assert consumers.on_job_event(event_body(sid, started=runner_pb2.JobStarted())) is True
    assert store.submissions[sid].status == types_pb2.SUBMISSION_STATUS_JUDGING


def test_event_requeues_when_dao_down(setup, store):
    consumers, sid = setup
    store.down = True
    assert consumers.on_job_event(event_body(sid, started=runner_pb2.JobStarted())) is False


def test_duplicate_finished_is_acked(setup, store):
    consumers, sid = setup
    body = event_body(
        sid,
        finished=runner_pb2.ExecuteResult(
            status=runner_pb2.EXECUTE_STATUS_COMPILATION_ERROR, compile_output="x"
        ),
    )
    assert consumers.on_job_event(body) is True
    assert consumers.on_job_event(body) is True
    assert store.submissions[sid].verdict == types_pb2.VERDICT_COMPILATION_ERROR


def test_undecodable_messages_are_acked(setup):
    consumers, _ = setup
    assert consumers.on_job_event(b"\xff\xff\xff") is True
    assert consumers.on_dead_job(b"\xff\xff\xff") is True


def test_dead_job_marks_failed_and_acks(setup, store, queue):
    consumers, sid = setup
    assert consumers.on_dead_job(queue.published[0].SerializeToString()) is True
    assert store.submissions[sid].status == types_pb2.SUBMISSION_STATUS_FAILED


def test_dead_job_requeues_when_dao_down(setup, store, queue):
    consumers, _ = setup
    store.down = True
    assert consumers.on_dead_job(queue.published[0].SerializeToString()) is False
