"""HTTP routes of the midlayer."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from .clients import Unavailable
from .schemas import (
    Language,
    ProblemCreate,
    ProblemDetail,
    ProblemSummary,
    ProblemUpdate,
    RunRequest,
    RunResult,
    Sample,
    SubmissionCreate,
    SubmissionDetail,
    SubmissionSummary,
    TestCaseIn,
    TestCaseOut,
)

log = logging.getLogger(__name__)
router = APIRouter()


def _deps(request: Request):
    s = request.app.state
    return s.dao, s.runner, s.judge


async def _languages(request: Request) -> list[dict]:
    state = request.app.state
    if not state.languages:
        state.languages = await state.runner.languages()
    return state.languages


async def _require_language(request: Request, language: str) -> None:
    ids = {lang["id"] for lang in await _languages(request)}
    if language not in ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unsupported language {language!r}")


# ---------- health ----------


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request, response: Response) -> dict:
    dao, runner, judge = _deps(request)

    async def probe(client) -> str:
        try:
            await client.health()
            return "ok"
        except Exception as exc:  # noqa: BLE001
            return f"error: {type(exc).__name__}"

    dao_s, runner_s = await asyncio.gather(probe(dao), probe(runner))
    ready = dao_s == "ok" and runner_s == "ok"
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if ready else "degraded",
        "dao": dao_s,
        "runner": runner_s,
        "queue_depth": judge.queue.qsize(),
    }


@router.get("/languages", response_model=list[Language])
async def languages(request: Request):
    return await _languages(request)


# ---------- problems ----------


@router.get("/problems", response_model=list[ProblemSummary])
async def list_problems(request: Request):
    dao, _, _ = _deps(request)
    return await dao.list_problems()


@router.get("/problems/{pid}", response_model=ProblemDetail)
async def get_problem(pid: int, request: Request):
    dao, _, _ = _deps(request)
    problem, samples = await asyncio.gather(dao.get_problem(pid), dao.list_testcases(pid, samples_only=True))
    return ProblemDetail(
        **problem,
        samples=[Sample(input=s["input"], output=s["expected_output"]) for s in samples],
    )


@router.post("/problems", response_model=ProblemDetail, status_code=status.HTTP_201_CREATED)
async def create_problem(body: ProblemCreate, request: Request):
    dao, _, _ = _deps(request)
    problem = await dao.create_problem(body.model_dump(exclude={"test_cases"}))
    try:
        for i, tc in enumerate(body.test_cases, start=1):
            await dao.create_testcase(problem["id"], {**tc.model_dump(), "ordinal": i})
    except Exception:
        # Compensate so we never leave a problem without its test data.
        log.exception("creating test cases failed; rolling back problem %s", problem["id"])
        try:
            await dao.delete_problem(problem["id"])
        except Exception:  # noqa: BLE001
            log.exception("rollback failed for problem %s", problem["id"])
        raise
    return ProblemDetail(
        **problem,
        samples=[Sample(input=t.input, output=t.expected_output) for t in body.test_cases if t.is_sample],
    )


@router.put("/problems/{pid}", response_model=ProblemSummary)
async def update_problem(pid: int, body: ProblemUpdate, request: Request):
    dao, _, _ = _deps(request)
    return await dao.update_problem(pid, body.model_dump())


@router.delete("/problems/{pid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_problem(pid: int, request: Request):
    dao, _, _ = _deps(request)
    await dao.delete_problem(pid)


@router.get("/problems/{pid}/testcases", response_model=list[TestCaseOut])
async def list_testcases(pid: int, request: Request):
    dao, _, _ = _deps(request)
    return await dao.list_testcases(pid)


@router.post("/problems/{pid}/testcases", response_model=TestCaseOut, status_code=status.HTTP_201_CREATED)
async def add_testcase(pid: int, body: TestCaseIn, request: Request):
    dao, _, _ = _deps(request)
    existing = await dao.list_testcases(pid)
    ordinal = max((t["ordinal"] for t in existing), default=0) + 1
    return await dao.create_testcase(pid, {**body.model_dump(), "ordinal": ordinal})


@router.delete("/problems/{pid}/testcases/{tcid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_testcase(pid: int, tcid: int, request: Request):
    dao, _, _ = _deps(request)
    await dao.delete_testcase(pid, tcid)


# ---------- submissions ----------


@router.post("/submissions", response_model=SubmissionDetail, status_code=status.HTTP_202_ACCEPTED)
async def submit(body: SubmissionCreate, request: Request):
    dao, _, judge = _deps(request)
    await _require_language(request, body.language)
    await dao.get_problem(body.problem_id)  # 404 early with a clear message
    sub = await dao.create_submission(body.model_dump())
    judge.enqueue(sub["id"])
    return sub


@router.get("/submissions", response_model=list[SubmissionSummary])
async def list_submissions(
    request: Request,
    problem_id: int | None = Query(default=None, gt=0),
    username: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    dao, _, _ = _deps(request)
    return await dao.list_submissions(problem_id=problem_id, username=username, limit=limit, offset=offset)


@router.get("/submissions/{sid}", response_model=SubmissionDetail)
async def get_submission(sid: int, request: Request):
    dao, _, _ = _deps(request)
    return await dao.get_submission(sid)


# ---------- custom run ----------


@router.post("/run", response_model=RunResult)
async def run(body: RunRequest, request: Request):
    dao, runner, _ = _deps(request)
    await _require_language(request, body.language)
    time_limit, memory_limit = 2000, 256
    if body.problem_id is not None:
        p = await dao.get_problem(body.problem_id)
        time_limit, memory_limit = p["time_limit_ms"], p["memory_limit_mb"]
    resp = await runner.execute(
        language=body.language,
        source=body.source,
        tests=[{"id": "custom", "stdin": body.stdin}],
        time_limit_ms=time_limit,
        memory_limit_mb=memory_limit,
    )
    if resp["status"] == "CE":
        return RunResult(status="CE", compile_output=resp.get("compile_output", ""))
    if not resp.get("results"):
        raise Unavailable("runner returned no results")
    r = resp["results"][0]
    return RunResult(
        status=r["status"],
        stdout=r.get("stdout", ""),
        stderr=r.get("stderr", ""),
        exit_code=r.get("exit_code", 0),
        time_ms=r.get("time_ms", 0),
        memory_kb=r.get("memory_kb", 0),
    )
