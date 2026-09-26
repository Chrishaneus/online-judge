"""Domain errors raised by services and repositories. The gRPC transport maps them to status codes."""


class AppError(Exception):
    """Unexpected failure. Mapped to INTERNAL."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationError(AppError):
    """INVALID_ARGUMENT. The message names the offending field."""


class NotFound(AppError):
    """NOT_FOUND."""


class AlreadyExists(AppError):
    """ALREADY_EXISTS (duplicate problem slug)."""


class PreconditionFailed(AppError):
    """FAILED_PRECONDITION (compare-and-set of a submission status lost)."""


class ResourceExhausted(AppError):
    """RESOURCE_EXHAUSTED (judging queue is full)."""


class DeadlineExceeded(AppError):
    """DEADLINE_EXCEEDED (a custom run got no runner answer in time)."""


class Unavailable(AppError):
    """UNAVAILABLE (oj-dao or RabbitMQ unreachable)."""
