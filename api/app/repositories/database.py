"""Postgres connection pool (SQLAlchemy Core + psycopg 3), driver-error translation and migrations."""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from sqlalchemy import Connection, create_engine, make_url, text
from sqlalchemy.exc import DBAPIError, IntegrityError, InterfaceError, OperationalError

from app.errors import AppError, Conflict, NotFound, Unavailable

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
# Same key as dao's internal/store/migrate.go, so api and an old dao never migrate concurrently.
MIGRATION_LOCK_ID = 727_001
CONNECT_TIMEOUT_S = 5

UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"


def normalize_url(url: str) -> str:
    """Accept postgres:// and postgresql:// DSNs too; always use the psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def translate(err: DBAPIError) -> Exception:
    """Driver error -> app.errors (or the original error, which becomes a 500)."""
    if isinstance(err, OperationalError | InterfaceError) or err.connection_invalidated:
        return Unavailable(f"database unavailable: {type(err.orig).__name__}")
    if isinstance(err, IntegrityError):
        state = getattr(err.orig, "sqlstate", None)
        if state == UNIQUE_VIOLATION:
            return Conflict("already exists")
        if state == FOREIGN_KEY_VIOLATION:
            return NotFound("not found")
    return err


class Database:
    """Owns the engine. Repositories run each operation in one transaction via begin()."""

    def __init__(self, url: str, *, pool_size: int = 16):
        self.url = normalize_url(url)
        self.engine = create_engine(
            self.url,
            pool_size=pool_size,
            max_overflow=4,
            pool_pre_ping=True,
            pool_timeout=10,
            connect_args={"connect_timeout": CONNECT_TIMEOUT_S},
        )

    @contextmanager
    def begin(self) -> Iterator[Connection]:
        try:
            with self.engine.begin() as conn:
                yield conn
        except DBAPIError as err:
            translated = translate(err)
            if translated is err:
                raise
            raise translated from err

    def ping(self) -> None:
        """Raises Unavailable unless `SELECT 1` succeeds."""
        with self.begin() as conn:
            conn.execute(text("SELECT 1"))

    def dispose(self) -> None:
        self.engine.dispose()

    # ---------- migrations ----------

    def _libpq_dsn(self) -> str:
        return make_url(self.url).set(drivername="postgresql").render_as_string(hide_password=False)

    def migrate(self, migrations_dir: Path = MIGRATIONS_DIR, wait_s: float = 60.0) -> list[str]:
        """Apply migrations/*.sql not yet recorded in schema_migrations, in name order, each in its own
        transaction, under a session advisory lock (safe with concurrent starts). Returns the versions
        applied. Compatible with a database dao already migrated: same table, same versions, same lock.
        Waits up to wait_s for the database to accept connections."""
        deadline = time.monotonic() + wait_s
        while True:
            try:
                conn = psycopg.connect(self._libpq_dsn(), autocommit=True, connect_timeout=CONNECT_TIMEOUT_S)
                break
            except psycopg.OperationalError as exc:
                if time.monotonic() >= deadline:
                    raise Unavailable(f"database unavailable: {exc}") from exc
                log.warning("database not reachable yet (%s); retrying", str(exc).strip().splitlines()[0])
                time.sleep(1)

        applied: list[str] = []
        with conn:
            conn.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_ID,))
            try:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS schema_migrations (
                        version    TEXT PRIMARY KEY,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )"""
                )
                for path in sorted(migrations_dir.glob("*.sql"), key=lambda p: p.name):
                    version = path.name
                    row = conn.execute(
                        "SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = %s)", (version,)
                    ).fetchone()
                    if row and row[0]:
                        continue
                    with conn.transaction():
                        # No parameters: psycopg sends the file as-is (several statements allowed).
                        conn.execute(path.read_text())
                        conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
                    log.info("applied migration %s", version)
                    applied.append(version)
            except psycopg.Error as exc:
                raise AppError(f"migration failed: {exc}") from exc
            finally:
                if not conn.closed:
                    conn.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_ID,))
        return applied
