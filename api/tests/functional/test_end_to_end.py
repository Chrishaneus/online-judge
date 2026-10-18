"""The real wiring end to end: Flask app + worker with the real repositories on Postgres and RabbitMQ,
a fake runner in between. Needs both TEST_DATABASE_URL and RABBITMQ_TEST_URL."""

import os
import threading
import time
import uuid

import pytest
from sqlalchemy import text

from app import create_app
from app.config import Settings
from app.gen.oj.v1 import runner_pb2, types_pb2
from app.repositories import Repositories
from app.worker import Worker, healthcheck
from tests.functional.test_broker import fake_runner, wait_until

DB_URL = os.environ.get("TEST_DATABASE_URL")
MQ_URL = os.environ.get("RABBITMQ_TEST_URL")
pytestmark = pytest.mark.skipif(
    not (DB_URL and MQ_URL), reason="TEST_DATABASE_URL and RABBITMQ_TEST_URL not both set"
)

TOKEN = "e2e-admin-token-0123456789"


@pytest.fixture
def stack(tmp_path):
    prefix = f"test-e2e-{uuid.uuid4().hex[:8]}."
    names = {
        "jobs_queue": prefix + "judge.jobs",
        "dead_queue": prefix + "judge.jobs.dead",
        "events_queue": prefix + "judge.events",
        "reply_queue_prefix": prefix + "judge.rpc.",
    }
    settings = Settings(
        database_url=DB_URL,
        rabbitmq_url=MQ_URL,
        admin_token=TOKEN,
        worker_health_file=str(tmp_path / "healthy"),
        requeue_delay_s=0.1,
        **names,
    )
    api_repos = Repositories.from_settings(settings)
    api_repos.database.migrate()
    with api_repos.database.begin() as conn:
        conn.execute(text("TRUNCATE problems, test_cases, submissions RESTART IDENTITY CASCADE"))
    app = create_app(settings, api_repos)
    worker = Worker(settings, Repositories.from_settings(settings))
    thread = threading.Thread(target=worker.run, daemon=True)
    thread.start()
    wait_until(lambda: healthcheck(settings.worker_health_file), what="worker")
    yield app.test_client(), names
    worker.stop()
    thread.join(10)
    api_repos.queue.close()
    api_repos.database.dispose()
    worker.repositories.database.dispose()
    import pika

    conn = pika.BlockingConnection(pika.URLParameters(MQ_URL))
    ch = conn.channel()
    for key in ("jobs_queue", "dead_queue", "events_queue"):
        ch.queue_delete(names[key])
    conn.close()


def test_submit_judge_and_run(stack):
    client, names = stack
    auth = {"Authorization": f"Bearer {TOKEN}"}
    res = client.post(
        "/api/v1/admin/problems",
        json={
            "slug": "square",
            "title": "Square",
            "difficulty": "DIFFICULTY_MEDIUM",
            "testCases": [
                {"input": "3", "expectedOutput": "9", "isSample": True},
                {"input": "12", "expectedOutput": "144"},
            ],
        },
        headers=auth,
    )
    assert res.status_code == 201, res.get_json()
    pid = res.get_json()["problem"]["id"]

    status = client.get("/api/v1/status").get_json()
    assert (status["healthy"], status["database"], status["broker"]) == (True, "ok", "ok")

    res = client.post(
        "/api/v1/submissions",
        json={
            "problemId": pid,
            "language": "LANGUAGE_PYTHON",
            "source": "print(int(input())**2)",
            "username": "e2e",
        },
    )
    assert res.status_code == 202, res.get_json()
    sid = res.get_json()["submission"]["id"]
    assert client.get("/api/v1/status").get_json()["queueDepth"] == "1"

    cases = client.get(f"/api/v1/admin/problems/{pid}/testcases", headers=auth).get_json()["testCases"]
    result = runner_pb2.ExecuteResult(
        status=runner_pb2.EXECUTE_STATUS_OK,
        results=[
            runner_pb2.TestRun(
                id=c["id"], status=types_pb2.RUN_STATUS_OK, stdout=c["expectedOutput"] + "\n", time_ms=7
            )
            for c in cases
        ],
    )
    job = fake_runner(names, result, [])
    assert [t.stdin for t in job.tests] == ["3", "12"]

    def judged():
        return client.get(f"/api/v1/submissions/{sid}").get_json()["submission"]

    wait_until(lambda: judged()["status"] == "SUBMISSION_STATUS_FINISHED", what="verdict")
    sub = judged()
    assert (sub["verdict"], sub["passed"], sub["total"], sub["timeMs"], sub["message"]) == (
        "VERDICT_ACCEPTED",
        2,
        2,
        7,
        "All tests passed",
    )
    assert [r["sample"] for r in sub["results"]] == [True, False]
    listed = client.get(f"/api/v1/submissions?problemId={pid}&username=e2e").get_json()["submissions"]
    assert [s["id"] for s in listed] == [sid] and listed[0]["results"] == []

    # Custom run through the RPC reply queue.
    runner = threading.Thread(
        target=fake_runner,
        args=(
            names,
            runner_pb2.ExecuteResult(
                status=runner_pb2.EXECUTE_STATUS_OK,
                results=[runner_pb2.TestRun(id="custom", status=types_pb2.RUN_STATUS_OK, stdout="hi\n")],
            ),
            [],
        ),
    )
    runner.start()
    res = client.post("/api/v1/run", json={"language": "LANGUAGE_C", "source": "x", "problemId": pid})
    runner.join()
    assert (res.status_code, res.get_json()["stdout"]) == (200, "hi\n")


def test_dead_letter_marks_failed(stack):
    client, names = stack
    import pika

    auth = {"Authorization": f"Bearer {TOKEN}"}
    pid = client.post(
        "/api/v1/admin/problems",
        json={"slug": "dl", "title": "DL", "testCases": [{"input": "1", "expectedOutput": "1"}]},
        headers=auth,
    ).get_json()["problem"]["id"]
    sid = client.post(
        "/api/v1/submissions", json={"problemId": pid, "language": "LANGUAGE_CPP", "source": "x"}
    ).get_json()["submission"]["id"]
    conn = pika.BlockingConnection(pika.URLParameters(MQ_URL))
    for _ in range(4):  # the runner "crashes" holding the job each time
        ch = conn.channel()
        deadline = time.monotonic() + 5
        while ch.basic_get(names["jobs_queue"])[0] is None and time.monotonic() < deadline:
            time.sleep(0.05)
        ch.close()
    conn.close()
    wait_until(
        lambda: (
            client.get(f"/api/v1/submissions/{sid}").get_json()["submission"]["status"]
            == "SUBMISSION_STATUS_FAILED"
        ),
        what="FAILED",
    )
    sub = client.get(f"/api/v1/submissions/{sid}").get_json()["submission"]
    assert (sub["verdict"], sub["message"]) == (
        "VERDICT_INTERNAL_ERROR",
        "Judging failed: runner crashed or job expired",
    )
