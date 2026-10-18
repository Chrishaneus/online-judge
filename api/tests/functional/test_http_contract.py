"""The public HTTP contract (ported from rest's gateway/middleware tests): routes -> request messages,
status codes, canonical proto JSON, error shapes and mapping, admin auth, rate limit, body limits,
request ids, CORS. Services are replaced by a recorder so each route's exact request message is
checked; flows through the real services are in test_api_flows.py."""

import io
import logging

import pytest
from google.protobuf import json_format
from google.protobuf.timestamp_pb2 import Timestamp

from app import create_app
from app.config import Settings
from app.controllers.http import MAX_SUBMISSION_BODY
from app.errors import (
    AppError,
    Conflict,
    NotFound,
    PreconditionFailed,
    QueueFull,
    Timeout,
    Unavailable,
    ValidationError,
)
from app.gen.oj.v1 import judge_pb2, types_pb2
from tests.conftest import ADMIN_TOKEN
from tests.fakes import FakeQueue, FakeStore, fake_repositories

T = types_pb2


class RecordingServices:
    """Stands in for app.services.Services: records (method, request), returns a canned or empty
    response, or raises `error`."""

    def __init__(self):
        self.calls: list[tuple[str, object]] = []
        self.responses: dict[str, object] = {}
        self.error: Exception | None = None

    def __getattr__(self, group):
        recorder = self

        class Group:
            def __getattr__(self, method):
                def call(req):
                    recorder.calls.append((method, req))
                    if recorder.error is not None:
                        raise recorder.error
                    if method in recorder.responses:
                        return recorder.responses[method]
                    return getattr(judge_pb2, type(req).__name__.replace("Request", "Response"))()

                return call

        return Group()

    def last(self):
        return self.calls[-1] if self.calls else (None, None)


def make_client(settings: Settings | None = None):
    settings = settings or Settings(admin_token=ADMIN_TOKEN, rate_limit_per_min=600, rate_limit_burst=100)
    app = create_app(settings, fake_repositories(FakeStore(), FakeQueue()))
    rec = RecordingServices()
    app.extensions["services"] = rec
    return app.test_client(), rec


@pytest.fixture
def gw():
    return make_client()


AUTH = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def call(client, method, path, body="", headers=None, **kw):
    return client.open(path, method=method, data=body, headers=headers or {}, **kw)


def assert_error(res, status=None):
    body = res.get_json()
    assert res.content_type == "application/json", res.data
    assert set(body) == {"error", "details"}, body  # details always present
    assert isinstance(body["details"], list)
    assert body["error"]
    if status is not None:
        assert res.status_code == status, body
    return body


