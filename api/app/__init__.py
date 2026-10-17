"""App factory. Layers (dependencies point downward only):

controllers/   HTTP only (parse into a proto message, call ONE service method, serialize the response)
               + cross-cutting HTTP concerns; consumers.py is the same for RabbitMQ messages (worker)
services/      business logic on proto messages; raises app.errors; no Flask, no SQL, no pika
repositories/  all I/O: Postgres (SQLAlchemy Core + psycopg) and RabbitMQ (pika)
gen/           code generated from proto/ - never edit
worker.py      `python -m app.worker`: judge.events / judge.jobs.dead consumers + recovery sweep
"""

import logging

import click
from flask import Flask

from .config import Settings
from .controllers import register_controllers
from .controllers.http import MAX_ADMIN_BODY
from .controllers.rate_limit import RateLimiter
from .repositories import Repositories
from .services import build_services

log = logging.getLogger("app")


def create_app(settings: Settings | None = None, repositories: Repositories | None = None) -> Flask:
    """Wire repositories (real ones from settings, or fakes in tests) into services and controllers."""
    settings = settings or Settings.from_env()
    repositories = repositories or Repositories.from_settings(settings)

    app = Flask(__name__, static_folder=None)
    app.config.update(
        ADMIN_TOKEN=settings.admin_token,
        CORS_ORIGINS=list(settings.cors_origins),
        TRUST_PROXY_HEADERS=settings.trust_proxy_headers,
        MAX_CONTENT_LENGTH=MAX_ADMIN_BODY,
    )
    app.json.sort_keys = False
    app.extensions["settings"] = settings
    app.extensions["repositories"] = repositories
    app.extensions["services"] = build_services(settings, repositories)
    app.extensions["rate_limiter"] = RateLimiter(settings.rate_limit_per_min, settings.rate_limit_burst)
    register_controllers(app)

    if not settings.admin_token:
        log.warning("ADMIN_TOKEN not set: admin API disabled")
    elif len(settings.admin_token) < 16:
        log.warning("ADMIN_TOKEN is short; use at least 16 random characters")

    @app.cli.command("migrate")
    def migrate():
        """Apply pending migrations/*.sql (idempotent, advisory-locked; waits up to 60 s for Postgres)."""
        applied = repositories.database.migrate()
        click.echo(f"database migrated ({', '.join(applied) if applied else 'up to date'})")

    return app
