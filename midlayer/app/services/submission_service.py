"""Submissions: submit, public views, and the judging pipeline driven by RabbitMQ events."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from google.protobuf.timestamp_pb2 import Timestamp

from app.errors import AppError, NotFound, PreconditionFailed, ResourceExhausted, Unavailable
from app.gen.oj.v1 import dao_pb2, judge_pb2, runner_pb2, types_pb2

from . import validation
from .judging import OPEN_STATUSES, evaluate, failed_update
from .ports import Dao, Queue

log = logging.getLogger(__name__)

DEAD_LETTER_MESSAGE = "Judging failed: runner crashed or job expired"
NO_TEST_CASES_MESSAGE = "Problem has no test cases"
PUBLISH_FAILED_MESSAGE = "Judging failed: could not queue the submission"
RECOVER_PAGE_SIZE = 500


def job_id_for(submission_id: int) -> str:
    return f"submission-{submission_id}"


def build_job(
    submission: types_pb2.Submission, problem: types_pb2.Problem, test_cases: list[types_pb2.TestCase]
) -> runner_pb2.ExecuteJob:
    return runner_pb2.ExecuteJob(
        job_id=job_id_for(submission.id),
        submission_id=submission.id,
        language=submission.language,
        source=submission.source,
        tests=[runner_pb2.TestInput(id=str(tc.id), stdin=tc.input) for tc in test_cases],
        time_limit_ms=problem.time_limit_ms,
        memory_limit_mb=problem.memory_limit_mb,
    )


def to_summary(s: types_pb2.Submission) -> types_pb2.Submission:
    """List view: no source, message or per-test results."""
    out = types_pb2.Submission()
    out.CopyFrom(s)
    out.ClearField("source")
    out.ClearField("message")
    out.ClearField("results")
    return out


class SubmissionService:
    def __init__(
        self,
        dao: Dao,
        queue: Queue,
        *,
        max_queue_depth: int = 1000,
        recover_after_s: float = 300.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.dao = dao
        self.queue = queue
        self.max_queue_depth = max_queue_depth
        self.recover_after_s = recover_after_s
        self.clock = clock

    # ---------- public API ----------

    async def submit(self, req: judge_pb2.SubmitRequest) -> judge_pb2.SubmitResponse:
        problem_id = validation.require_id(req.problem_id, "problem_id")
        language = validation.language(req.language)
        source = validation.source(req.source)
        username = validation.username(req.username)

        depth, _ = await self.queue.queue_stats()
        if depth >= self.max_queue_depth:
            raise ResourceExhausted("The judging queue is full, try again later")

        problem = await self.dao.get_problem(problem_id)
        test_cases = await self.dao.list_test_cases(problem_id)
        submission = await self.dao.create_submission(
            types_pb2.Submission(problem_id=problem_id, username=username, language=language, source=source)
        )
        if not test_cases:
            submission = await self.dao.update_submission(failed_update(submission.id, NO_TEST_CASES_MESSAGE))
            return judge_pb2.SubmitResponse(submission=submission)

        try:
            await self.queue.publish_submission_job(build_job(submission, problem, test_cases))
        except Unavailable:
            await self._mark_failed_quietly(submission.id, PUBLISH_FAILED_MESSAGE)
            raise
        return judge_pb2.SubmitResponse(submission=submission)

    async def list_submission_summaries(
        self, req: judge_pb2.ListSubmissionSummariesRequest
    ) -> judge_pb2.ListSubmissionSummariesResponse:
        limit, offset = validation.page(req.limit, req.offset)
        submissions = await self.dao.list_submissions(
            dao_pb2.ListSubmissionsRequest(
                problem_id=validation.optional_id(req.problem_id, "problem_id"),
                username=validation.username_filter(req.username),
                limit=limit,
                offset=offset,
            )
        )
        return judge_pb2.ListSubmissionSummariesResponse(submissions=[to_summary(s) for s in submissions])

    async def get_submission_detail(
        self, req: judge_pb2.GetSubmissionDetailRequest
    ) -> judge_pb2.GetSubmissionDetailResponse:
        submission = await self.dao.get_submission(validation.require_id(req.id))
        return judge_pb2.GetSubmissionDetailResponse(submission=submission)

    # ---------- judging pipeline (RabbitMQ consumers) ----------

    async def handle_job_event(self, event: runner_pb2.JobEvent) -> None:
        """judge.events: `started` -> JUDGING, `finished` -> verdict. Raises Unavailable to retry."""
        sid = event.submission_id
        kind = event.WhichOneof("event")
        if sid <= 0 or kind is None:
            log.warning("ignoring job event %r (%s) without submission", event.job_id, kind)
            return
        if kind == "started":
            req = dao_pb2.UpdateSubmissionRequest(
                id=sid,
                status=types_pb2.SUBMISSION_STATUS_JUDGING,
                expected_statuses=[types_pb2.SUBMISSION_STATUS_PENDING],
            )
            await self._update_ignoring_stale(req, f"started by {event.runner_id}")
            return

        result = event.finished
        if result.status in (runner_pb2.EXECUTE_STATUS_OK, runner_pb2.EXECUTE_STATUS_COMPILATION_ERROR):
            try:
                submission = await self.dao.get_submission(sid)
                test_cases = await self.dao.list_test_cases(submission.problem_id)
            except NotFound:
                log.info("submission %d or its problem is gone; dropping result", sid)
                return
            outcome = evaluate(test_cases, result)
            req = outcome.as_update(sid)
            summary = f"{types_pb2.Verdict.Name(outcome.verdict)} ({outcome.passed}/{outcome.total})"
        else:
            status = runner_pb2.ExecuteStatus.Name(result.status)
            log.error("runner reported %s for submission %d: %s", status, sid, result.error)
            req = failed_update(sid, f"Judging failed: {result.error or status}")
            summary = f"FAILED ({status})"
        await self._update_ignoring_stale(req, summary)

    async def handle_dead_job(self, job: runner_pb2.ExecuteJob) -> None:
        """judge.jobs.dead: the job crashed runners or expired. Custom runs are just dropped."""
        if job.submission_id <= 0:
            return
        await self._update_ignoring_stale(
            failed_update(job.submission_id, DEAD_LETTER_MESSAGE), "FAILED (dead)"
        )

    async def recover(self) -> int:
        """Re-publish submissions stuck in PENDING/JUDGING for longer than recover_after_s.

        Duplicates are harmless: results are stored with compare-and-set on the status.
        """
        updated_before = Timestamp()
        updated_before.FromDatetime(self.clock() - timedelta(seconds=self.recover_after_s))
        problems: dict[int, tuple[types_pb2.Problem, list[types_pb2.TestCase]]] = {}
        republished, offset = 0, 0
        while True:
            page = await self.dao.list_submissions(
                dao_pb2.ListSubmissionsRequest(
                    statuses=OPEN_STATUSES,
                    updated_before=updated_before,
                    limit=RECOVER_PAGE_SIZE,
                    offset=offset,
                )
            )
            for submission in page:
                try:
                    if submission.problem_id not in problems:
                        pid = submission.problem_id
                        problems[pid] = (await self.dao.get_problem(pid), await self.dao.list_test_cases(pid))
                    problem, test_cases = problems[submission.problem_id]
                    if not test_cases:
                        await self._update_ignoring_stale(
                            failed_update(submission.id, NO_TEST_CASES_MESSAGE), "FAILED (no tests)"
                        )
                        continue
                    await self.queue.publish_submission_job(build_job(submission, problem, test_cases))
                    republished += 1
                except NotFound:
                    log.info("submission %d: problem is gone, skipping", submission.id)
            if len(page) < RECOVER_PAGE_SIZE:
                break
            offset += RECOVER_PAGE_SIZE
        if republished:
            log.info("re-published %d unfinished submissions", republished)
        return republished

    # ---------- helpers ----------

    async def _update_ignoring_stale(self, req: dao_pb2.UpdateSubmissionRequest, what: str) -> None:
        try:
            await self.dao.update_submission(req)
        except PreconditionFailed:
            log.info("submission %d: ignoring late or duplicate update (%s)", req.id, what)
        except NotFound:
            log.info("submission %d: no longer exists, ignoring update (%s)", req.id, what)
        else:
            log.info("submission %d: %s", req.id, what)

    async def _mark_failed_quietly(self, submission_id: int, message: str) -> None:
        try:
            await self.dao.update_submission(failed_update(submission_id, message))
        except AppError:
            log.exception("could not mark submission %d as failed", submission_id)
