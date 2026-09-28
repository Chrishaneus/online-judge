"""RabbitMQ consumer handlers (transport): decode, call the service, return ack (True) / requeue (False)."""

import pytest

from app.gen.oj.v1 import judge_pb2, runner_pb2, types_pb2
from app.services import SubmissionService
from app.transport import JudgeConsumers
from tests.fakes import seed_problem


@pytest.fixture
async def setup(dao, queue):
    service = SubmissionService(dao, queue)
    p, _ = await seed_problem(dao)
    sub = (
        await service.submit(
            judge_pb2.SubmitRequest(problem_id=p.id, language=types_pb2.LANGUAGE_C, source="int main(){}")
        )
    ).submission
    return JudgeConsumers(service), sub.id


def event_body(sid, **kw):
    return runner_pb2.JobEvent(job_id=f"submission-{sid}", submission_id=sid, **kw).SerializeToString()


async def test_event_acks_after_dao_write(setup, dao):
    consumers, sid = setup
    assert await consumers.on_job_event(event_body(sid, started=runner_pb2.JobStarted())) is True
    assert dao.submissions[sid].status == types_pb2.SUBMISSION_STATUS_JUDGING


async def test_event_requeues_when_dao_down(setup, dao):
    consumers, sid = setup
    dao.down = True
    assert await consumers.on_job_event(event_body(sid, started=runner_pb2.JobStarted())) is False


async def test_duplicate_finished_is_acked(setup, dao):
    consumers, sid = setup
    body = event_body(
        sid,
        finished=runner_pb2.ExecuteResult(
            status=runner_pb2.EXECUTE_STATUS_COMPILATION_ERROR, compile_output="x"
        ),
    )
    assert await consumers.on_job_event(body) is True
    assert await consumers.on_job_event(body) is True
    assert dao.submissions[sid].verdict == types_pb2.VERDICT_COMPILATION_ERROR


async def test_undecodable_messages_are_acked(setup):
    consumers, _ = setup
    assert await consumers.on_job_event(b"\xff\xff\xff") is True
    assert await consumers.on_dead_job(b"\xff\xff\xff") is True


async def test_dead_job_marks_failed_and_acks(setup, dao, queue):
    consumers, sid = setup
    assert await consumers.on_dead_job(queue.published[0].SerializeToString()) is True
    assert dao.submissions[sid].status == types_pb2.SUBMISSION_STATUS_FAILED


async def test_dead_job_requeues_when_dao_down(setup, dao, queue):
    consumers, _ = setup
    dao.down = True
    assert await consumers.on_dead_job(queue.published[0].SerializeToString()) is False
