"""Request/response plumbing shared by controllers and the cross-cutting HTTP concerns: proto JSON in and
out, path/query parameters, request ids, CORS, body limits, admin auth, rate limiting and the mapping of
app.errors to oj.v1.ErrorResponse."""

import hmac
import json
import logging
import re
import secrets
from functools import wraps

from flask import Flask, Response, current_app, g, jsonify, request
from google.protobuf import json_format
from google.protobuf.message import Message
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from app.errors import (
    AppError,
    BadRequest,
    Forbidden,
    PayloadTooLarge,
    RateLimited,
    Unauthorized,
    Unavailable,
)
from app.gen.oj.v1 import types_pb2
from app.services import Services

from .rate_limit import RateLimiter, retry_after_seconds

log = logging.getLogger("app.http")

REQUEST_ID_HEADER = "X-Request-ID"
VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ID_PARAM = re.compile(r"^[1-9][0-9]{0,17}$")
INT_PARAM = re.compile(r"^[+-]?[0-9]+$")
MAX_INT32 = 2**31 - 1

MAX_SUBMISSION_BODY = 512 << 10
MAX_RUN_BODY = 2 << 20
MAX_ADMIN_BODY = 64 << 20


def services() -> Services:
    return current_app.extensions["services"]


# ---------- proto JSON ----------


def to_json(message: Message) -> dict:
    """Canonical proto JSON: camelCase, enums by name, int64 as strings, fields with default values."""
    return json_format.MessageToDict(message, always_print_fields_with_no_presence=True)


def proto_response(message: Message, status: int = 200):
    return jsonify(to_json(message)), status


def no_content() -> Response:
    res = Response(status=204)
    res.headers.remove("Content-Type")
    return res


def parse_body[M: Message](message_cls: type[M]) -> M:
    """The JSON body as message_cls. Empty body = {}. Unknown fields and bad JSON are 400."""
    msg = message_cls()
    raw = request.get_data(cache=True)
    limit = request.max_content_length
    if limit is not None and len(raw) >= limit:
        # A chunked body is silently cut at the limit; reading on raises RequestEntityTooLarge.
        request.stream.read(1)
    if not raw.strip():
        return msg
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise BadRequest("invalid JSON body", [str(e)]) from e
    if not isinstance(data, dict):
        raise BadRequest("invalid JSON body", ["the body must be a JSON object"])
    try:
        return json_format.ParseDict(data, msg)
    except json_format.ParseError as e:
        raise BadRequest("invalid JSON body", [str(e).splitlines()[0]]) from e


def path_id(value: str, name: str = "id") -> int:
    if not ID_PARAM.match(value):
        raise BadRequest(f"invalid {name}: must be a positive integer")
    return int(value)


def query_int32(name: str) -> int:
    value = request.args.get(name, "")
    if value == "":
        return 0
    if not INT_PARAM.match(value) or not 0 <= int(value) <= MAX_INT32:
        raise BadRequest(f"invalid {name}: must be a non-negative integer")
    return int(value)


# ---------- decorators ----------


def body_limit(max_bytes: int):
    """Cap the request body (413 before reading when Content-Length says so, else while reading)."""

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if request.content_length is not None and request.content_length > max_bytes:
                raise PayloadTooLarge("request body too large")
            request.max_content_length = max_bytes
            return view(*args, **kwargs)

        return wrapper

    return decorator


