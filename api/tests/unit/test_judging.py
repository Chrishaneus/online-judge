"""Judging rules: output normalisation and verdict precedence (ported from the pre-gRPC midlayer)."""

import pytest

from app.gen.oj.v1 import runner_pb2, types_pb2
from app.services.judging import MAX_MESSAGE_CHARS, Outcome, evaluate, normalize_output, outputs_match

V = types_pb2


@pytest.mark.parametrize(
    "actual,expected,ok",
    [
        ("3\n", "3", True),
        ("3", "3\n\n\n", True),
        ("1 2   \r\n3\r\n", "1 2\n3", True),
        ("1\r2\r", "1\n2", True),
        ("3\n4", "3\n5", False),
        (" 3", "3", False),  # leading whitespace is significant
        ("", "", True),
        ("a\n\nb", "a\nb", False),  # inner blank lines are significant
    ],
)
def test_outputs_match(actual, expected, ok):
    assert outputs_match(actual, expected) is ok


def test_normalize_output():
    assert normalize_output("x  \n\n") == "x"
    assert normalize_output("  x\t \r\n y \n \n") == "  x\n y"


TCS = [
    types_pb2.TestCase(id=10, expected_output="2", is_sample=True),
    types_pb2.TestCase(id=11, expected_output="4"),
    types_pb2.TestCase(id=12, expected_output="6"),
]


def ok_result(*items):
    return runner_pb2.ExecuteResult(
        status=runner_pb2.EXECUTE_STATUS_OK,
        results=[
            runner_pb2.TestRun(id=str(tc.id), status=st, stdout=out, time_ms=t, memory_kb=100)
            for tc, (st, out, t) in zip(TCS, items, strict=False)
        ],
    )


OK, TLE = V.RUN_STATUS_OK, V.RUN_STATUS_TIME_LIMIT_EXCEEDED


def test_evaluate_all_accepted():
    o = evaluate(TCS, ok_result((OK, "2\n", 5), (OK, "4", 9), (OK, "6 ", 7)))
    assert (o.verdict, o.passed, o.total, o.time_ms) == (V.VERDICT_ACCEPTED, 3, 3, 9)
    assert o.message == "All tests passed"
    assert [r.test for r in o.results] == [1, 2, 3]
    assert [r.sample for r in o.results] == [True, False, False]
    assert o.results[0].memory_kb == 100


def test_evaluate_first_failure_wins():
    o = evaluate(TCS, ok_result((OK, "2", 1), (TLE, "", 1000), (OK, "nope", 1)))
    assert o.verdict == V.VERDICT_TIME_LIMIT_EXCEEDED
    assert o.passed == 1
    assert o.time_ms == 1000
    assert o.message == "Time Limit Exceeded on test 2"
    assert [r.verdict for r in o.results] == [
        V.VERDICT_ACCEPTED,
        V.VERDICT_TIME_LIMIT_EXCEEDED,
        V.VERDICT_WRONG_ANSWER,
    ]


@pytest.mark.parametrize(
    "run_status,verdict",
    [
        (V.RUN_STATUS_TIME_LIMIT_EXCEEDED, V.VERDICT_TIME_LIMIT_EXCEEDED),
        (V.RUN_STATUS_MEMORY_LIMIT_EXCEEDED, V.VERDICT_MEMORY_LIMIT_EXCEEDED),
        (V.RUN_STATUS_OUTPUT_LIMIT_EXCEEDED, V.VERDICT_OUTPUT_LIMIT_EXCEEDED),
        (V.RUN_STATUS_RUNTIME_ERROR, V.VERDICT_RUNTIME_ERROR),
        (V.RUN_STATUS_COMPILATION_ERROR, V.VERDICT_INTERNAL_ERROR),
        (V.RUN_STATUS_UNSPECIFIED, V.VERDICT_INTERNAL_ERROR),
    ],
)
def test_evaluate_maps_run_status(run_status, verdict):
    o = evaluate(TCS[:1], ok_result((run_status, "2", 1)))
    assert o.verdict == verdict
    assert o.passed == 0


def test_evaluate_compile_error():
    o = evaluate(
        TCS,
        runner_pb2.ExecuteResult(status=runner_pb2.EXECUTE_STATUS_COMPILATION_ERROR, compile_output="boom"),
    )
    assert (o.verdict, o.passed, o.total, o.message) == (V.VERDICT_COMPILATION_ERROR, 0, 3, "boom")
    assert o.results == []


def test_evaluate_missing_result_is_internal_error():
    o = evaluate(TCS, runner_pb2.ExecuteResult(status=runner_pb2.EXECUTE_STATUS_OK))
    assert o.verdict == V.VERDICT_INTERNAL_ERROR
    assert o.message == "Internal Error on test 1"


def test_evaluate_matches_results_by_id_not_position():
    result = ok_result((OK, "2", 1), (OK, "4", 1), (OK, "6", 1))
    result.results.reverse()
    assert evaluate(TCS, result).verdict == V.VERDICT_ACCEPTED


def test_outcome_update_truncates_message_and_uses_cas():
    req = Outcome(V.VERDICT_COMPILATION_ERROR, 0, 1, message="x" * 10_000).as_update(7)
    assert len(req.message) == MAX_MESSAGE_CHARS
    assert req.id == 7
    assert req.status == V.SUBMISSION_STATUS_FINISHED
    assert list(req.expected_statuses) == [V.SUBMISSION_STATUS_PENDING, V.SUBMISSION_STATUS_JUDGING]
    assert req.results == []
