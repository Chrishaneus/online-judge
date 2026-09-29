# AGENTS.md

Instructions for any AI coding agent working in oj-midlayer (the Online Judge's business logic:
gRPC `oj.v1.JudgeService` server, oj-dao gRPC client, RabbitMQ publisher/consumer).

## Architecture rules (reviewers enforce these)

### Three layers, dependencies point downward only
- `app/transport/`: gRPC and AMQP only. The servicer parses the request (already a proto message),
  calls **one** service method and returns its response; `app.errors.*` become gRPC status codes there.
  RabbitMQ consumers decode the message, call one service method and return ack (True) / requeue
  (False). No business logic.
- `app/services/`: business logic. Takes and returns proto messages (`app.gen.oj.v1.*_pb2`). Raises
  `app.errors.*` (`ValidationError` with a field-specific message, `NotFound`, `ResourceExhausted`, ...).
  **No `grpc` or `aio_pika` imports.** Talks to I/O only through the repository interfaces in
  `app/services/ports.py`.
- `app/repositories/`: all I/O (oj-dao over gRPC, RabbitMQ over AMQP). Translates transport errors into
  `app.errors` (`NotFound`, `AlreadyExists`, `PreconditionFailed`, `Unavailable`, ...). No business rules.
- Wiring happens in `app/__init__.py` (`create_app(settings, dao=..., queue=...)`): repositories are
  injected into services. Configuration comes from env vars via `app/config.py`.

### Contract (protobuf)
- The contract lives in the sibling repo **oj-proto** (`oj/v1/*.proto`). To change a message or RPC, edit it
  there and run `make gen`; never redeclare shapes here.
- **Never hand-edit `app/gen/`.** It is generated and committed.
- The RabbitMQ topology and AMQP properties are specified in the header of `oj-proto/oj/v1/runner.proto`;
  `JobQueue` must declare queues with exactly those arguments.

### Judging invariants
- Every submission status write from the judging pipeline uses compare-and-set (`expected_statuses`);
  `PreconditionFailed` means a late/duplicate event and is ignored. Messages are acked only after the
  dao write; `Unavailable` means requeue.
- Hidden test cases never leave the midlayer (only samples in `GetProblemDetail`).

## Commands (cwd: repo root)

| What | Command |
|---|---|
| Setup | `uv venv --python 3.13 .venv && uv pip install --python .venv -r requirements-dev.txt` |
| Lint | `.venv/bin/ruff check . && .venv/bin/ruff format --check .` |
| Unit tests | `.venv/bin/pytest tests/unit` |
| Functional tests | `.venv/bin/pytest tests/functional` |
| With a real broker | `RABBITMQ_TEST_URL=amqp://oj:oj@127.0.0.1:5673/ .venv/bin/pytest` |
| Run | `.venv/bin/python -m app` (needs oj-dao and RabbitMQ) |
| Image | `docker build -t online-judge/midlayer:latest .` |

## Test levels: put each test where it belongs
- **Unit** (`tests/unit`): services and consumer handlers with the fakes in `tests/fakes.py`
  (no network). Judging rules, validation, submit/run, the events/dead-letter pipeline, recovery.
- **Functional** (`tests/functional`): the gRPC servicer through a real in-process grpc.aio server on a
  free port with fake repositories (status-code mapping, health, interceptor); `JobQueue` and the wired
  app against a real RabbitMQ, gated on `RABBITMQ_TEST_URL` (the only acceptable skip). Broker tests use
  a unique queue-name prefix per test and delete their queues.

## Hard rules
- Never delete, skip or loosen a test to make it pass.
- Never commit secrets; configuration comes from env vars.
- Keep changes minimal and on-task. All gates (lint + tests) must pass before committing.
