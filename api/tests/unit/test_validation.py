import pytest

from app.errors import ValidationError
from app.gen.oj.v1 import judge_pb2, types_pb2
from app.services import validation


def make_problem(**overrides):
    args = {
        "slug": "double-it",
        "title": "Double",
        "statement": "",
        "difficulty": 0,
        "time_limit_ms": 0,
        "memory_limit_mb": 0,
    }
    args.update(overrides)
    return validation.problem(**args)


def test_problem_defaults():
    p = make_problem()
    assert (p.difficulty, p.time_limit_ms, p.memory_limit_mb) == (types_pb2.DIFFICULTY_EASY, 2000, 256)


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"slug": "Bad Slug"}, "slug"),
        ({"slug": "-a"}, "slug"),
        ({"slug": "a--b"}, "slug"),
        ({"slug": "a" * 65}, "slug"),
        ({"title": ""}, "title"),
        ({"title": "t" * 201}, "title"),
        ({"statement": "s" * 100_001}, "statement"),
        ({"difficulty": 42}, "difficulty"),
        ({"time_limit_ms": 50}, "time_limit_ms"),
        ({"time_limit_ms": 15_001}, "time_limit_ms"),
        ({"memory_limit_mb": 15}, "memory_limit_mb"),
        ({"memory_limit_mb": 1025}, "memory_limit_mb"),
    ],
)
def test_problem_rejects(overrides, field):
    with pytest.raises(ValidationError, match=field):
        make_problem(**overrides)


def test_problem_accepts_bounds():
    p = make_problem(slug="a" * 64, title="t" * 200, time_limit_ms=100, memory_limit_mb=1024)
    assert (p.time_limit_ms, p.memory_limit_mb) == (100, 1024)


def test_test_cases_count():
    with pytest.raises(ValidationError, match="test_cases"):
        validation.test_cases([])
    with pytest.raises(ValidationError, match="test_cases"):
        validation.test_cases([judge_pb2.NewTestCase()] * 201)
    assert len(validation.test_cases([judge_pb2.NewTestCase()] * 200)) == 200


def test_test_case_size():
    big = "x" * (validation.MAX_IO_CHARS + 1)
    with pytest.raises(ValidationError, match=r"test_cases\[1\].expected_output"):
        validation.test_cases([judge_pb2.NewTestCase(), judge_pb2.NewTestCase(expected_output=big)])
    with pytest.raises(ValidationError, match=r"test_case\.input"):
        validation.test_case(judge_pb2.NewTestCase(input=big))


@pytest.mark.parametrize("name", ["", "anonymous"])
def test_username_defaults_to_anonymous(name):
    assert validation.username(name) == "anonymous"


@pytest.mark.parametrize("name", ["has space", "x" * 33, "ü", "a/b"])
def test_username_rejects(name):
    with pytest.raises(ValidationError, match="username"):
        validation.username(name)


def test_username_accepts():
    assert validation.username("Al_ice.b-0") == "Al_ice.b-0"


def test_source_and_stdin_limits():
    with pytest.raises(ValidationError, match="source"):
        validation.source("")
    with pytest.raises(ValidationError, match="source"):
        validation.source("x" * (256 * 1024 + 1))
    assert validation.source("x" * 256 * 1024)
    with pytest.raises(ValidationError, match="stdin"):
        validation.stdin("x" * (1024 * 1024 + 1))
    assert validation.stdin("") == ""


@pytest.mark.parametrize("lang", [types_pb2.LANGUAGE_UNSPECIFIED, 99])
def test_language_rejects(lang):
    with pytest.raises(ValidationError, match="language"):
        validation.language(lang)


@pytest.mark.parametrize("limit,offset,expected", [(0, 0, (50, 0)), (1, 3, (1, 3)), (200, 0, (200, 0))])
def test_page(limit, offset, expected):
    assert validation.page(limit, offset) == expected


@pytest.mark.parametrize("limit,offset,field", [(201, 0, "limit"), (-1, 0, "limit"), (10, -1, "offset")])
def test_page_rejects(limit, offset, field):
    with pytest.raises(ValidationError, match=field):
        validation.page(limit, offset)


def test_title_is_trimmed():
    assert make_problem(title="  Double  ").title == "Double"
    with pytest.raises(ValidationError, match="title"):
        make_problem(title="   ")
