import asyncio
import json

import httpx
import pytest

from app.clients import Conflict, DaoClient, NotFound, RunnerClient, Unavailable, UpstreamError


def dao_with(handler) -> DaoClient:
    return DaoClient(httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://dao"))


def test_success_and_query_params():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        return httpx.Response(200, json=[{"id": 1}])

    out = asyncio.run(dao_with(handler).list_submissions(problem_id=3, username="", status=None))
    assert out == [{"id": 1}]
    assert seen["url"] == "http://dao/submissions?problem_id=3"


@pytest.mark.parametrize(
    "status,exc",
    [(404, NotFound), (409, Conflict), (400, UpstreamError), (500, UpstreamError)],
)
def test_error_mapping(status, exc):
    dao = dao_with(lambda req: httpx.Response(status, json={"error": "nope"}))
    with pytest.raises(exc) as info:
        asyncio.run(dao.get_problem(1))
    assert info.value.detail == "nope"
    assert info.value.status == status


def test_no_content():
    dao = dao_with(lambda req: httpx.Response(204))
    assert asyncio.run(dao.delete_problem(1)) is None


def test_transport_error_is_unavailable():
    def handler(req):
        raise httpx.ConnectError("refused", request=req)

    with pytest.raises(Unavailable):
        asyncio.run(dao_with(handler).list_problems())


def test_runner_execute_payload():
    body = {}

    def handler(req: httpx.Request) -> httpx.Response:
        body.update(json.loads(req.content))
        return httpx.Response(200, json={"status": "OK", "results": []})

    runner = RunnerClient(httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://r"))
    asyncio.run(runner.execute("python", "print(1)", [{"id": "1", "stdin": ""}], 1000, 64))
    assert body == {
        "language": "python",
        "source": "print(1)",
        "tests": [{"id": "1", "stdin": ""}],
        "time_limit_ms": 1000,
        "memory_limit_mb": 64,
    }
