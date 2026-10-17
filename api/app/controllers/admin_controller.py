"""Admin routes under /api/v1/admin (bearer ADMIN_TOKEN). Path parameters override body fields."""

from flask import Blueprint, jsonify

from app.gen.oj.v1 import judge_pb2

from .http import (
    MAX_ADMIN_BODY,
    body_limit,
    no_content,
    parse_body,
    path_id,
    proto_response,
    require_admin,
    services,
)

bp = Blueprint("admin", __name__, url_prefix="/api/v1/admin")


@bp.get("/verify")
@require_admin
def verify():
    return jsonify(admin=True)


@bp.post("/problems")
@require_admin
@body_limit(MAX_ADMIN_BODY)
def add_problem():
    return proto_response(services().problems.add_problem(parse_body(judge_pb2.AddProblemRequest)), 201)


@bp.put("/problems/<raw_id>")
@require_admin
@body_limit(MAX_ADMIN_BODY)
def edit_problem(raw_id: str):
    req = parse_body(judge_pb2.EditProblemRequest)
    req.id = path_id(raw_id)
    return proto_response(services().problems.edit_problem(req))


@bp.delete("/problems/<raw_id>")
@require_admin
def remove_problem(raw_id: str):
    services().problems.remove_problem(judge_pb2.RemoveProblemRequest(id=path_id(raw_id)))
    return no_content()


@bp.get("/problems/<raw_problem_id>/testcases")
@require_admin
def list_problem_test_cases(raw_problem_id: str):
    req = judge_pb2.ListProblemTestCasesRequest(problem_id=path_id(raw_problem_id, "problemId"))
    return proto_response(services().problems.list_problem_test_cases(req))


@bp.post("/problems/<raw_problem_id>/testcases")
@require_admin
@body_limit(MAX_ADMIN_BODY)
def add_test_case(raw_problem_id: str):
    req = parse_body(judge_pb2.AddTestCaseRequest)
    req.problem_id = path_id(raw_problem_id, "problemId")
    return proto_response(services().problems.add_test_case(req), 201)


@bp.delete("/problems/<raw_problem_id>/testcases/<raw_id>")
@require_admin
def remove_test_case(raw_problem_id: str, raw_id: str):
    req = judge_pb2.RemoveTestCaseRequest(problem_id=path_id(raw_problem_id, "problemId"), id=path_id(raw_id))
    services().problems.remove_test_case(req)
    return no_content()
