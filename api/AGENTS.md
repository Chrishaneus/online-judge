# AGENTS.md

Instructions for any AI coding agent working in `api/` (the Online Judge backend: Flask HTTP API +
RabbitMQ worker, Python 3.13, SQLAlchemy Core + psycopg on Postgres, pika on RabbitMQ). See README.md
for routes, message flow and configuration.

## Architecture rules (reviewers enforce these)

### Three layers, dependencies point downward only
- `app/controllers/`: HTTP only. A route parses the request into a proto message (`parse_body`,
  `path_id`, `query_int32`), calls **one** service method and returns `proto_response(...)` (or
  `no_content()` for 204). No business logic, no DB or broker access. Cross-cutting HTTP concerns live in
  `controllers/http.py` (request id, CORS, body limits, admin auth, rate limit, mapping of `app.errors`
  to status + `oj.v1.ErrorResponse`). `controllers/consumers.py` is the same for RabbitMQ messages:
  decode, call one service method, return ack (True) / requeue (False).
- `app/services/`: business logic. Takes and returns proto messages (`app.gen.oj.v1.*_pb2`). Raises
  `app.errors.*` (`ValidationError` naming the field → 422, `NotFound` → 404, `Conflict` → 409,
  `QueueFull` → 429, `Timeout` → 504, `Unavailable` → 503). **No Flask, SQL or pika imports.** Talks to
  I/O only through the interfaces in `app/services/ports.py`.
- `app/repositories/`: all I/O (Postgres, RabbitMQ). Returns proto messages or the plain records in
  `records.py`; translates driver errors into `app.errors` (`NotFound`, `Conflict`, `PreconditionFailed`,
  `Unavailable`). No business rules. Enum ⇄ stored-string mapping only in `codecs.py`.
- Wiring happens in `app/__init__.py` (`create_app(settings, repositories)`) and `app/worker.py`;
  repositories are injected into services (`build_services`), so tests pass fakes.

### Contract (protobuf)
- The HTTP JSON, the RabbitMQ messages and the topology are defined in `../proto/oj/v1/*.proto`. Change
  them there and run `make gen` at the repo root; never redeclare shapes here.
- **Never hand-edit `app/gen/`.**
- Over HTTP: canonical proto JSON via `json_format` (camelCase, enums by name, int64 as strings, defaults
  emitted). Unknown request fields are rejected (400). Keep status codes and error shapes stable: the
  webapp and `scripts/smoke.py` depend on them.
- `JobQueue` must declare queues with exactly the arguments in the header of `runner.proto`.

### Invariants
- Every submission status write from the judging pipeline is a compare-and-set (`expected_statuses`);
  `PreconditionFailed` means a late/duplicate event and is ignored. Messages are acked only after the
  database write; `Unavailable` means requeue.
- Hidden test cases never leave the api (only samples in problem detail; admins list all test cases).
- The schema is owned by `migrations/*.sql` (copied from dao): add new numbered files, never edit an
  applied one; keep the `schema_migrations` table and advisory lock id 727001.
- One gunicorn process (gthread): the rate limiter is in memory. pika connections are per thread.

## Commands (cwd: `api/`)

| What | Command |
|---|---|
| Setup | `uv venv --python 3.13 .venv && uv pip install --python .venv -r requirements-dev.txt` |
| Lint | `.venv/bin/ruff check . && .venv/bin/ruff format --check .` |
| Unit tests | `.venv/bin/pytest tests/unit` |
| Functional tests | `.venv/bin/pytest tests/functional` |
| With real services | `TEST_DATABASE_URL=postgresql+psycopg://oj:oj@127.0.0.1:55432/oj_test RABBITMQ_TEST_URL=amqp://oj:oj@127.0.0.1:5673/ .venv/bin/pytest` (throwaway Postgres container + `make test-broker`; tables are truncated/dropped) |
| Migrate | `.venv/bin/flask --app wsgi migrate` |
| Run | `.venv/bin/gunicorn -c gunicorn.conf.py wsgi:app` and `.venv/bin/python -m app.worker` |
| Image | `docker build -t online-judge/api:latest .` |

## Test levels: put each test where it belongs
- **Unit** (`tests/unit`): services and consumer handlers with the fakes in `tests/fakes.py` (no
  network): judging rules, validation, submit/run, events/dead-letter pipeline, recovery, codecs, rate
  limiter, worker healthcheck.
- **Functional** (`tests/functional`): HTTP through the Flask test client — the contract with a recording
  service double (`test_http_contract.py`) and flows through the real services with fake repositories
  (`test_api_flows.py`); repositories and migrations against real Postgres (`TEST_DATABASE_URL`);
  `JobQueue` and the worker against real RabbitMQ (`RABBITMQ_TEST_URL`); the full stack with both
  (`test_end_to_end.py`). Broker tests use a unique queue-name prefix and delete their queues.
- **E2E**: `scripts/smoke.py` and `webapp/e2e` against the running compose stack.

## Hard rules
- Never delete, skip or loosen a test to make it pass. The only acceptable skips are the env-gated
  Postgres / RabbitMQ tests.
- Never commit secrets; configuration comes from env vars.
- Keep changes minimal and on-task. All gates (lint + tests) must pass before committing.
