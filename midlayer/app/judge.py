"""Judging rules and the background judging worker pool."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# Submission lifecycle (mirrors oj-dao).
PENDING, JUDGING, FINISHED, FAILED = "PENDING", "JUDGING", "FINISHED", "FAILED"

# Verdicts.
AC, WA, TLE, MLE, OLE, RE, CE, IE = "AC", "WA", "TLE", "MLE", "OLE", "RE", "CE", "IE"

VERDICT_NAMES = {
    AC: "Accepted",
    WA: "Wrong Answer",
    TLE: "Time Limit Exceeded",
    MLE: "Memory Limit Exceeded",
    OLE: "Output Limit Exceeded",
    RE: "Runtime Error",
    CE: "Compilation Error",
    IE: "Internal Error",
}

_RUNNER_STATUS_TO_VERDICT = {"TLE": TLE, "MLE": MLE, "OLE": OLE, "RE": RE}

MAX_MESSAGE_CHARS = 4000


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


@dataclass
class Outcome:
    verdict: str
    passed: int
    total: int
    time_ms: int = 0
    message: str = ""
    results: list[dict[str, Any]] = field(default_factory=list)

    def as_update(self) -> dict[str, Any]:
        return {
            "status": FINISHED,
            "verdict": self.verdict,
            "passed": self.passed,
            "total": self.total,
            "time_ms": self.time_ms,
            "message": self.message[:MAX_MESSAGE_CHARS],
            "results": self.results,
        }


def evaluate(testcases: list[dict], runner_resp: dict) -> Outcome:
    """Turn raw runner results + expected outputs into a verdict."""
    total = len(testcases)
    if runner_resp.get("status") == "CE":
        return Outcome(CE, 0, total, message=runner_resp.get("compile_output", ""))

    by_id = {str(r["id"]): r for r in runner_resp.get("results", [])}
    results: list[dict[str, Any]] = []
    first_failure: tuple[int, str] | None = None
    for idx, tc in enumerate(testcases, start=1):
        r = by_id.get(str(tc["id"]))
        if r is None:
            verdict, time_ms, mem = IE, 0, 0
        else:
            time_ms, mem = int(r.get("time_ms", 0)), int(r.get("memory_kb", 0))
            if r["status"] == "OK":
                verdict = AC if outputs_match(r.get("stdout", ""), tc["expected_output"]) else WA
            else:
                verdict = _RUNNER_STATUS_TO_VERDICT.get(r["status"], IE)
        results.append(
            {
                "test": idx,
                "verdict": verdict,
                "time_ms": time_ms,
                "memory_kb": mem,
                "sample": bool(tc.get("is_sample")),
            }
        )
        if verdict != AC and first_failure is None:
            first_failure = (idx, verdict)

    passed = sum(1 for r in results if r["verdict"] == AC)
    max_time = max((r["time_ms"] for r in results), default=0)
    if first_failure is None:
        return Outcome(AC, passed, total, max_time, "All tests passed", results)
    idx, verdict = first_failure
    return Outcome(verdict, passed, total, max_time, f"{VERDICT_NAMES[verdict]} on test {idx}", results)


class Judge:
    """Async worker pool that judges queued submissions."""

    def __init__(self, dao, runner, workers: int = 4):
        self.dao = dao
        self.runner = runner
        self.workers = max(1, workers)
        self.queue: asyncio.Queue[int] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []

    async def start(self, recover: bool = True) -> None:
        self._tasks = [asyncio.create_task(self._worker(i)) for i in range(self.workers)]
        if recover:
            try:
                await self.recover()
            except Exception:  # dao may still be starting; not fatal
                log.exception("recovery of unfinished submissions failed")

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    def enqueue(self, submission_id: int) -> None:
        self.queue.put_nowait(submission_id)

    async def recover(self) -> int:
        """Re-queue submissions interrupted by a restart (oldest first)."""
        ids: set[int] = set()
        for status in (JUDGING, PENDING):
            for sub in await self.dao.list_submissions(status=status, limit=500):
                ids.add(sub["id"])
        for sid in sorted(ids):
            self.enqueue(sid)
        if ids:
            log.info("re-queued %d unfinished submissions", len(ids))
        return len(ids)

    async def _worker(self, n: int) -> None:
        while True:
            sid = await self.queue.get()
            try:
                await self.judge(sid)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("worker %d: unexpected error judging %s", n, sid)
            finally:
                self.queue.task_done()

    async def judge(self, sid: int) -> None:
        sub = await self.dao.get_submission(sid)
        if sub["status"] in (FINISHED, FAILED):
            return
        await self.dao.update_submission(sid, status=JUDGING)
        try:
            problem = await self.dao.get_problem(sub["problem_id"])
            testcases = await self.dao.list_testcases(sub["problem_id"])
            if not testcases:
                outcome = Outcome(IE, 0, 0, message="Problem has no test cases")
            else:
                resp = await self.runner.execute(
                    language=sub["language"],
                    source=sub["source"],
                    tests=[{"id": str(tc["id"]), "stdin": tc["input"]} for tc in testcases],
                    time_limit_ms=problem["time_limit_ms"],
                    memory_limit_mb=problem["memory_limit_mb"],
                )
                outcome = evaluate(testcases, resp)
            await self.dao.update_submission(sid, **outcome.as_update())
            log.info("judged submission %s: %s (%d/%d)", sid, outcome.verdict, outcome.passed, outcome.total)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("judging submission %s failed", sid)
            await self.dao.update_submission(
                sid, status=FAILED, verdict=IE, message=f"Judging failed: {type(exc).__name__}"
            )