ROUTES = [
    ("GET", "/api/v1/status", "", None, 200, "get_status", judge_pb2.GetStatusRequest()),
    ("GET", "/api/v1/languages", "", None, 200, "list_languages", judge_pb2.ListLanguagesRequest()),
    (
        "GET",
        "/api/v1/problems",
        "",
        None,
        200,
        "list_problem_summaries",
        judge_pb2.ListProblemSummariesRequest(),
    ),
    (
        "GET",
        "/api/v1/problems/12",
        "",
        None,
        200,
        "get_problem_detail",
        judge_pb2.GetProblemDetailRequest(id=12),
    ),
    (
        "POST",
        "/api/v1/submissions",
        '{"problemId":"1","language":"LANGUAGE_PYTHON","source":"print(1)","username":"ann"}',
        None,
        202,
        "submit",
        judge_pb2.SubmitRequest(problem_id=1, language=T.LANGUAGE_PYTHON, source="print(1)", username="ann"),
    ),
    (
        "GET",
        "/api/v1/submissions?problemId=3&username=ann&limit=5&offset=10",
        "",
        None,
        200,
        "list_submission_summaries",
        judge_pb2.ListSubmissionSummariesRequest(problem_id=3, username="ann", limit=5, offset=10),
    ),
    (
        "GET",
        "/api/v1/submissions?problem_id=4",
        "",
        None,
        200,
        "list_submission_summaries",
        judge_pb2.ListSubmissionSummariesRequest(problem_id=4),
    ),
    (
        "GET",
        "/api/v1/submissions/7",
        "",
        None,
        200,
        "get_submission_detail",
        judge_pb2.GetSubmissionDetailRequest(id=7),
    ),
    (
        "POST",
        "/api/v1/run",
        '{"language":"LANGUAGE_C","source":"int main(){}","stdin":"x","problemId":2}',
        None,
        200,
        "run_code",
        judge_pb2.RunCodeRequest(language=T.LANGUAGE_C, source="int main(){}", stdin="x", problem_id=2),
    ),
    (
        "POST",
        "/api/v1/admin/problems",
        '{"slug":"a-b","title":"A","testCases":[{"input":"1","expectedOutput":"2","isSample":true}]}',
        AUTH,
        201,
        "add_problem",
        judge_pb2.AddProblemRequest(
            slug="a-b",
            title="A",
            test_cases=[judge_pb2.NewTestCase(input="1", expected_output="2", is_sample=True)],
        ),
    ),
    # The path id wins over a body id; snake_case is accepted in bodies too.
    (
        "PUT",
        "/api/v1/admin/problems/4",
        '{"id":"99","title":"T","difficulty":"DIFFICULTY_HARD","time_limit_ms":500}',
        AUTH,
        200,
        "edit_problem",
        judge_pb2.EditProblemRequest(id=4, title="T", difficulty=T.DIFFICULTY_HARD, time_limit_ms=500),
    ),
    (
        "DELETE",
        "/api/v1/admin/problems/4",
        "",
        AUTH,
        204,
        "remove_problem",
        judge_pb2.RemoveProblemRequest(id=4),
    ),
    (
        "GET",
        "/api/v1/admin/problems/4/testcases",
        "",
        AUTH,
        200,
        "list_problem_test_cases",
        judge_pb2.ListProblemTestCasesRequest(problem_id=4),
    ),
    (
        "POST",
        "/api/v1/admin/problems/4/testcases",
        '{"testCase":{"input":"i","expectedOutput":"o"},"problemId":"77"}',
        AUTH,
        201,
        "add_test_case",
        judge_pb2.AddTestCaseRequest(
            problem_id=4, test_case=judge_pb2.NewTestCase(input="i", expected_output="o")
        ),
    ),
    (
        "DELETE",
        "/api/v1/admin/problems/4/testcases/9",
        "",
        AUTH,
        204,
        "remove_test_case",
        judge_pb2.RemoveTestCaseRequest(problem_id=4, id=9),
    ),
]


@pytest.mark.parametrize("method,path,body,headers,status,service_method,request_msg", ROUTES)
def test_routes_build_requests(gw, method, path, body, headers, status, service_method, request_msg):
    client, rec = gw
    res = call(client, method, path, body, headers, content_type="application/json")
    assert res.status_code == status, res.data
    assert rec.last() == (service_method, request_msg)
    assert len(rec.calls) == 1
    if status == 204:
        assert res.data == b""
        assert "Content-Type" not in res.headers
    else:
        assert res.headers["Content-Type"] == "application/json"
        assert isinstance(res.get_json(), dict)


def test_empty_body_is_empty_message(gw):
    client, rec = gw
    assert call(client, "POST", "/api/v1/submissions").status_code == 202
    assert rec.last() == ("submit", judge_pb2.SubmitRequest())
    assert call(client, "POST", "/api/v1/run", "  \n").status_code == 200


def test_response_json_shape(gw):
    client, rec = gw
    rec.responses["get_submission_detail"] = judge_pb2.GetSubmissionDetailResponse(
        submission=T.Submission(
            id=7,
            problem_id=3,
            language=T.LANGUAGE_PYTHON,
            status=T.SUBMISSION_STATUS_FINISHED,
            verdict=T.VERDICT_ACCEPTED,
            create_time=Timestamp(seconds=1767323045),  # 2026-01-02T03:04:05Z
            update_time=Timestamp(seconds=1767323045, nanos=500_000_000),
            results=[T.TestResult(test=1, verdict=T.VERDICT_ACCEPTED, memory_kb=9000, sample=True)],
        )
    )
    res = call(client, "GET", "/api/v1/submissions/7")
    assert res.status_code == 200
    s = res.get_json()["submission"]
    assert s == {
        "id": "7",
        "problemId": "3",
        "username": "",
        "language": "LANGUAGE_PYTHON",
        "source": "",
        "status": "SUBMISSION_STATUS_FINISHED",
        "verdict": "VERDICT_ACCEPTED",
        "passed": 0,
        "total": 0,
        "timeMs": 0,
        "message": "",
        "results": [
            {"test": 1, "verdict": "VERDICT_ACCEPTED", "timeMs": 0, "memoryKb": "9000", "sample": True}
        ],
        "createTime": "2026-01-02T03:04:05Z",
        "updateTime": "2026-01-02T03:04:05.500Z",
    }


