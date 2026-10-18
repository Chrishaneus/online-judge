"""Enum <-> stored string mapping and the results JSONB row format (ported from dao's convert_test.go)."""

import pytest

from app.errors import ValidationError
from app.gen.oj.v1 import types_pb2 as T
from app.repositories import codecs


@pytest.mark.parametrize(
    "to_db,from_db,pairs",
    [
        (
            codecs.language_to_db,
            codecs.language_from_db,
            {
                T.LANGUAGE_PYTHON: "python",
                T.LANGUAGE_C: "c",
                T.LANGUAGE_CPP: "cpp",
                T.LANGUAGE_JAVASCRIPT: "javascript",
            },
        ),
        (
            codecs.difficulty_to_db,
            codecs.difficulty_from_db,
            {T.DIFFICULTY_EASY: "easy", T.DIFFICULTY_MEDIUM: "medium", T.DIFFICULTY_HARD: "hard"},
        ),
        (
            codecs.status_to_db,
            codecs.status_from_db,
            {
                T.SUBMISSION_STATUS_PENDING: "PENDING",
                T.SUBMISSION_STATUS_JUDGING: "JUDGING",
                T.SUBMISSION_STATUS_FINISHED: "FINISHED",
                T.SUBMISSION_STATUS_FAILED: "FAILED",
            },
        ),
        (
            codecs.verdict_to_db,
            codecs.verdict_from_db,
            {
                T.VERDICT_UNSPECIFIED: "",
                T.VERDICT_ACCEPTED: "AC",
                T.VERDICT_WRONG_ANSWER: "WA",
                T.VERDICT_TIME_LIMIT_EXCEEDED: "TLE",
                T.VERDICT_MEMORY_LIMIT_EXCEEDED: "MLE",
                T.VERDICT_OUTPUT_LIMIT_EXCEEDED: "OLE",
                T.VERDICT_RUNTIME_ERROR: "RE",
                T.VERDICT_COMPILATION_ERROR: "CE",
                T.VERDICT_INTERNAL_ERROR: "IE",
            },
        ),
    ],
)
def test_round_trip(to_db, from_db, pairs):
    for enum, stored in pairs.items():
        assert to_db(enum) == stored
        assert from_db(stored) == enum
    assert from_db("legacy-garbage") == 0  # unknown stored values read as UNSPECIFIED


@pytest.mark.parametrize(
    "fn,value",
    [
        (codecs.language_to_db, T.LANGUAGE_UNSPECIFIED),
        (codecs.language_to_db, 99),
        (codecs.difficulty_to_db, T.DIFFICULTY_UNSPECIFIED),
        (codecs.status_to_db, T.SUBMISSION_STATUS_UNSPECIFIED),
        (codecs.verdict_to_db, 42),
    ],
)
def test_unstorable_values_are_rejected(fn, value):
    with pytest.raises(ValidationError):
        fn(value)


def test_results_row_format():
    rows = codecs.results_to_db(
        [T.TestResult(test=1, verdict=T.VERDICT_ACCEPTED, time_ms=12, memory_kb=9000, sample=True)]
    )
    assert rows == [{"test": 1, "verdict": "AC", "time_ms": 12, "memory_kb": 9000, "sample": True}]
    assert codecs.results_from_db(1, rows) == [
        T.TestResult(test=1, verdict=T.VERDICT_ACCEPTED, time_ms=12, memory_kb=9000, sample=True)
    ]


@pytest.mark.parametrize(
    "raw",
    [{"weird": True}, "x", [1, 2], [{"test": "one"}], [{"sample": "yes"}], [{"test": 2**40}]],
)
def test_malformed_legacy_results_read_as_empty(raw):
    assert codecs.results_from_db(7, raw) == []


def test_missing_keys_default_and_unknown_verdict_is_unspecified():
    assert codecs.results_from_db(1, None) == []
    assert codecs.results_from_db(1, [{"test": 3, "verdict": "??"}]) == [T.TestResult(test=3)]
