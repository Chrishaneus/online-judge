"""HTTP through the real services with fake repositories (ported from midlayer's gRPC functional tests):
problem CRUD, submissions, custom runs, status, and how domain errors surface as HTTP."""

from app.gen.oj.v1 import runner_pb2, types_pb2
from tests.fakes import seed_problem

T = types_pb2


def test_status_and_languages(client, queue):
    queue.depth, queue.consumers = 3, 2
    body = client.get("/api/v1/status").get_json()
    assert body == {"healthy": True, "database": "ok", "broker": "ok", "queueDepth": "3", "runners": 2}
    queue.down = True
    body = client.get("/api/v1/status").get_json()
    assert body["healthy"] is False and body["broker"].startswith("error: RabbitMQ unavailable")
    langs = client.get("/api/v1/languages").get_json()["languages"]
    assert langs[0] == {"language": "LANGUAGE_PYTHON", "name": "Python 3"}
    assert len(langs) == 4


def test_status_never_fails_when_everything_is_down(client, store, queue):
    store.down = queue.down = True
    res = client.get("/api/v1/status")
    assert res.status_code == 200
    body = res.get_json()
    assert body["healthy"] is False
    assert body["database"].startswith("error: database unavailable")


def test_problem_crud_and_error_codes(client, auth):
    body = {
        "slug": "sum",
        "title": "Sum",
        "testCases": [
            {"input": "1 2", "expectedOutput": "3", "isSample": True},
            {"input": "2 2", "expectedOutput": "4"},
        ],
    }
    res = client.post("/api/v1/admin/problems", json=body, headers=auth)
    assert res.status_code == 201
    created = res.get_json()["problem"]
    assert created["samples"] == [{"input": "1 2", "output": "3"}]
    assert (created["difficulty"], created["timeLimitMs"], created["memoryLimitMb"]) == (
        "DIFFICULTY_EASY",
        2000,
        256,
    )
    pid = created["id"]
    assert isinstance(pid, str)

    detail = client.get(f"/api/v1/problems/{pid}").get_json()["problem"]
    assert len(detail["samples"]) == 1 and "testCases" not in detail
    summaries = client.get("/api/v1/problems").get_json()["problems"]
    assert [p["slug"] for p in summaries] == ["sum"]
    assert "statement" not in summaries[0]

    res = client.post("/api/v1/admin/problems", json=body, headers=auth)
    assert res.status_code == 409 and "already exists" in res.get_json()["error"]
    res = client.post("/api/v1/admin/problems", json={**body, "slug": "Bad Slug"}, headers=auth)
    assert res.status_code == 422 and "slug" in res.get_json()["error"]
    assert client.get("/api/v1/problems/999").status_code == 404

    res = client.post(
        f"/api/v1/admin/problems/{pid}/testcases",
        json={"testCase": {"input": "5 5", "expectedOutput": "10"}},
        headers=auth,
    )
    assert res.status_code == 201
    tc = res.get_json()["testCase"]
    assert (tc["ordinal"], tc["problemId"], tc["isSample"]) == (3, pid, False)
    cases = client.get(f"/api/v1/admin/problems/{pid}/testcases", headers=auth).get_json()["testCases"]
    assert [c["expectedOutput"] for c in cases] == ["3", "4", "10"]  # admins see hidden tests
    res = client.delete(f"/api/v1/admin/problems/{pid}/testcases/{tc['id']}", headers=auth)
    assert (res.status_code, res.data) == (204, b"")
    assert (
        client.delete(f"/api/v1/admin/problems/{pid}/testcases/{tc['id']}", headers=auth).status_code == 404
    )
    assert client.get("/api/v1/admin/problems/999/testcases", headers=auth).status_code == 404
    assert client.post("/api/v1/admin/problems/999/testcases", json={}, headers=auth).status_code == 404

    res = client.put(f"/api/v1/admin/problems/{pid}", json={"slug": "sum2", "title": "Sum 2"}, headers=auth)
    assert res.status_code == 200
    assert res.get_json()["problem"]["slug"] == "sum2"
    assert client.delete(f"/api/v1/admin/problems/{pid}", headers=auth).status_code == 204
    assert client.delete(f"/api/v1/admin/problems/{pid}", headers=auth).status_code == 404
    assert client.get(f"/api/v1/problems/{pid}").status_code == 404


def test_add_problem_validation_names_the_field(client, auth):
    res = client.post("/api/v1/admin/problems", json={"slug": "x", "title": "X"}, headers=auth)
    assert res.status_code == 422 and "test_cases" in res.get_json()["error"]
    res = client.post(
        "/api/v1/admin/problems",
        json={"slug": "x", "title": "X", "timeLimitMs": 50, "testCases": [{}]},
        headers=auth,
    )
    assert res.status_code == 422 and "time_limit_ms" in res.get_json()["error"]


