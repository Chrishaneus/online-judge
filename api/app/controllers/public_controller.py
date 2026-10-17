"""Public routes under /api/v1 (plus /healthz). Each parses one request message, calls ONE service method
and returns its response message."""

from flask import Blueprint, jsonify, request

from app.gen.oj.v1 import judge_pb2

from .http import (
    MAX_RUN_BODY,
    MAX_SUBMISSION_BODY,
    body_limit,
    parse_body,
    path_id,
    proto_response,
    query_int32,
    rate_limited,
    services,
)

bp = Blueprint("public", __name__, url_prefix="/api/v1")
health_bp = Blueprint("health", __name__)


@health_bp.get("/healthz")
def healthz():
    """Liveness only: never touches Postgres or RabbitMQ."""
    return jsonify(status="ok")


@bp.get("/status")
def get_status():
    return proto_response(services().status.get_status(judge_pb2.GetStatusRequest()))


@bp.get("/languages")
def list_languages():
    return proto_response(services().languages.list_languages(judge_pb2.ListLanguagesRequest()))


@bp.get("/problems")
def list_problem_summaries():
    req = judge_pb2.ListProblemSummariesRequest()
    return proto_response(services().problems.list_problem_summaries(req))


@bp.get("/problems/<raw_id>")
def get_problem_detail(raw_id: str):
    req = judge_pb2.GetProblemDetailRequest(id=path_id(raw_id))
    return proto_response(services().problems.get_problem_detail(req))


@bp.post("/submissions")
@rate_limited
@body_limit(MAX_SUBMISSION_BODY)
def submit():
    return proto_response(services().submissions.submit(parse_body(judge_pb2.SubmitRequest)), 202)


@bp.get("/submissions")
def list_submission_summaries():
    """?problemId=&username=&limit=&offset= (problem_id is accepted too for older clients)."""
    req = judge_pb2.ListSubmissionSummariesRequest()
    pid = request.args.get("problemId") or request.args.get("problem_id") or ""
    if pid:
        req.problem_id = path_id(pid, "problemId")
    req.username = request.args.get("username", "")
    req.limit = query_int32("limit")
    req.offset = query_int32("offset")
    return proto_response(services().submissions.list_submission_summaries(req))


@bp.get("/submissions/<raw_id>")
def get_submission_detail(raw_id: str):
    req = judge_pb2.GetSubmissionDetailRequest(id=path_id(raw_id))
    return proto_response(services().submissions.get_submission_detail(req))


@bp.post("/run")
@rate_limited
@body_limit(MAX_RUN_BODY)
def run_code():
    return proto_response(services().runs.run_code(parse_body(judge_pb2.RunCodeRequest)))
