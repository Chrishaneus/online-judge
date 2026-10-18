"""gunicorn settings for the api (see README.md).

ONE worker process with API_THREADS threads (gthread): the per-client rate limiter lives in process
memory, so a single process keeps it exact. Scale with threads (or replicas behind a shared limiter).
Works on a read-only root filesystem: the worker heartbeat file goes to /tmp (a tmpfs).
"""

import os

from gunicorn.glogging import Logger

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = 1
worker_class = "gthread"
threads = int(os.environ.get("API_THREADS", "16"))
worker_tmp_dir = os.environ.get("GUNICORN_TMP_DIR", "/tmp")
# Requests may legitimately wait RUN_TIMEOUT_S for a runner; gthread keeps heartbeating meanwhile.
timeout = 60
graceful_timeout = int(float(os.environ.get("RUN_TIMEOUT_S", "30"))) + 5
keepalive = 5
# No runtime control socket (it would need a writable home directory).
control_socket_disable = True
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s "%(r)s" %(s)s %(B)s %(M)sms request_id=%({x-request-id}o)s'


class AccessLogger(Logger):
    """gunicorn's access log without the /healthz probes."""

    def access(self, resp, req, environ, request_time):
        if environ.get("PATH_INFO") == "/healthz":
            return
        super().access(resp, req, environ, request_time)


logger_class = AccessLogger


def post_worker_init(worker):
    """Declare the RabbitMQ topology at startup (best effort: each new connection declares it too)."""
    try:
        worker.wsgi.extensions["repositories"].queue.connect()
    except Exception as exc:  # noqa: BLE001 - broker not up yet: requests connect lazily
        worker.log.warning("RabbitMQ not reachable at startup (%s)", exc)
