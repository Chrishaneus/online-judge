"""JobQueue and the worker against a real RabbitMQ (ported from midlayer's broker tests).

Set RABBITMQ_TEST_URL (e.g. amqp://oj:oj@127.0.0.1:5673/, `make test-broker`) to run. Each test uses its
own queue-name prefix so runs on a shared broker don't interfere, and deletes its queues afterwards.
Persistence is the in-memory FakeStore here; test_end_to_end.py adds real Postgres.
"""

import os
import threading
import time
import uuid

import pika
import pytest

from app.config import Settings
from app.errors import Timeout, Unavailable
from app.gen.oj.v1 import judge_pb2, runner_pb2, types_pb2
from app.repositories import JobQueue
from app.repositories.job_queue import QUORUM, jobs_queue_arguments
from app.worker import Worker, healthcheck
from tests.fakes import FakeStore, fake_repositories, seed_problem

URL = os.environ.get("RABBITMQ_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="RABBITMQ_TEST_URL not set")


@pytest.fixture
def names():
    prefix = f"test-api-{uuid.uuid4().hex[:8]}."
    return {
        "jobs_queue": prefix + "judge.jobs",
        "dead_queue": prefix + "judge.jobs.dead",
        "events_queue": prefix + "judge.events",
        "reply_queue_prefix": prefix + "judge.rpc.",
    }


@pytest.fixture
def raw(names):
    """A separate connection playing the runner / inspecting queues. Deletes the test queues at the end."""
    conn = pika.BlockingConnection(pika.URLParameters(URL))
    yield conn
    if conn.is_open:
        conn.close()
    cleanup = pika.BlockingConnection(pika.URLParameters(URL))
    ch = cleanup.channel()
    for key in ("jobs_queue", "dead_queue", "events_queue"):
        ch.queue_delete(names[key])
    cleanup.close()


@pytest.fixture
def jq(names, raw):
    q = JobQueue(URL, **names)
    q.connect()
    yield q
    q.close()


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


def get_one(channel, queue, timeout=5.0):
    """basic_get until a message arrives (not acked: the caller settles it or closes the channel)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        method, props, body = channel.basic_get(queue, auto_ack=False)
        if method is not None:
            return method, props, body
        time.sleep(0.05)
    raise AssertionError(f"no message on {queue} within {timeout}s")


def wait_until(predicate, timeout=10.0, what="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


def message_count(raw, queue) -> int:
    ch = raw.channel()
    try:
        return ch.queue_declare(queue, passive=True).method.message_count
    finally:
        ch.close()


def test_topology_matches_runner_proto(jq, names, raw):
    # Re-declaring with the arguments from runner.proto succeeds only if they are identical.
    ch = raw.channel()
    ch.queue_declare(names["jobs_queue"], durable=True, arguments=jobs_queue_arguments(names["dead_queue"]))
    ch.queue_declare(names["dead_queue"], durable=True, arguments=QUORUM)
    ch.queue_declare(names["events_queue"], durable=True, arguments=QUORUM)
    ch.close()
    assert jobs_queue_arguments("judge.jobs.dead") == {
        "x-queue-type": "quorum",
        "x-delivery-limit": 3,
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": "judge.jobs.dead",
    }


def test_publish_submission_job_properties(jq, names, raw):
    jq.publish_submission_job(job())
    ch = raw.channel()
    method, props, body = get_one(ch, names["jobs_queue"])
    ch.basic_ack(method.delivery_tag)
    ch.close()
    assert runner_pb2.ExecuteJob.FromString(body) == job()
    assert props.content_type == "application/x-protobuf"
    assert props.type == "oj.v1.ExecuteJob"
    assert props.delivery_mode == 2
    assert props.correlation_id == "submission-7"
    assert props.reply_to == names["events_queue"]
    assert props.expiration is None


def test_queue_stats(jq, names, raw):
    assert jq.queue_stats() == (0, 0)
    jq.publish_submission_job(job())
    jq.publish_submission_job(job("submission-8", 8))
    assert jq.queue_stats() == (2, 0)
    ch = raw.channel()
    ch.basic_qos(prefetch_count=1)
    tag = ch.basic_consume(names["jobs_queue"], lambda *_: None)  # holds one job unacked
    wait_until(lambda: (raw.process_data_events(0), jq.queue_stats())[1] == (1, 1), what="consumer")
    ch.basic_cancel(tag)
    ch.close()


def fake_runner(names, result: runner_pb2.ExecuteResult, seen: list, *, raw_url=URL):
    """Consume one job and answer like a runner: `started`, then `finished`, to reply_to."""
    conn = pika.BlockingConnection(pika.URLParameters(raw_url))
    ch = conn.channel()
    method, props, body = get_one(ch, names["jobs_queue"], timeout=10)
    seen.append(props)
    received = runner_pb2.ExecuteJob.FromString(body)
    for kw in ({"started": runner_pb2.JobStarted()}, {"finished": result}):
        event = runner_pb2.JobEvent(job_id=received.job_id, submission_id=received.submission_id, **kw)
        ch.basic_publish(
            "",
            props.reply_to,
            event.SerializeToString(),
            pika.BasicProperties(
                content_type="application/x-protobuf",
                type="oj.v1.JobEvent",
                correlation_id=props.correlation_id,
                delivery_mode=2,
            ),
        )
    ch.basic_ack(method.delivery_tag)
    conn.close()
    return received


def test_run_job_rpc(jq, names):
    result = runner_pb2.ExecuteResult(
        status=runner_pb2.EXECUTE_STATUS_OK,
        results=[runner_pb2.TestRun(id="custom", status=types_pb2.RUN_STATUS_OK, stdout="1\n")],
    )
    seen = []
    runner = threading.Thread(target=fake_runner, args=(names, result, seen))
    runner.start()
    got = jq.run_job(job("3f1c-run", 0), timeout_s=10)
    runner.join()
    assert got == result
    assert seen[0].reply_to.startswith(names["reply_queue_prefix"])
    assert len(seen[0].reply_to) == len(names["reply_queue_prefix"]) + 32  # judge.rpc.<uuid hex>
    assert seen[0].correlation_id == "3f1c-run"
    assert seen[0].expiration == "10000"


def test_run_job_times_out_and_late_replies_are_ignored(jq, names):
    with pytest.raises(Timeout, match=r"0\.3s"):
        jq.run_job(job("never-answered", 0), timeout_s=0.3)
    # The stale job is still queued; answering it now must not leak into the next run.
    late = runner_pb2.ExecuteResult(status=runner_pb2.EXECUTE_STATUS_OK)
    fake_runner(names, late, [])
    result = runner_pb2.ExecuteResult(status=runner_pb2.EXECUTE_STATUS_COMPILATION_ERROR, compile_output="x")
    runner = threading.Thread(target=fake_runner, args=(names, result, []))
    runner.start()
    assert jq.run_job(job("second", 0), timeout_s=10) == result
    runner.join()


def test_each_thread_has_its_own_connection_and_reply_queue(jq, names):
    reply_queues, errors = set(), []

    def run(i):
        try:
            res = runner_pb2.ExecuteResult(status=runner_pb2.EXECUTE_STATUS_OK, compile_output=str(i))
            seen = []
            runner = threading.Thread(target=fake_runner, args=(names, res, seen))
            runner.start()
            jq.run_job(job(f"run-{i}", 0), timeout_s=10)
            runner.join()
            reply_queues.add(seen[0].reply_to)
        except Exception as exc:  # noqa: BLE001 - collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(reply_queues) == 4


def test_reconnects_after_the_connection_dies(jq, names, raw):
    jq.publish_submission_job(job())
    import socket

    sock = jq._local.session.connection._impl._transport._sock
    sock.shutdown(socket.SHUT_RDWR)  # simulate a dropped TCP connection
    jq.publish_submission_job(job("submission-8", 8))
    assert jq.queue_stats()[0] == 2


def test_unreachable_broker_is_unavailable():
    q = JobQueue("amqp://guest:guest@127.0.0.1:1/")
    with pytest.raises(Unavailable, match="RabbitMQ unavailable"):
        q.publish_submission_job(job())
    with pytest.raises(Unavailable):
        q.queue_stats()
    with pytest.raises(Unavailable):
        q.run_job(job("x", 0), timeout_s=1)


@pytest.fixture
def consuming(jq, names):
    """Run JobQueue.consume in a thread with the given handlers; stop it at the end."""
    stop = threading.Event()
    threads = []

    def start(handlers, **kw):
        t = threading.Thread(
            target=jq.consume, args=(handlers,), kwargs={"stop": stop, "tick_s": 0.1, **kw}, daemon=True
        )
        t.start()
        threads.append(t)

    yield start
    stop.set()
    for t in threads:
        t.join(5)


def test_consume_ack_and_requeue(consuming, names, raw):
    calls = []

    def handler(body: bytes) -> bool:
        calls.append(body)
        return len(calls) > 1  # first delivery: "database down" -> requeue; then ack

    consuming({names["events_queue"]: handler}, requeue_delay_s=0.1)
    raw.channel().basic_publish("", names["events_queue"], b"evt")
    wait_until(lambda: len(calls) >= 2, what="redelivery")
    time.sleep(0.3)
    assert calls == [b"evt", b"evt"]
    assert message_count(raw, names["events_queue"]) == 0


def test_handler_error_drops_the_message(consuming, names, raw):
    calls = []

    def handler(body: bytes) -> bool:
        calls.append(body)
        raise RuntimeError("bug")

    consuming({names["events_queue"]: handler})
    raw.channel().basic_publish("", names["events_queue"], b"poison")
    wait_until(lambda: calls, what="delivery")
    time.sleep(0.3)
    assert calls == [b"poison"]
    assert message_count(raw, names["events_queue"]) == 0


def test_rejected_jobs_are_dead_lettered(jq, consuming, names, raw):
    """A job that keeps failing (runner crash) lands in judge.jobs.dead after x-delivery-limit."""
    dead = []

    def on_dead(body: bytes) -> bool:
        dead.append(runner_pb2.ExecuteJob.FromString(body))
        return True

    consuming({names["dead_queue"]: on_dead})
    jq.publish_submission_job(job())
    for _ in range(4):  # first delivery + 3 redeliveries; each time the "runner" dies holding the job
        ch = raw.channel()
        get_one(ch, names["jobs_queue"])
        ch.close()  # unacked -> returned to the queue, delivery count + 1
    wait_until(lambda: dead, what="dead letter")
    assert dead[0].submission_id == 7
    assert message_count(raw, names["jobs_queue"]) == 0


# ---------- the worker wired to a real broker (fake persistence) ----------


@pytest.fixture
def worker_env(names, raw, tmp_path):
    """A JobQueue for the api side plus a running Worker sharing the same queues."""
    store = FakeStore()
    settings = Settings(
        rabbitmq_url=URL, requeue_delay_s=0.1, worker_health_file=str(tmp_path / "healthy"), **names
    )
    api_queue = JobQueue(URL, **names)
    api_repos = fake_repositories(store, api_queue)
    worker = Worker(settings, fake_repositories(store, JobQueue(URL, **names)))
    thread = threading.Thread(target=worker.run, kwargs={"recover": False}, daemon=True)
    thread.start()
    wait_until(lambda: healthcheck(settings.worker_health_file), what="worker health file")
    from app.services import build_services

    yield store, build_services(settings, api_repos), worker, settings
    worker.stop()
    thread.join(10)
    api_queue.close()


def wait_for_status(store, sid, status, timeout=10.0):
    wait_until(lambda: store.submissions[sid].status == status, timeout, f"status {status}")
    return store.submissions[sid]


def test_submission_judged_end_to_end(worker_env, names):
    store, services, _, _ = worker_env
    p, cases = seed_problem(store)
    sub = services.submissions.submit(
        judge_pb2.SubmitRequest(problem_id=p.id, language=types_pb2.LANGUAGE_PYTHON, source="x")
    ).submission
    result = runner_pb2.ExecuteResult(
        status=runner_pb2.EXECUTE_STATUS_OK,
        results=[
            runner_pb2.TestRun(id=str(c.id), status=types_pb2.RUN_STATUS_OK, stdout=out)
            for c, out in zip(cases, ["2", "11"], strict=True)
        ],
    )
    fake_runner(names, result, [])
    stored = wait_for_status(store, sub.id, types_pb2.SUBMISSION_STATUS_FINISHED)
    assert (stored.verdict, stored.passed, stored.message) == (
        types_pb2.VERDICT_WRONG_ANSWER,
        1,
        "Wrong Answer on test 2",
    )


def test_dead_lettered_submission_fails(worker_env, names, raw):
    store, services, _, _ = worker_env
    p, _ = seed_problem(store)
    sub = services.submissions.submit(
        judge_pb2.SubmitRequest(problem_id=p.id, language=types_pb2.LANGUAGE_C, source="x")
    ).submission
    for _ in range(4):
        ch = raw.channel()
        get_one(ch, names["jobs_queue"])
        ch.close()
    stored = wait_for_status(store, sub.id, types_pb2.SUBMISSION_STATUS_FAILED)
    assert stored.message == "Judging failed: runner crashed or job expired"


def test_events_requeued_while_database_down(worker_env, names, raw):
    store, _, _, _ = worker_env
    p, _ = seed_problem(store)
    sub = store.create_submission(types_pb2.Submission(problem_id=p.id, language=1, source="x"))
    store.down = True
    event = runner_pb2.JobEvent(job_id="submission-x", submission_id=sub.id, started=runner_pb2.JobStarted())
    raw.channel().basic_publish("", names["events_queue"], event.SerializeToString())
    time.sleep(0.5)  # a few nack/requeue rounds
    store.down = False
    wait_for_status(store, sub.id, types_pb2.SUBMISSION_STATUS_JUDGING)


def test_worker_recovery_republishes_stale_submissions(names, raw, tmp_path):
    store = FakeStore()
    p, _ = seed_problem(store)
    sub = store.create_submission(types_pb2.Submission(problem_id=p.id, language=1, source="x"))
    settings = Settings(rabbitmq_url=URL, worker_health_file=str(tmp_path / "h"), recover_after_s=60, **names)
    worker = Worker(settings, fake_repositories(store, JobQueue(URL, **names)))
    worker.repositories.queue.connect()  # declare the queues before polling them
    thread = threading.Thread(target=worker.run, daemon=True)  # recover=True
    thread.start()
    try:
        ch = raw.channel()
        method, props, body = get_one(ch, names["jobs_queue"], timeout=10)
        ch.basic_ack(method.delivery_tag)
        assert runner_pb2.ExecuteJob.FromString(body).submission_id == sub.id
        assert props.reply_to == names["events_queue"]
    finally:
        worker.stop()
        thread.join(10)
    assert not os.path.exists(settings.worker_health_file)  # removed on shutdown
