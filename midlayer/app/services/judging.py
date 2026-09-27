"""Judging rules: output normalisation and verdict precedence. Pure functions, no I/O."""

from dataclasses import dataclass, field

from app.gen.oj.v1 import dao_pb2, runner_pb2, types_pb2

V = types_pb2

VERDICT_NAMES = {
    V.VERDICT_ACCEPTED: "Accepted",
    V.VERDICT_WRONG_ANSWER: "Wrong Answer",
    V.VERDICT_TIME_LIMIT_EXCEEDED: "Time Limit Exceeded",
    V.VERDICT_MEMORY_LIMIT_EXCEEDED: "Memory Limit Exceeded",
    V.VERDICT_OUTPUT_LIMIT_EXCEEDED: "Output Limit Exceeded",
    V.VERDICT_RUNTIME_ERROR: "Runtime Error",
    V.VERDICT_COMPILATION_ERROR: "Compilation Error",
    V.VERDICT_INTERNAL_ERROR: "Internal Error",
}

_RUN_STATUS_TO_VERDICT = {
    V.RUN_STATUS_TIME_LIMIT_EXCEEDED: V.VERDICT_TIME_LIMIT_EXCEEDED,
    V.RUN_STATUS_MEMORY_LIMIT_EXCEEDED: V.VERDICT_MEMORY_LIMIT_EXCEEDED,
    V.RUN_STATUS_OUTPUT_LIMIT_EXCEEDED: V.VERDICT_OUTPUT_LIMIT_EXCEEDED,
    V.RUN_STATUS_RUNTIME_ERROR: V.VERDICT_RUNTIME_ERROR,
}

MAX_MESSAGE_CHARS = 4000

# A finished result may overwrite a submission only while it is still being judged.
OPEN_STATUSES = [V.SUBMISSION_STATUS_PENDING, V.SUBMISSION_STATUS_JUDGING]


def normalize_output(text: str) -> str:
    """Canonical form used for comparison.

    CRLF/CR become LF, trailing whitespace on each line is dropped, and
    trailing blank lines are dropped. Leading whitespace is significant.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [line.rstrip() for line in lines]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def outputs_match(actual: str, expected: str) -> bool:
    return normalize_output(actual) == normalize_output(expected)


def truncate_message(message: str) -> str:
    return message[:MAX_MESSAGE_CHARS]


@dataclass
class Outcome:
    verdict: int
    passed: int
    total: int
    time_ms: int = 0
    message: str = ""
    results: list[types_pb2.TestResult] = field(default_factory=list)

    def as_update(self, submission_id: int) -> dao_pb2.UpdateSubmissionRequest:
        return dao_pb2.UpdateSubmissionRequest(
            id=submission_id,
            status=V.SUBMISSION_STATUS_FINISHED,
            verdict=self.verdict,
            passed=self.passed,
            total=self.total,
            time_ms=self.time_ms,
            message=truncate_message(self.message),
            results=dao_pb2.TestResults(results=self.results),
            expected_statuses=OPEN_STATUSES,
        )


def failed_update(submission_id: int, message: str) -> dao_pb2.UpdateSubmissionRequest:
    """FAILED / INTERNAL_ERROR: judging itself broke. Only applies to a submission still being judged."""
    return dao_pb2.UpdateSubmissionRequest(
        id=submission_id,
        status=V.SUBMISSION_STATUS_FAILED,
        verdict=V.VERDICT_INTERNAL_ERROR,
        message=truncate_message(message),
        expected_statuses=OPEN_STATUSES,
    )


def evaluate(test_cases: list[types_pb2.TestCase], result: runner_pb2.ExecuteResult) -> Outcome:
    """Turn raw runner results + expected outputs into a verdict.

    Only for OK / COMPILATION_ERROR results; REJECTED / INTERNAL_ERROR are judging failures.
    """
    total = len(test_cases)
    if result.status == runner_pb2.EXECUTE_STATUS_COMPILATION_ERROR:
        return Outcome(V.VERDICT_COMPILATION_ERROR, 0, total, message=result.compile_output)

    by_id = {r.id: r for r in result.results}
    results: list[types_pb2.TestResult] = []
    first_failure: tuple[int, int] | None = None
    for idx, tc in enumerate(test_cases, start=1):
        run = by_id.get(str(tc.id))
        if run is None:
            verdict, time_ms, memory_kb = V.VERDICT_INTERNAL_ERROR, 0, 0
        else:
            time_ms, memory_kb = run.time_ms, run.memory_kb
            if run.status == V.RUN_STATUS_OK:
                ok = outputs_match(run.stdout, tc.expected_output)
                verdict = V.VERDICT_ACCEPTED if ok else V.VERDICT_WRONG_ANSWER
            else:
                verdict = _RUN_STATUS_TO_VERDICT.get(run.status, V.VERDICT_INTERNAL_ERROR)
        results.append(
            types_pb2.TestResult(
                test=idx, verdict=verdict, time_ms=time_ms, memory_kb=memory_kb, sample=tc.is_sample
            )
        )
        if verdict != V.VERDICT_ACCEPTED and first_failure is None:
            first_failure = (idx, verdict)

    passed = sum(1 for r in results if r.verdict == V.VERDICT_ACCEPTED)
    max_time = max((r.time_ms for r in results), default=0)
    if first_failure is None:
        return Outcome(V.VERDICT_ACCEPTED, passed, total, max_time, "All tests passed", results)
    idx, verdict = first_failure
    return Outcome(verdict, passed, total, max_time, f"{VERDICT_NAMES[verdict]} on test {idx}", results)
