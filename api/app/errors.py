"""Domain errors raised by services and repositories. The HTTP error handler (controllers/http.py)
turns them into an oj.v1.ErrorResponse with `status_code`; the worker decides ack vs. requeue on them."""


class AppError(Exception):
    """Unexpected failure: 500, details are logged, never returned."""

    status_code = 500

    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []


# ---------- raised by controllers (malformed HTTP requests) ----------


class BadRequest(AppError):
    """Unparsable JSON body, unknown field, non-numeric path or query parameter."""

    status_code = 400


class Unauthorized(AppError):
    """Missing or wrong admin token."""

    status_code = 401


class Forbidden(AppError):
    """Admin API disabled (ADMIN_TOKEN empty)."""

    status_code = 403


class PayloadTooLarge(AppError):
    status_code = 413


class RateLimited(AppError):
    """Per-client token bucket empty. The response carries Retry-After."""

    status_code = 429

    def __init__(self, message: str, retry_after_s: int):
        super().__init__(message)
        self.retry_after_s = retry_after_s


# ---------- raised by services and repositories ----------


class ValidationError(AppError):
    """The message names the offending field."""

    status_code = 422


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    """Duplicate problem slug."""

    status_code = 409


class PreconditionFailed(Conflict):
    """Compare-and-set of a submission status lost (late or duplicate judging event)."""


class QueueFull(AppError):
    """judge.jobs holds MAX_QUEUE_DEPTH or more jobs."""

    status_code = 429


class Timeout(AppError):
    """A custom run got no runner answer in time."""

    status_code = 504


class Unavailable(AppError):
    """Database or RabbitMQ unreachable (or the runner failed a custom run). The worker requeues."""

    status_code = 503