def test_defaults_are_emitted(gw):
    client, rec = gw
    rec.responses["get_status"] = judge_pb2.GetStatusResponse()
    assert call(client, "GET", "/api/v1/status").get_json() == {
        "healthy": False,
        "database": "",
        "broker": "",
        "queueDepth": "0",
        "runners": 0,
    }
    assert call(client, "GET", "/api/v1/problems").get_json() == {"problems": []}


BAD_REQUESTS = [
    ("POST", "/api/v1/submissions", '{"problemId":"1","bogus":true}', None),
    ("POST", "/api/v1/submissions", '{"problemId":', None),
    ("POST", "/api/v1/submissions", '{"language":"COBOL"}', None),
    ("POST", "/api/v1/submissions", '{"problemId":"x"}', None),
    ("POST", "/api/v1/submissions", b"\xff\xfe", None),
    ("POST", "/api/v1/run", "[]", None),
    ("POST", "/api/v1/run", '"text"', None),
    ("GET", "/api/v1/problems/abc", "", None),
    ("GET", "/api/v1/problems/0", "", None),
    ("GET", "/api/v1/problems/-1", "", None),
    ("GET", "/api/v1/problems/01", "", None),
    ("GET", "/api/v1/problems/99999999999999999999", "", None),
    ("GET", "/api/v1/submissions/1.5", "", None),
    ("GET", "/api/v1/submissions?problemId=x", "", None),
    ("GET", "/api/v1/submissions?problem_id=0", "", None),
    ("GET", "/api/v1/submissions?limit=-1", "", None),
    ("GET", "/api/v1/submissions?limit=abc", "", None),
    ("GET", "/api/v1/submissions?offset=1e3", "", None),
    ("GET", "/api/v1/submissions?offset=99999999999", "", None),
    ("PUT", "/api/v1/admin/problems/x", "{}", AUTH),
    ("PUT", "/api/v1/admin/problems/1", '{"slug": 5}', AUTH),
    ("GET", "/api/v1/admin/problems/x/testcases", "", AUTH),
    ("DELETE", "/api/v1/admin/problems/4/testcases/0", "", AUTH),
    ("DELETE", "/api/v1/admin/problems/x", "", AUTH),
]


@pytest.mark.parametrize("method,path,body,headers", BAD_REQUESTS)
def test_bad_requests_are_400_and_never_reach_services(gw, method, path, body, headers):
    client, rec = gw
    res = call(client, method, path, body, headers)
    assert_error(res, 400)
    assert rec.calls == []


def test_unknown_field_is_named_in_details(gw):
    client, _ = gw
    body = assert_error(call(client, "POST", "/api/v1/submissions", '{"bogus":1}'), 400)
    assert body["error"] == "invalid JSON body"
    assert "bogus" in body["details"][0]


def test_unknown_routes_are_json_404_and_405(gw):
    client, rec = gw
    for path in ("/api/v1/readyz", "/problems", "/api/v2/problems", "/api/v1/problems/", "/"):
        assert assert_error(call(client, "GET", path), 404)["error"] == "not found"
    # Admin-only mutation is not exposed publicly.
    res = call(client, "DELETE", "/api/v1/problems/1")
    assert assert_error(res, 405)["error"] == "method not allowed"
    assert "GET" in res.headers["Allow"]
    assert_error(call(client, "PATCH", "/api/v1/submissions"), 405)
    assert rec.calls == []


