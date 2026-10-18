"""Worker health file and healthcheck command (no broker needed)."""

import os
import time

from app.worker import healthcheck, main


def test_healthcheck_reads_the_file_age(tmp_path):
    path = tmp_path / "healthy"
    assert healthcheck(str(path)) is False  # missing
    path.touch()
    assert healthcheck(str(path)) is True
    old = time.time() - 21
    os.utime(path, (old, old))
    assert healthcheck(str(path)) is False


def test_healthcheck_command_exit_code(tmp_path, monkeypatch):
    path = tmp_path / "healthy"
    monkeypatch.setenv("WORKER_HEALTH_FILE", str(path))
    assert main(["app.worker", "healthcheck"]) == 1
    path.touch()
    assert main(["app.worker", "healthcheck"]) == 0
