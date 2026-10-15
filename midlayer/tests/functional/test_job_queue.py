"""JobQueue against a real RabbitMQ. Set RABBITMQ_TEST_URL (e.g. amqp://oj:oj@127.0.0.1:5673/) to run.

Each test uses its own queue-name prefix so parallel runs on a shared broker don't interfere, and
deletes its queues afterwards.
"""

import asyncio
import os
import uuid

import aio_pika
import pytest

from app import create_app
from app.config import Settings
from app.errors import DeadlineExceeded
from app.gen.oj.v1 import judge_pb2, runner_pb2, types_pb2
from app.repositories import JobQueue
from app.repositories.job_queue import QUORUM, jobs_queue_arguments
from tests.fakes import seed_problem

URL = os.environ.get("RABBITMQ_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="RABBITMQ_TEST_URL not set")


@pytest.fixture
def names():
    prefix = f"test-midlayer-{uuid.uuid4().hex[:8]}."
    return {
        "jobs_queue": prefix + "judge.jobs",
        "dead_queue": prefix + "judge.jobs.dead",
        "events_queue": prefix + "judge.events",
        "reply_queue_prefix": prefix + "judge.rpc.",
    }


@pytest.fixture
async def raw():
    """A separate connection playing the runner / inspecting queues."""
    conn = await aio_pika.connect(URL)
    yield conn
    await conn.close()


@pytest.fixture
async def jq(names, raw):
    q = JobQueue(URL, prefetch=4, requeue_delay_s=0.1, **names)
    await q.start()
    yield q
    await q.close()
    async with raw.channel() as ch:
        for key in ("jobs_queue", "dead_queue", "events_queue"):
            await ch.queue_delete(names[key], if_unused=False, if_empty=False)


def job(job_id="submission-7", submission_id=7):
    return runner_pb2.ExecuteJob(
        job_id=job_id,
        submission_id=submission_id,
        language=types_pb2.LANGUAGE_PYTHON,
        source="print(1)",
        tests=[runner_pb2.TestInput(id="1", stdin="")],
        time_limit_ms=1000,
        memory_limit_mb=64,
    )


async def get_one(channel, queue_name, timeout=5.0):
    queue = await channel.get_queue(queue_name, ensure=False)
    async with asyncio.timeout(timeout):
        while True:
            msg = await queue.get(fail=False)
            if msg is not None:
                return msg
            await asyncio.sleep(0.05)


async def test_topology_matches_runner_proto(jq, names, raw):
    # Re-declaring with the arguments from runner.proto succeeds only if they are identical.
    async with raw.channel() as ch:
        await ch.declare_queue(
            names["jobs_queue"], durable=True, arguments=jobs_queue_arguments(names["dead_queue"])
        )
        await ch.declare_queue(names["dead_queue"], durable=True, arguments=QUORUM)
        await ch.declare_queue(names["events_queue"], durable=True, arguments=QUORUM)
    assert jobs_queue_arguments("judge.jobs.dead") == {
        "x-queue-type": "quorum",
        "x-delivery-limit": 3,
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": "judge.jobs.dead",
    }


async def test_publish_submission_job_properties(jq, names, raw):
    await jq.publish_submission_job(job())
    async with raw.channel() as ch:
        msg = await get_one(ch, names["jobs_queue"])
        await msg.ack()
    assert runner_pb2.ExecuteJob.FromString(msg.body) == job()
    assert msg.content_type == "application/x-protobuf"
    assert msg.type == "oj.v1.ExecuteJob"
    assert msg.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    assert msg.correlation_id == "submission-7"
    assert msg.reply_to == names["events_queue"]
    assert msg.expiration is None


async def test_queue_stats(jq, names, raw):
    assert await jq.queue_stats() == (0, 0)
    await jq.publish_submission_job(job())
    await jq.publish_submission_job(job("submission-8", 8))
    async with raw.channel() as ch:
        await ch.set_qos(prefetch_count=1)
        q = await ch.get_queue(names["jobs_queue"], ensure=False)

        async def hold(message):  # keep it unacked so the consumer stays busy
            pass

        tag = await q.consume(hold)
        async with asyncio.timeout(5):
            while (await jq.queue_stats())[1] != 1:
                await asyncio.sleep(0.05)
        depth, consumers = await jq.queue_stats()
        assert consumers == 1 and depth <= 1
        await q.cancel(tag)


async def fake_runner(raw, names, result: runner_pb2.ExecuteResult, seen: list):
    """Consume one job and answer like runner: started, then finished, to reply_to."""
    ch = await raw.channel()
    msg = await get_one(ch, names["jobs_queue"])
    seen.append(msg)
    received = runner_pb2.ExecuteJob.FromString(msg.body)
    for kw in ({"started": runner_pb2.JobStarted()}, {"finished": result}):
        event = runner_pb2.JobEvent(job_id=received.job_id, submission_id=received.submission_id, **kw)
        await ch.default_exchange.publish(
            aio_pika.Message(
                event.SerializeToString(),
                content_type="application/x-protobuf",
                type="oj.v1.JobEvent",
                correlation_id=msg.correlation_id,
            ),
            routing_key=msg.reply_to,
        )
    await msg.ack()
    await ch.close()


async def test_run_job_rpc(jq, names, raw):
    result = runner_pb2.ExecuteResult(
        status=runner_pb2.EXECUTE_STATUS_OK,
        results=[runner_pb2.TestRun(id="custom", status=types_pb2.RUN_STATUS_OK, stdout="1\n")],
    )
    seen = []
    runner = asyncio.create_task(fake_runner(raw, names, result, seen))
    got = await jq.run_job(job("3f1c-run", 0), timeout_s=10)
    await runner
    assert got == result
    assert seen[0].reply_to == jq.reply_queue
    assert seen[0].correlation_id == "3f1c-run"
    assert seen[0].expiration == 10


async def test_run_job_times_out(jq):
    with pytest.raises(DeadlineExceeded):
        await jq.run_job(job("never-answered", 0), timeout_s=0.3)
    assert jq._pending == {}


async def test_consume_ack_and_requeue(jq, names, raw):
    calls = []

    async def handler(body: bytes) -> bool:
        calls.append(body)
        return len(calls) > 1  # first delivery: "dao down" -> requeue; then ack

    await jq.consume(names["events_queue"], handler)
    async with raw.channel() as ch:
        await ch.default_exchange.publish(aio_pika.Message(b"evt"), routing_key=names["events_queue"])
    async with asyncio.timeout(5):
        while len(calls) < 2:
            await asyncio.sleep(0.05)
    await asyncio.sleep(0.3)
    assert calls == [b"evt", b"evt"]
    async with raw.channel() as ch:
        q = await ch.declare_queue(names["events_queue"], passive=True)
        assert q.declaration_result.message_count == 0


async def test_rejected_jobs_are_dead_lettered(jq, names, raw):
    """A job that keeps failing (runner crash) lands in judge.jobs.dead after x-delivery-limit."""
    dead = asyncio.get_running_loop().create_future()

    async def on_dead(body: bytes) -> bool:
        if not dead.done():
            dead.set_result(runner_pb2.ExecuteJob.FromString(body))
        return True

    await jq.consume(names["dead_queue"], on_dead)
    await jq.publish_submission_job(job())
    for _ in range(4):  # first delivery + 3 redeliveries; each time the "runner" dies holding the job
        ch = await raw.channel()
        await get_one(ch, names["jobs_queue"])
        await ch.close()  # unacked -> returned to the queue, delivery count + 1
    async with asyncio.timeout(10):
        got = await dead
    assert got.submission_id == 7
    async with raw.channel() as ch:
        q = await ch.declare_queue(names["jobs_queue"], passive=True)
        assert q.declaration_result.message_count == 0


@pytest.fixture
async def app_with_broker(names, raw, dao):
    settings = Settings(grpc_addr="127.0.0.1:0", rabbitmq_url=URL, requeue_delay_s=0.1, **names)
    app = create_app(settings, dao=dao)
    await app.start(recover=False)
    yield app
    await app.stop(grace=0)
    async with raw.channel() as ch:
        for key in ("jobs_queue", "dead_queue", "events_queue"):
            await ch.queue_delete(names[key], if_unused=False, if_empty=False)


async def wait_for_status(dao, sid, status, timeout=10.0):
    async with asyncio.timeout(timeout):
        while dao.submissions[sid].status != status:
            await asyncio.sleep(0.05)
    return dao.submissions[sid]


async def test_submission_judged_end_to_end(app_with_broker, names, raw, dao):
    p, cases = await seed_problem(dao)
    sub = (
        await app_with_broker.services.submissions.submit(
            judge_pb2.SubmitRequest(problem_id=p.id, language=types_pb2.LANGUAGE_PYTHON, source="x")
        )
    ).submission
    result = runner_pb2.ExecuteResult(
        status=runner_pb2.EXECUTE_STATUS_OK,
        results=[
            runner_pb2.TestRun(id=str(c.id), status=types_pb2.RUN_STATUS_OK, stdout=out)
            for c, out in zip(cases, ["2", "11"], strict=True)
        ],
    )
    await fake_runner(raw, names, result, [])
    stored = await wait_for_status(dao, sub.id, types_pb2.SUBMISSION_STATUS_FINISHED)
    assert (stored.verdict, stored.passed, stored.message) == (
        types_pb2.VERDICT_WRONG_ANSWER,
        1,
        "Wrong Answer on test 2",
    )


async def test_dead_lettered_submission_fails(app_with_broker, names, raw, dao):
    p, _ = await seed_problem(dao)
    sub = (
        await app_with_broker.services.submissions.submit(
            judge_pb2.SubmitRequest(problem_id=p.id, language=types_pb2.LANGUAGE_C, source="x")
        )
    ).submission
    for _ in range(4):
        ch = await raw.channel()
        await get_one(ch, names["jobs_queue"])
        await ch.close()
    stored = await wait_for_status(dao, sub.id, types_pb2.SUBMISSION_STATUS_FAILED)
    assert stored.message == "Judging failed: runner crashed or job expired"


async def test_events_requeued_while_dao_down(app_with_broker, names, raw, dao):
    p, _ = await seed_problem(dao)
    sub = await dao.create_submission(types_pb2.Submission(problem_id=p.id, language=1, source="x"))
    dao.down = True
    event = runner_pb2.JobEvent(job_id="submission-x", submission_id=sub.id, started=runner_pb2.JobStarted())
    async with raw.channel() as ch:
        await ch.default_exchange.publish(
            aio_pika.Message(event.SerializeToString()), routing_key=names["events_queue"]
        )
    await asyncio.sleep(0.5)  # a few nack/requeue rounds
    dao.down = False
    await wait_for_status(dao, sub.id, types_pb2.SUBMISSION_STATUS_JUDGING)