def test_submit_and_queue_errors(client, store, queue):
    p, _ = seed_problem(store)
    ok = {"problemId": str(p.id), "language": "LANGUAGE_PYTHON", "source": "print(1)"}
    res = client.post("/api/v1/submissions", json=ok)
    assert res.status_code == 202
    sub = res.get_json()["submission"]
    assert sub["status"] == "SUBMISSION_STATUS_PENDING" and sub["username"] == "anonymous"
    assert sub["verdict"] == "VERDICT_UNSPECIFIED" and sub["results"] == []
    assert queue.published[0].job_id == f"submission-{sub['id']}"

    listed = client.get("/api/v1/submissions").get_json()["submissions"]
    assert listed[0]["source"] == "" and listed[0]["id"] == sub["id"]
    detail = client.get(f"/api/v1/submissions/{sub['id']}").get_json()["submission"]
    assert detail["source"] == "print(1)"
    assert client.get("/api/v1/submissions/999").status_code == 404

    assert client.post("/api/v1/submissions", json={**ok, "problemId": "999"}).status_code == 404
    res = client.post("/api/v1/submissions", json={"problemId": str(p.id), "source": "x"})
    assert res.status_code == 422 and "language" in res.get_json()["error"]
    res = client.post("/api/v1/submissions", json={**ok, "username": "a b"})
    assert res.status_code == 422 and "username" in res.get_json()["error"]
    assert client.get("/api/v1/submissions?limit=500").status_code == 422

    queue.depth = 1000
    assert client.post("/api/v1/submissions", json=ok).status_code == 429
    queue.depth, queue.down = 0, True
    assert client.post("/api/v1/submissions", json=ok).status_code == 503
    queue.down, store.down = False, True
    res = client.post("/api/v1/submissions", json=ok)
    assert (res.status_code, res.get_json()["error"]) == (503, "service unavailable")


def test_list_submissions_filters_and_paging(client, store):
    p1, _ = seed_problem(store, slug="one")
    p2, _ = seed_problem(store, slug="two")
    for pid, user in ((p1.id, "ann"), (p1.id, "bob"), (p2.id, "ann")):
        body = {"problemId": pid, "language": "LANGUAGE_C", "source": "x", "username": user}
        assert client.post("/api/v1/submissions", json=body).status_code == 202

    def users(query):
        return [
            (s["problemId"], s["username"])
            for s in client.get(f"/api/v1/submissions{query}").get_json()["submissions"]
        ]

    assert users("") == [(str(p2.id), "ann"), (str(p1.id), "bob"), (str(p1.id), "ann")]
    assert users(f"?problemId={p1.id}") == [(str(p1.id), "bob"), (str(p1.id), "ann")]
    assert users(f"?problem_id={p2.id}&username=ann") == [(str(p2.id), "ann")]
    assert users("?username=ann&limit=1&offset=1") == [(str(p1.id), "ann")]


def test_run_code(client, queue, store):
    queue.run_result = runner_pb2.ExecuteResult(
        status=runner_pb2.EXECUTE_STATUS_OK,
        results=[
            runner_pb2.TestRun(
                id="custom", status=T.RUN_STATUS_OK, stdout="1\n", time_ms=5, memory_kb=1234, exit_code=0
            )
        ],
    )
    res = client.post("/api/v1/run", json={"language": "LANGUAGE_JAVASCRIPT", "source": "console.log(1)"})
    assert res.status_code == 200
    assert res.get_json() == {
        "status": "RUN_STATUS_OK",
        "compileOutput": "",
        "stdout": "1\n",
        "stderr": "",
        "exitCode": 0,
        "timeMs": 5,
        "memoryKb": "1234",
    }
    queue.run_result = runner_pb2.ExecuteResult(
        status=runner_pb2.EXECUTE_STATUS_COMPILATION_ERROR, compile_output="boom"
    )
    body = client.post("/api/v1/run", json={"language": "LANGUAGE_C", "source": "x"}).get_json()
    assert (body["status"], body["compileOutput"]) == ("RUN_STATUS_COMPILATION_ERROR", "boom")

    from app.errors import Timeout

    queue.run_result = Timeout("No runner answered within 30s")
    res = client.post("/api/v1/run", json={"language": "LANGUAGE_C", "source": "x"})
    assert (res.status_code, res.get_json()["error"]) == (504, "No runner answered within 30s")
    res = client.post("/api/v1/run", json={"language": "LANGUAGE_UNSPECIFIED", "source": "x"})
    assert res.status_code == 422
    assert (
        client.post("/api/v1/run", json={"language": "LANGUAGE_C", "source": "x", "problemId": 9}).status_code
        == 404
    )


def test_unexpected_repository_error_is_500_without_details(client, store):
    def boom():
        raise RuntimeError("secret detail")

    store.list_problems = boom
    res = client.get("/api/v1/problems")
    assert res.status_code == 500
    assert res.get_json() == {"error": "internal error", "details": []}


def test_large_admin_bodies_up_to_64_mib(client, store, auth):
    p, _ = seed_problem(store)
    big = "x" * (5 * 1024 * 1024)
    res = client.post(
        f"/api/v1/admin/problems/{p.id}/testcases",
        json={"testCase": {"input": big, "expectedOutput": big}},
        headers=auth,
    )
    assert res.status_code == 201
    assert len(res.get_json()["testCase"]["input"]) == len(big)
