# midlayer

Business-logic layer of the Online Judge (Python 3.13, grpc.aio, aio-pika).

* Serves **`oj.v1.JudgeService`** over gRPC (`:50051`). rest maps it to `/api/v1`.
* Persists everything through **dao** (`oj.v1.DaoService`, gRPC client).
* Judges through **RabbitMQ**: it publishes an `ExecuteJob` per submission to
  `judge.jobs`, consumes the runners' `JobEvent`s from `judge.events`, compares
  outputs, computes the verdict and stores it.
* Owns the **judging rules**: output normalisation (CRLF/CR == LF, trailing
  whitespace on each line and trailing blank lines are ignored, leading
  whitespace and inner blank lines are significant) and verdict precedence (the
  verdict of the first failing test, else ACCEPTED).
* Shapes public data: problem details only expose sample tests; submission
  listings omit source, message and per-test results.
* Validates domain input (slug, title, limits, languages, usernames, sizes).

Authentication, rate limits and CORS live in rest. The contract (all
messages, the gRPC APIs and the RabbitMQ topology) lives in **proto**; the
generated code is in `app/gen/` and must never be edited by hand.

## Layers

Dependencies point downward only (see `AGENTS.md`).

| Path | Role |
|---|---|
| `app/transport/` | `JudgeServicer` (gRPC: parse, call one service method, map `app.errors` to status codes), `JudgeConsumers` (decode RabbitMQ messages, call a service, ack or requeue), logging interceptor |
| `app/services/` | Business logic on proto messages: `validation`, `judging` (rules), problems, submissions (submit + judging pipeline + recovery), runs, status, languages |
| `app/repositories/` | All I/O: `DaoRepository` (grpc.aio DaoService stub, gRPC errors to `app.errors`), `JobQueue` (aio-pika: topology, publisher confirms, RPC reply queue, queue stats, consumers) |
| `app/__init__.py` | `create_app(settings, dao=..., queue=...)`: wiring; `App.start()` / `App.stop()` |
| `app/__main__.py` | `python -m app`: runs the server until SIGTERM |
| `app/healthcheck.py` | `python -m app.healthcheck`: exits 0 iff the local `grpc.health.v1.Health` reports SERVING |

## gRPC API

`oj.v1.JudgeService` (see `proto/oj/v1/judge.proto` for every field):
`GetStatus`, `ListLanguages`, `ListProblemSummaries`, `GetProblemDetail`,
`Submit`, `ListSubmissionSummaries`, `GetSubmissionDetail`, `RunCode`, and the
admin RPCs `AddProblem`, `EditProblem`, `RemoveProblem`,
`ListProblemTestCases`, `AddTestCase`, `RemoveTestCase`.

| Status | When |
|---|---|
| `INVALID_ARGUMENT` | validation failed; the message names the field |
| `NOT_FOUND` | problem / submission / test case not found |
| `ALREADY_EXISTS` | duplicate problem slug |
| `RESOURCE_EXHAUSTED` | `judge.jobs` holds `MAX_QUEUE_DEPTH` or more jobs (checked before creating) |
| `DEADLINE_EXCEEDED` | `RunCode` got no answer within `RUN_TIMEOUT_S` |
| `UNAVAILABLE` | dao or RabbitMQ unreachable, or the runner failed a custom run |
| `INTERNAL` | anything unexpected (logged; details not leaked) |

The standard `grpc.health.v1.Health` service reports SERVING (for `""` and
`oj.v1.JudgeService`) once the broker is connected and the server started.
Max message size is 64 MiB both ways. Each RPC is logged with method, status
code, duration and the `x-request-id` metadata set by rest.

## Message flow

Topology and AMQP properties follow the header of `proto/oj/v1/runner.proto`.
At startup the midlayer re-declares the quorum queues with identical arguments
(`judge.jobs`: `x-delivery-limit=3`, dead-lettered to `judge.jobs.dead`).

```
Submit ─> dao.CreateSubmission (PENDING) ─> publish ExecuteJob to judge.jobs
            job_id "submission-<id>", correlation_id = job_id, reply_to = judge.events,
            persistent, publisher confirm. Publish fails -> FAILED/INTERNAL_ERROR + UNAVAILABLE.

runner ─> judge.events  started  -> UpdateSubmission JUDGING   if status in [PENDING]
                        finished -> evaluate -> FINISHED + verdict if status in [PENDING, JUDGING]
                                    REJECTED / INTERNAL_ERROR -> FAILED / INTERNAL_ERROR
        A FAILED_PRECONDITION (late or duplicate event) is ignored. Acked after the dao write;
        dao unavailable -> nack + requeue after a short delay.

judge.jobs.dead ─> submission jobs: FAILED / INTERNAL_ERROR (same CAS); custom runs: ack.

RunCode ─> publish ExecuteJob (UUID job_id, reply_to = this instance's exclusive reply queue,
           AMQP expiration = RUN_TIMEOUT_S) and wait for the `finished` event.
```

Startup recovery: submissions in PENDING/JUDGING not updated for
`RECOVER_AFTER_S` are re-published (duplicates are harmless thanks to the
compare-and-set). Failure is logged, not fatal.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `GRPC_ADDR` | `[::]:50051` | Listen address |
| `DAO_ADDR` | `localhost:50052` | dao gRPC address |
| `DAO_TIMEOUT_S` | `10` | Deadline for each dao call |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Broker URL |
| `RUN_TIMEOUT_S` | `30` | `RunCode` wait (and the job's AMQP expiration) |
| `MAX_QUEUE_DEPTH` | `1000` | `Submit` returns RESOURCE_EXHAUSTED at this depth |
| `RECOVER_AFTER_S` | `300` | Age after which open submissions are re-published at startup |

RabbitMQ permissions for the midlayer user (vhost of `RABBITMQ_URL`):
configure `^(judge\.jobs|judge\.jobs\.dead|judge\.events|judge\.rpc\..*)$`,
write `^amq\.default$`,
read `^(judge\.jobs\.dead|judge\.events|judge\.rpc\..*)$`.
The reply queue is named `judge.rpc.<uuid>` by the midlayer (not server-named)
so that it survives a reconnect.

## Development

```bash
uv venv --python 3.13 .venv && uv pip install --python .venv -r requirements-dev.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/pytest tests/unit
.venv/bin/pytest tests/functional            # broker tests skip unless RABBITMQ_TEST_URL is set
RABBITMQ_TEST_URL=amqp://oj:oj@127.0.0.1:5673/ .venv/bin/pytest
.venv/bin/python -m app                     # needs dao and RabbitMQ
docker build -t online-judge/midlayer:latest .
```

Regenerate `app/gen/` from proto with `make gen` at the repo root.