def require_admin(view):
    """`Authorization: Bearer <ADMIN_TOKEN>`, compared in constant time. Empty ADMIN_TOKEN = admin off."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        token: str = current_app.config["ADMIN_TOKEN"]
        if not token:
            raise Forbidden("admin API is disabled")
        header = request.headers.get("Authorization", "")
        given = header.removeprefix("Bearer ") if header.startswith("Bearer ") else None
        if given is None or not hmac.compare_digest(given.encode(), token.encode()):
            raise Unauthorized("invalid or missing admin token")
        return view(*args, **kwargs)

    return wrapper


def client_ip() -> str:
    """Proxy headers are honoured only behind a trusted reverse proxy (TRUST_PROXY_HEADERS=true)."""
    if current_app.config["TRUST_PROXY_HEADERS"]:
        if ip := request.headers.get("X-Real-IP", "").strip():
            return ip
        if xff := request.headers.get("X-Forwarded-For", ""):
            return xff.split(",")[0].strip()
    return request.remote_addr or ""


def rate_limited(view):
    """Shared per-client token bucket for the endpoints that execute code."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        limiter: RateLimiter = current_app.extensions["rate_limiter"]
        ok, wait = limiter.allow(client_ip())
        if not ok:
            secs = retry_after_seconds(wait)
            raise RateLimited(f"rate limit exceeded, retry in {secs}s", secs)
        return view(*args, **kwargs)

    return wrapper


# ---------- app-wide hooks ----------


def error_response(status: int, message: str, details: list[str] | None = None):
    return proto_response(types_pb2.ErrorResponse(error=message, details=details or []), status)


def register_http_hooks(app: Flask) -> None:
    origins = [o.strip() for o in app.config["CORS_ORIGINS"] if o.strip()]
    allow_all = "*" in origins

    def cors_origin() -> str | None:
        origin = request.headers.get("Origin", "")
        if origin and (allow_all or origin in origins):
            return "*" if allow_all else origin
        return None

    @app.before_request
    def request_id_and_preflight():
        rid = request.headers.get(REQUEST_ID_HEADER, "")
        g.request_id = rid if VALID_REQUEST_ID.match(rid) else secrets.token_hex(12)
        if (
            request.method == "OPTIONS"
            and request.headers.get("Access-Control-Request-Method")
            and cors_origin()
        ):
            res = Response(status=204)
            res.headers.remove("Content-Type")
            res.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            res.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Request-ID"
            res.headers["Access-Control-Max-Age"] = "600"
            return res
        return None

    @app.after_request
    def response_headers(res: Response) -> Response:
        res.headers[REQUEST_ID_HEADER] = g.get("request_id") or secrets.token_hex(12)
        if (allowed := cors_origin()) is not None:
            res.headers["Access-Control-Allow-Origin"] = allowed
            if not allow_all:
                res.vary.add("Origin")
            res.headers["Access-Control-Expose-Headers"] = "X-Request-ID, Retry-After"
        return res

    @app.errorhandler(AppError)
    def handle_app_error(err: AppError):
        rid = g.get("request_id", "-")
        if isinstance(err, Unavailable):
            log.warning("%s %s -> 503: %s (request_id=%s)", request.method, request.path, err.message, rid)
            return error_response(503, "service unavailable")
        if err.status_code >= 500 and type(err) is AppError:
            log.error("%s %s -> 500: %s (request_id=%s)", request.method, request.path, err.message, rid)
            return error_response(500, "internal error")
        res, status = error_response(err.status_code, err.message, err.details)
        if isinstance(err, RateLimited):
            res.headers["Retry-After"] = str(err.retry_after_s)
        if isinstance(err, Unauthorized):
            res.headers["WWW-Authenticate"] = 'Bearer realm="oj-admin"'
        return res, status

    @app.errorhandler(HTTPException)
    def handle_http_error(err: HTTPException):
        if isinstance(err, RequestEntityTooLarge):
            return error_response(413, "request body too large")
        status = err.code or 500
        message = {404: "not found", 405: "method not allowed"}.get(status, (err.name or "error").lower())
        res, status = error_response(status, message)
        for key, value in err.get_headers():  # keep e.g. the Allow header of a 405
            if key.lower() != "content-type":
                res.headers[key] = value
        return res, status

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        log.exception(
            "unhandled error on %s %s (request_id=%s)", request.method, request.path, g.get("request_id")
        )
        return error_response(500, "internal error")
