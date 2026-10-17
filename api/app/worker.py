"""Worker process (same image as the api): `python -m app.worker`.

* consumes judge.events (runner JobEvents -> verdicts) and judge.jobs.dead (-> FAILED) through
  controllers/consumers.py, reconnecting to RabbitMQ as needed;
* at startup, in a background thread, re-publishes submissions left PENDING/JUDGING for longer than
  RECOVER_AFTER_S (failure is logged, not fatal);
* touches WORKER_HEALTH_FILE at least every second while its consumers are active.

`python -m app.worker healthcheck` exits 0 iff that file was touched less than 20 s ago.
Runs a single consumer thread: events are handled one at a time (a few ms each).
"""

import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

from .config import Settings
from .controllers.consumers import JudgeConsumers
from .repositories import Repositories
from .services import Services, build_services

log = logging.getLogger("app.worker")

HEALTHY_WITHIN_S = 20.0


class Worker:
    def __init__(self, settings: Settings, repositories: Repositories, services: Services | None = None):
        self.settings = settings
        self.repositories = repositories
        self.services = services or build_services(settings, repositories)
        self.consumers = JudgeConsumers(self.services.submissions)
        self.stop_event = threading.Event()
        self.health_file = Path(settings.worker_health_file)

    def touch_health_file(self) -> None:
        try:
            self.health_file.touch()
        except OSError:
            log.warning("cannot write health file %s", self.health_file, exc_info=True)

    def recover(self) -> None:
        try:
            self.services.submissions.recover()
        except Exception:
            log.exception("recovery of unfinished submissions failed")

    def run(self, *, recover: bool = True) -> None:
        """Consume until stop() is called."""
        if recover:
            threading.Thread(target=self.recover, name="recovery", daemon=True).start()
        q, s = self.repositories.queue, self.settings
        q.consume(
            {s.events_queue: self.consumers.on_job_event, s.dead_queue: self.consumers.on_dead_job},
            stop=self.stop_event,
            on_tick=self.touch_health_file,
            prefetch=s.prefetch,
            requeue_delay_s=s.requeue_delay_s,
        )
        self.health_file.unlink(missing_ok=True)
        q.close()

    def stop(self) -> None:
        self.stop_event.set()


def healthcheck(path: str, max_age_s: float = HEALTHY_WITHIN_S) -> bool:
    try:
        return time.time() - os.stat(path).st_mtime < max_age_s
    except OSError:
        return False


def main(argv: list[str]) -> int:
    settings = Settings.from_env()
    if argv[1:2] == ["healthcheck"]:
        return 0 if healthcheck(settings.worker_health_file) else 1

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("pika").setLevel(logging.WARNING)
    worker = Worker(settings, Repositories.from_settings(settings))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: worker.stop())
    log.info("worker starting (events=%s, dead=%s)", settings.events_queue, settings.dead_queue)
    worker.run()
    log.info("worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