ERRORS = [
    (ValidationError("source must not be empty"), 422, "source must not be empty"),
    (NotFound("problem 3 not found"), 404, "problem 3 not found"),
    (Conflict("a problem with slug 'x' already exists"), 409, "a problem with slug 'x' already exists"),
    (PreconditionFailed("status mismatch"), 409, "status mismatch"),
    (
        QueueFull("The judging queue is full, try again later"),
        429,
        "The judging queue is full, try again later",
    ),
    (Timeout("No runner answered within 30s"), 504, "No runner answered within 30s"),
    (Unavailable("database unavailable: OperationalError"), 503, "service unavailable"),
    (AppError("secret detail"), 500, "internal error"),
    (RuntimeError("secret detail"), 500, "internal error"),
]


@pytest.mark.parametrize("error,status,message", ERRORS)
def test_error_mapping(gw, error, status, message):
    client, rec = gw
    rec.error = error
    body = assert_error(call(client, "POST", "/api/v1/submissions", "{}"), status)
    assert body["error"] == message
    assert "secret" not in str(body)


def test_queue_full_has_no_retry_after(gw):
    client, rec = gw
    rec.error = QueueFull("full")
    assert "Retry-After" not in call(client, "POST", "/api/v1/submissions", "{}").headers


def test_unexpected_errors_are_logged_with_request_id(gw, caplog):
    client, rec = gw
    rec.error = RuntimeError("boom")
    caplog.set_level(logging.ERROR, logger="app.http")
    call(client, "GET", "/api/v1/problems", headers={"X-Request-ID": "req-42"})
    assert any("request_id=req-42" in r.getMessage() for r in caplog.records)


def test_admin_auth(gw):
    client, rec = gw
    for headers in (None, {"Authorization": "Bearer wrong"}, {"Authorization": ADMIN_TOKEN}):
        res = call(client, "POST", "/api/v1/admin/problems", "{}", headers)
        assert_error(res, 401)
        assert res.headers["WWW-Authenticate"] == 'Bearer realm="oj-admin"'
    assert_error(
        call(client, "GET", "/api/v1/admin/problems/1/testcases", headers={"Authorization": "Basic x"}), 401
    )
    assert rec.calls == []
    res = call(client, "GET", "/api/v1/admin/verify", headers=AUTH)
    assert (res.status_code, res.get_json()) == (200, {"admin": True})


def test_admin_disabled_without_token():
    client, rec = make_client(Settings(admin_token=""))
    for headers in ({"Authorization": "Bearer "}, AUTH):
        assert_error(call(client, "GET", "/api/v1/admin/verify", headers=headers), 403)
    assert_error(call(client, "DELETE", "/api/v1/admin/problems/1", headers=AUTH), 403)
    assert rec.calls == []


def test_rate_limit_on_code_execution():
    client, _ = make_client(Settings(rate_limit_per_min=1, rate_limit_burst=2))
    codes = [call(client, "POST", "/api/v1/submissions", "{}").status_code for _ in range(3)]
    assert codes == [202, 202, 429]
    res = call(client, "POST", "/api/v1/run", "{}")  # shares the limiter
    body = assert_error(res, 429)
    assert int(res.headers["Retry-After"]) >= 1
    assert body["error"] == f"rate limit exceeded, retry in {res.headers['Retry-After']}s"
    # Reads are never rate limited.
    assert call(client, "GET", "/api/v1/problems").status_code == 200


def test_rate_limit_is_per_client_ip():
    client, _ = make_client(Settings(rate_limit_per_min=1, rate_limit_burst=1))
    a = {"REMOTE_ADDR": "10.0.0.1"}
    assert call(client, "POST", "/api/v1/run", "{}", environ_base=a).status_code == 200
    assert call(client, "POST", "/api/v1/run", "{}", environ_base=a).status_code == 429
    assert (
        call(client, "POST", "/api/v1/run", "{}", environ_base={"REMOTE_ADDR": "10.0.0.2"}).status_code == 200
    )
    # Proxy headers are ignored unless TRUST_PROXY_HEADERS: still 10.0.0.1.
    res = call(client, "POST", "/api/v1/run", "{}", {"X-Forwarded-For": "1.2.3.4"}, environ_base=a)
    assert res.status_code == 429


