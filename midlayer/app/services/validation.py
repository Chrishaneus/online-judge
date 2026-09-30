"""Input validation and defaults. Raises ValidationError naming the offending field."""

import re

from app.errors import ValidationError
from app.gen.oj.v1 import types_pb2

from .languages import LANGUAGE_NAMES

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")

MAX_SLUG_CHARS = 64
MAX_TITLE_CHARS = 200
MAX_STATEMENT_CHARS = 100_000
MAX_SOURCE_CHARS = 256 * 1024
MAX_STDIN_CHARS = 1024 * 1024
MAX_IO_CHARS = 8 * 1024 * 1024
MAX_TEST_CASES = 200
MAX_USERNAME_CHARS = 32

DEFAULT_TIME_LIMIT_MS, MIN_TIME_LIMIT_MS, MAX_TIME_LIMIT_MS = 2000, 100, 15_000
DEFAULT_MEMORY_LIMIT_MB, MIN_MEMORY_LIMIT_MB, MAX_MEMORY_LIMIT_MB = 256, 16, 1024

DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT = 50, 200
ANONYMOUS = "anonymous"


def require_id(value: int, field: str = "id") -> int:
    if value <= 0:
        raise ValidationError(f"{field} must be a positive integer")
    return value


def optional_id(value: int, field: str) -> int:
    if value < 0:
        raise ValidationError(f"{field} must not be negative")
    return value


def language(value: int) -> int:
    if value not in LANGUAGE_NAMES:
        raise ValidationError("language: unsupported language")
    return value


def source(value: str) -> str:
    if not value:
        raise ValidationError("source must not be empty")
    if len(value) > MAX_SOURCE_CHARS:
        raise ValidationError(f"source must be at most {MAX_SOURCE_CHARS} characters")
    return value


def stdin(value: str) -> str:
    if len(value) > MAX_STDIN_CHARS:
        raise ValidationError(f"stdin must be at most {MAX_STDIN_CHARS} characters")
    return value


def username(value: str) -> str:
    """Empty means anonymous."""
    if not value:
        return ANONYMOUS
    if not USERNAME_RE.match(value):
        raise ValidationError("username must match [A-Za-z0-9_.-]{1,32}")
    return value


def username_filter(value: str) -> str:
    if len(value) > MAX_USERNAME_CHARS:
        raise ValidationError(f"username must be at most {MAX_USERNAME_CHARS} characters")
    return value


def page(limit: int, offset: int) -> tuple[int, int]:
    if limit == 0:
        limit = DEFAULT_LIST_LIMIT
    if not 1 <= limit <= MAX_LIST_LIMIT:
        raise ValidationError(f"limit must be between 1 and {MAX_LIST_LIMIT}")
    if offset < 0:
        raise ValidationError("offset must not be negative")
    return limit, offset


def _ranged(value: int, field: str, default: int, lo: int, hi: int) -> int:
    if value == 0:
        return default
    if not lo <= value <= hi:
        raise ValidationError(f"{field} must be between {lo} and {hi}")
    return value


def problem(
    slug: str, title: str, statement: str, difficulty: int, time_limit_ms: int, memory_limit_mb: int
) -> types_pb2.Problem:
    """Validate problem metadata and apply defaults (difficulty EASY, 2000 ms, 256 MB)."""
    if len(slug) > MAX_SLUG_CHARS or not SLUG_RE.match(slug):
        raise ValidationError(f"slug must be lowercase kebab-case, at most {MAX_SLUG_CHARS} characters")
    if not 1 <= len(title) <= MAX_TITLE_CHARS:
        raise ValidationError(f"title must be 1 to {MAX_TITLE_CHARS} characters")
    if len(statement) > MAX_STATEMENT_CHARS:
        raise ValidationError(f"statement must be at most {MAX_STATEMENT_CHARS} characters")
    if difficulty == types_pb2.DIFFICULTY_UNSPECIFIED:
        difficulty = types_pb2.DIFFICULTY_EASY
    if difficulty not in types_pb2.Difficulty.values():
        raise ValidationError("difficulty: unknown value")
    return types_pb2.Problem(
        slug=slug,
        title=title,
        statement=statement,
        difficulty=difficulty,
        time_limit_ms=_ranged(
            time_limit_ms, "time_limit_ms", DEFAULT_TIME_LIMIT_MS, MIN_TIME_LIMIT_MS, MAX_TIME_LIMIT_MS
        ),
        memory_limit_mb=_ranged(
            memory_limit_mb,
            "memory_limit_mb",
            DEFAULT_MEMORY_LIMIT_MB,
            MIN_MEMORY_LIMIT_MB,
            MAX_MEMORY_LIMIT_MB,
        ),
    )


def test_case(tc, field: str = "test_case") -> types_pb2.TestCase:
    """Validate a judge_pb2.NewTestCase and convert it to a TestCase (no ids)."""
    if len(tc.input) > MAX_IO_CHARS:
        raise ValidationError(f"{field}.input must be at most {MAX_IO_CHARS} characters")
    if len(tc.expected_output) > MAX_IO_CHARS:
        raise ValidationError(f"{field}.expected_output must be at most {MAX_IO_CHARS} characters")
    return types_pb2.TestCase(input=tc.input, expected_output=tc.expected_output, is_sample=tc.is_sample)


def test_cases(items) -> list[types_pb2.TestCase]:
    if not 1 <= len(items) <= MAX_TEST_CASES:
        raise ValidationError(f"test_cases must contain 1 to {MAX_TEST_CASES} test cases")
    return [test_case(tc, f"test_cases[{i}]") for i, tc in enumerate(items)]
