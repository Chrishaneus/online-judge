import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fakes import FakeDao, FakeRunner

PROBLEM = {
    "slug": "double-it",
    "title": "Double it",
    "statement": "Print 2*n",
    "difficulty": "easy",
    "time_limit_ms": 1000,
    "memory_limit_mb": 64,
    "test_cases": [
        {"input": "1", "expected_output": "2", "is_sample": True},
        {"input": "21", "expected_output": "42"},
    ],
}


@pytest.fixture
def env():
    dao, runner = FakeDao(), FakeRunner()
    app = create_app(Settings(judge_workers=2), dao=dao, runner=runner)
    with TestClient(app) as client:
        yield client, dao, runner


def wait_finished(client, sid, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        sub = client.get(f"/submissions/{sid}").json()
        if sub["status"] in ("FINISHED", "FAILED"):
            return sub
        time.sleep(0.02)
    raise AssertionError("submission was not judged in time")


def test_health_and_ready(env):
    client, dao, _ = env
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200
    dao.down = True
    r = client.get("/readyz")
    assert r.status_code == 503 and r.json()["dao"].startswith("error")


def test_create_and_get_problem_hides_hidden_tests(env):
    client, _, _ = env
    r = client.post("/problems", json=PROBLEM)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    detail = client.get(f"/problems/{pid}").json()
    assert detail["samples"] == [{"input": "1", "output": "2"}]
    assert "test_cases" not in detail

    summaries = client.get("/problems").json()
    assert summaries[0]["slug"] == "double-it" and "statement" not in summaries[0]

    assert len(client.get(f"/problems/{pid}/testcases").json()) == 2
    assert client.post("/problems", json=PROBLEM).status_code == 409


@pytest.mark.parametrize(
    "patch",
    [
        {"slug": "Bad Slug"},
        {"difficulty": "impossible"},
        {"time_limit_ms": 50},
        {"test_cases": []},
        {"unknown": 1},
    ],
)
def test_create_problem_validation(env, patch):
    client, _, _ = env
    assert client.post("/problems", json={**PROBLEM, **patch}).status_code == 422


def test_create_problem_rolls_back_on_testcase_failure(env):
    client, dao, _ = env

    async def broken(*a, **k):
        raise RuntimeError("disk full")

    dao.create_testcase = broken
    with pytest.raises(RuntimeError):
        client.post("/problems", json=PROBLEM)
    assert dao.problems == {}


def test_update_and_delete_problem(env):
    client, _, _ = env
    pid = client.post("/problems", json=PROBLEM).json()["id"]
    body = {k: v for k, v in PROBLEM.items() if k != "test_cases"} | {"title": "Twice"}
    assert client.put(f"/problems/{pid}", json=body).json()["title"] == "Twice"
    assert client.delete(f"/problems/{pid}").status_code == 204
    assert client.get(f"/problems/{pid}").status_code == 404


def test_testcase_admin(env):
    client, _, _ = env
    pid = client.post("/problems", json=PROBLEM).json()["id"]
    tc = client.post(f"/problems/{pid}/testcases", json={"input": "3", "expected_output": "6"}).json()
    assert tc["ordinal"] == 3
    assert client.delete(f"/problems/{pid}/testcases/{tc['id']}").status_code == 204
    assert client.delete(f"/problems/{pid}/testcases/{tc['id']}").status_code == 404


@pytest.mark.parametrize("source,verdict,passed", [("double", "AC", 2), ("echo", "WA", 0), ("ce", "CE", 0)])
def test_submit_and_judge(env, source, verdict, passed):
    client, _, _ = env
    pid = client.post("/problems", json=PROBLEM).json()["id"]
    r = client.post("/submissions", json={"problem_id": pid, "language": "python", "source": source, "username": "alice"})
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "PENDING"

    sub = wait_finished(client, r.json()["id"])
    assert (sub["verdict"], sub["passed"], sub["total"]) == (verdict, passed, 2)
    if verdict != "CE":
        assert [t["sample"] for t in sub["results"]] == [True, False]

    listing = client.get("/submissions", params={"username": "alice"}).json()
    assert len(listing) == 1 and "source" not in listing[0]


def test_submit_validation(env):
    client, _, _ = env
    pid = client.post("/problems", json=PROBLEM).json()["id"]
    ok = {"problem_id": pid, "language": "python", "source": "double"}
    assert client.post("/submissions", json={**ok, "language": "brainfuck"}).status_code == 422
    assert client.post("/submissions", json={**ok, "problem_id": 999}).status_code == 404
    assert client.post("/submissions", json={**ok, "username": "has space"}).status_code == 422
    assert client.post("/submissions", json={**ok, "source": ""}).status_code == 422


def test_run_custom_input(env):
    client, _, runner = env
    r = client.post("/run", json={"language": "python", "source": "echo", "stdin": "hi"})
    assert r.status_code == 200
    assert r.json()["stdout"] == "hi" and r.json()["status"] == "OK"
    assert client.post("/run", json={"language": "python", "source": "ce"}).json()["status"] == "CE"


def test_runner_outage_returns_503(env):
    client, _, _ = env
    assert client.post("/run", json={"language": "python", "source": "boom"}).status_code == 503


def test_languages(env):
    client, _, _ = env
    assert [lang["id"] for lang in client.get("/languages").json()] == ["python", "cpp"]