def test_trusted_proxy_headers():
    client, _ = make_client(Settings(rate_limit_per_min=1, rate_limit_burst=1, trust_proxy_headers=True))
    env = {"REMOTE_ADDR": "10.0.0.1"}
    xff = {"X-Forwarded-For": "1.2.3.4, 10.0.0.1"}
    assert call(client, "POST", "/api/v1/run", "{}", xff, environ_base=env).status_code == 200
    assert call(client, "POST", "/api/v1/run", "{}", xff, environ_base=env).status_code == 429
    # X-Real-IP wins over X-Forwarded-For: another client.
    real = {"X-Real-IP": "5.6.7.8", **xff}
    assert call(client, "POST", "/api/v1/run", "{}", real, environ_base=env).status_code == 200
    # The proxy's own address is a separate bucket.
    assert call(client, "POST", "/api/v1/run", "{}", environ_base=env).status_code == 200


def test_body_too_large_with_content_length(gw):
    client, rec = gw
    big = '{"source":"' + "a" * MAX_SUBMISSION_BODY + '"}'
    assert_error(call(client, "POST", "/api/v1/submissions", big), 413)
    assert call(client, "POST", "/api/v1/run", big).status_code == 200  # run allows 2 MiB
    assert len(rec.calls) == 1


def test_body_too_large_chunked(gw):
    """Without Content-Length the body is cut off while reading."""
    client, rec = gw
    big = ('{"source":"' + "a" * MAX_SUBMISSION_BODY + '"}').encode()
    res = client.post(
        "/api/v1/submissions",
        input_stream=io.BytesIO(big),
        headers={"Transfer-Encoding": "chunked"},
        environ_overrides={"wsgi.input_terminated": True},
    )
    body = assert_error(res, 413)
    assert body["error"] == "request body too large"
    assert rec.calls == []


def test_request_id(gw):
    client, _ = gw
    generated = call(client, "GET", "/healthz").headers["X-Request-ID"]
    assert len(generated) == 24
    assert (
        call(client, "GET", "/api/v1/problems", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"]
        == "abc-123"
    )
    replaced = call(client, "GET", "/api/v1/problems", headers={"X-Request-ID": "bad id!"}).headers[
        "X-Request-ID"
    ]
    assert replaced != "bad id!" and len(replaced) == 24
    # Also on errors.
    assert call(client, "GET", "/nope", headers={"X-Request-ID": "r1"}).headers["X-Request-ID"] == "r1"


def test_cors_allow_list():
    client, _ = make_client(Settings(cors_origins=("https://oj.example",)))
    pre = call(
        client,
        "OPTIONS",
        "/api/v1/run",
        headers={"Origin": "https://oj.example", "Access-Control-Request-Method": "POST"},
    )
    assert pre.status_code == 204
    assert pre.headers["Access-Control-Allow-Origin"] == "https://oj.example"
    assert "POST" in pre.headers["Access-Control-Allow-Methods"]
    assert "Authorization" in pre.headers["Access-Control-Allow-Headers"]
    res = call(client, "GET", "/api/v1/problems", headers={"Origin": "https://oj.example"})
    assert res.headers["Access-Control-Allow-Origin"] == "https://oj.example"
    assert "Origin" in res.headers["Vary"]
    assert "Retry-After" in res.headers["Access-Control-Expose-Headers"]
    evil = call(client, "GET", "/api/v1/problems", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in evil.headers


def test_cors_wildcard(gw):
    client, _ = gw
    res = call(client, "GET", "/nope", headers={"Origin": "https://any.example"})
    assert res.headers["Access-Control-Allow-Origin"] == "*"
    assert call(client, "GET", "/api/v1/problems").headers.get("Access-Control-Allow-Origin") is None


def test_healthz_has_no_dependencies():
    store, queue = FakeStore(), FakeQueue()
    store.down = queue.down = True
    client = create_app(Settings(), fake_repositories(store, queue)).test_client()
    res = client.get("/healthz")
    assert (res.status_code, res.get_json()) == (200, {"status": "ok"})
    assert_error(client.get("/api/v1/problems"), 503)


def test_error_body_is_an_error_response(gw):
    client, _ = gw
    res = call(client, "GET", "/api/v1/problems/abc")
    parsed = json_format.Parse(res.data, T.ErrorResponse())
    assert parsed.error == "invalid id: must be a positive integer"
