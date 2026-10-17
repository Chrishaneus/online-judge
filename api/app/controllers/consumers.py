"""RabbitMQ consumers (the worker's "controllers"): decode the message, call ONE service method, decide
ack vs. requeue.

Handlers return True to ack and False to requeue (database unavailable). Undecodable messages are
acked and logged: redelivering them can never succeed.
"""

import logging

from google.protobuf.message import DecodeError

from app.errors import Unavailable
from app.gen.oj.v1 import runner_pb2
from app.services import SubmissionService

log = logging.getLogger(__name__)


class JudgeConsumers:
    def __init__(self, submissions: SubmissionService):
        self.submissions = submissions

    def on_job_event(self, body: bytes) -> bool:
        """judge.events"""
        try:
            event = runner_pb2.JobEvent.FromString(body)
        except DecodeError:
            log.warning("judge.events: dropping undecodable message (%d bytes)", len(body))
            return True
        try:
            self.submissions.handle_job_event(event)
        except Unavailable as err:
            log.warning("judge.events: %s; requeueing %s", err.message, event.job_id)
            return False
        return True

    def on_dead_job(self, body: bytes) -> bool:
        """judge.jobs.dead"""
        try:
            job = runner_pb2.ExecuteJob.FromString(body)
        except DecodeError:
            log.warning("judge.jobs.dead: dropping undecodable message (%d bytes)", len(body))
            return True
        log.warning(
            "judge.jobs.dead: job %s (submission %d) was dead-lettered", job.job_id, job.submission_id
        )
        try:
            self.submissions.handle_dead_job(job)
        except Unavailable as err:
            log.warning("judge.jobs.dead: %s; requeueing %s", err.message, job.job_id)
            return False
        return True
