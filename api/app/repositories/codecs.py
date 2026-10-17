"""The single place where proto enums map to the strings stored in Postgres (unchanged since v1).

Every mapping is a bijection over the known values. *_to_db raises ValidationError for values that
cannot be stored; *_from_db maps unknown stored strings (legacy or hand-edited rows) to UNSPECIFIED
and logs them instead of failing reads.
"""

import logging

from app.errors import ValidationError
from app.gen.oj.v1 import types_pb2 as T

log = logging.getLogger(__name__)

LANGUAGES = {
    T.LANGUAGE_PYTHON: "python",
    T.LANGUAGE_C: "c",
    T.LANGUAGE_CPP: "cpp",
    T.LANGUAGE_JAVASCRIPT: "javascript",
}

DIFFICULTIES = {
    T.DIFFICULTY_EASY: "easy",
    T.DIFFICULTY_MEDIUM: "medium",
    T.DIFFICULTY_HARD: "hard",
}

STATUSES = {
    T.SUBMISSION_STATUS_PENDING: "PENDING",
    T.SUBMISSION_STATUS_JUDGING: "JUDGING",
    T.SUBMISSION_STATUS_FINISHED: "FINISHED",
    T.SUBMISSION_STATUS_FAILED: "FAILED",
}

# VERDICT_UNSPECIFIED is storable: it means "not judged yet".
VERDICTS = {
    T.VERDICT_UNSPECIFIED: "",
    T.VERDICT_ACCEPTED: "AC",
    T.VERDICT_WRONG_ANSWER: "WA",
    T.VERDICT_TIME_LIMIT_EXCEEDED: "TLE",
    T.VERDICT_MEMORY_LIMIT_EXCEEDED: "MLE",
    T.VERDICT_OUTPUT_LIMIT_EXCEEDED: "OLE",
    T.VERDICT_RUNTIME_ERROR: "RE",
    T.VERDICT_COMPILATION_ERROR: "CE",
    T.VERDICT_INTERNAL_ERROR: "IE",
}

_BY_DB = {id(m): {v: k for k, v in m.items()} for m in (LANGUAGES, DIFFICULTIES, STATUSES, VERDICTS)}


def _to_db(mapping: dict[int, str], value: int, what: str) -> str:
    try:
        return mapping[value]
    except KeyError:
        raise ValidationError(f"{what}: unsupported value {value}") from None


def _from_db(mapping: dict[int, str], value: str, what: str) -> int:
    out = _BY_DB[id(mapping)].get(value)
    if out is None:
        log.warning("unknown stored enum value: %s=%r", what, value)
        return 0
    return out


def language_to_db(v: int) -> str:
    return _to_db(LANGUAGES, v, "language")


def language_from_db(s: str) -> int:
    return _from_db(LANGUAGES, s, "language")


def difficulty_to_db(v: int) -> str:
    return _to_db(DIFFICULTIES, v, "difficulty")


def difficulty_from_db(s: str) -> int:
    return _from_db(DIFFICULTIES, s, "difficulty")


def status_to_db(v: int) -> str:
    return _to_db(STATUSES, v, "status")


def status_from_db(s: str) -> int:
    return _from_db(STATUSES, s, "status")


def verdict_to_db(v: int) -> str:
    return _to_db(VERDICTS, v, "verdict")


def verdict_from_db(s: str) -> int:
    return _from_db(VERDICTS, s, "verdict")


# ---------- submissions.results JSONB ----------
# Row format (must not change): [{"test":1,"verdict":"AC","time_ms":12,"memory_kb":9000,"sample":true}]


def results_to_db(results: list[T.TestResult]) -> list[dict]:
    return [
        {
            "test": r.test,
            "verdict": verdict_to_db(r.verdict),
            "time_ms": r.time_ms,
            "memory_kb": r.memory_kb,
            "sample": r.sample,
        }
        for r in results
    ]


def _typed(row: dict, key: str, kind: type, default):
    value = row.get(key, default)
    if kind is int and (isinstance(value, bool) or not isinstance(value, int)):
        raise TypeError(key)
    if not isinstance(value, kind):
        raise TypeError(key)
    return value


def results_from_db(submission_id: int, raw) -> list[T.TestResult]:
    """Rows written by older versions may not match the format: they are logged and read as empty."""
    if raw is None:
        return []
    try:
        if not isinstance(raw, list):
            raise TypeError("not a list")
        out = []
        for row in raw:
            if not isinstance(row, dict):
                raise TypeError("element is not an object")
            out.append(
                T.TestResult(
                    test=_typed(row, "test", int, 0),
                    verdict=verdict_from_db(_typed(row, "verdict", str, "")),
                    time_ms=_typed(row, "time_ms", int, 0),
                    memory_kb=_typed(row, "memory_kb", int, 0),
                    sample=_typed(row, "sample", bool, False),
                )
            )
        return out
    except (TypeError, ValueError) as exc:
        log.warning("ignoring malformed results of submission %d: %s", submission_id, exc)
        return []
