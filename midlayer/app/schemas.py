"""Request/response models exposed by the midlayer."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Difficulty = Literal["easy", "medium", "hard"]

MAX_SOURCE_CHARS = 256 * 1024
MAX_IO_CHARS = 8 * 1024 * 1024


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- problems ----------


class ProblemSummary(BaseModel):
    id: int
    slug: str
    title: str
    difficulty: str
    time_limit_ms: int
    memory_limit_mb: int


class Sample(BaseModel):
    input: str
    output: str


class ProblemDetail(ProblemSummary):
    statement: str
    samples: list[Sample]


class TestCaseIn(_Model):
    input: str = Field(max_length=MAX_IO_CHARS)
    expected_output: str = Field(max_length=MAX_IO_CHARS)
    is_sample: bool = False


class TestCaseOut(BaseModel):
    id: int
    problem_id: int
    input: str
    expected_output: str
    is_sample: bool
    ordinal: int


class ProblemUpdate(_Model):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)
    title: str = Field(min_length=1, max_length=200)
    statement: str = Field(default="", max_length=100_000)
    difficulty: Difficulty = "easy"
    time_limit_ms: int = Field(default=2000, ge=100, le=15_000)
    memory_limit_mb: int = Field(default=256, ge=16, le=1024)


class ProblemCreate(ProblemUpdate):
    test_cases: list[TestCaseIn] = Field(min_length=1, max_length=200)


# ---------- submissions ----------


class SubmissionCreate(_Model):
    problem_id: int = Field(gt=0)
    language: str = Field(min_length=1, max_length=32)
    source: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)
    username: str = Field(default="anonymous", pattern=r"^[A-Za-z0-9_.-]{1,32}$")


class SubmissionSummary(BaseModel):
    id: int
    problem_id: int
    username: str
    language: str
    status: str
    verdict: str
    passed: int
    total: int
    time_ms: int
    created_at: datetime


class SubmissionDetail(SubmissionSummary):
    source: str
    message: str
    results: list[dict[str, Any]]
    updated_at: datetime


# ---------- custom run ----------


class RunRequest(_Model):
    language: str = Field(min_length=1, max_length=32)
    source: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)
    stdin: str = Field(default="", max_length=1024 * 1024)
    problem_id: int | None = Field(default=None, gt=0, description="Use this problem's limits")


class RunResult(BaseModel):
    status: str
    compile_output: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    time_ms: int = 0
    memory_kb: int = 0


class Language(BaseModel):
    id: str
    name: str
