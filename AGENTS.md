# AGENTS.md

Instructions for any AI coding agent (Claude Code, Codex, Cursor, Gemini, Aider, Copilot…) working in this repo.
Each service directory has its own `AGENTS.md` with its layout and rules; read it before changing that service.

## Layout

| Path | What |
|---|---|
| `proto/` | **Single source of truth for types shared by api, webapp and runner.** `oj/v1/*.proto` + `generate.py` |
| `api/` | Flask API, Python 3.13, Postgres + RabbitMQ. One image, two processes: HTTP (`gunicorn`) and `worker` |
| `webapp/` | SvelteKit 3 + Svelte 5 (runes) + Tailwind 4 + shadcn-svelte. Calls the api server-side |
| `runner/` | Go RabbitMQ consumer: sandboxed compile & execute of untrusted code |
| `rabbitmq/` | Broker config + `render_definitions.py` (users, permissions, queues) |
| `scripts/` | `setup.sh` (dev deps), `smoke.py` (end-to-end test of the running stack) |
| `docker-compose.yml` | postgres + rabbitmq + api + worker + runner × N + webapp |

```
browser ─> webapp ─proto JSON─> api ──────> postgres
                                 │ worker ──┘
                                 │ AMQP
                                 v
                              rabbitmq ── judge.jobs ──> runner × N
                                       <─ judge.events ──┘
```

## Architecture rules (reviewers enforce these)

### api: three layers, dependencies point downward only
- `app/controllers/`: HTTP only. Parse the request into a proto message, call **one** service method,
  return the proto response. Cross-cutting HTTP concerns (admin auth, rate limit, CORS, body limits,
  error → status mapping) live here too. No business logic, no SQL, no AMQP.
- `app/services/`: business logic and judging rules. Takes and returns proto messages
  (`app.gen.oj.v1.*_pb2`). Raises `app.errors.*`, never Flask responses. No Flask, SQL or pika imports.
- `app/repositories/`: all I/O (Postgres, RabbitMQ). Returns proto messages or records. No business rules.
- `app/worker.py`: the AMQP counterpart of a controller: decode a message, call one service, ack/requeue.
- Wiring happens in `create_app` (`app/__init__.py`): repositories are injected into services.
  `api/AGENTS.md` has the details.

### runner
- Never weaken the sandbox. It stays on the internal `jobs` network, acks a job only after its result is
  confirmed, and never sees expected outputs (judging happens in the api).

### Shared types (protobuf)
- To change any request/response/message shape, edit `proto/oj/v1/*.proto` and run `make gen`.
  It lints and regenerates `api/app/gen`, `runner/internal/gen` and `webapp/src/lib/gen`.
  Commit the `.proto` and the generated code together.
- **Never hand-edit generated code.** `make check-proto` (CI) fails if it is stale.
- Over HTTP: canonical proto JSON (camelCase, enums by name, int64 as strings → `bigint` in TS).
  The webapp validates every response with `fromJson(Schema, …)` in `webapp/src/lib/server/api.ts`.
- Between api and runner: binary protobuf over RabbitMQ. Keep it wire compatible (jobs can be queued
  across a deploy): never renumber, reuse or retype fields.
- The RabbitMQ topology is specified in the header of `proto/oj/v1/runner.proto`;
  `rabbitmq/render_definitions.py` and the api must match it exactly.

## Commands (repo root)

| What | Command |
|---|---|
| Install dev deps | `make setup` |
| Regenerate code from protos | `make gen` |
| Run every gate | `make check` (or `check-proto`, `check-api`, `check-runner`, `check-webapp`) |
| Integration tests | `make test-broker` + a Postgres; then `TEST_DATABASE_URL=… RABBITMQ_TEST_URL=amqp://oj:oj@127.0.0.1:5673/` (see `api/AGENTS.md`) |
| Full stack | `make env && make up` → http://localhost:8080 (api on 127.0.0.1:8000) |
| End-to-end | `make smoke` (API, verdicts, sandbox isolation), `make e2e` (Playwright vs the stack) |

## Test levels: put each test where it belongs
- **Unit**: api services with fake repositories (`api/tests/unit`); runner packages with fakes;
  webapp pure TS (`src/**/*.spec.ts`).
- **Functional**: api HTTP via the Flask test client, repositories against Postgres / RabbitMQ
  (gated on `TEST_DATABASE_URL` / `RABBITMQ_TEST_URL`) (`api/tests/functional`); runner against
  RabbitMQ; Svelte components in a real browser (`src/**/*.svelte.spec.ts`).
- **E2E**: the real stack: `scripts/smoke.py` and `webapp/e2e/*.e2e.ts`.

## Hard rules
- Never delete, skip or loosen a test or smoke check to make it pass (the only allowed skips are the
  env-gated Postgres/RabbitMQ tests).
- Never commit secrets. Configuration comes from env vars (see `.env.example`); new secrets also go in
  `SECRETS` in the Makefile.
- Keep `cap_drop: [ALL]`, `read_only` and `no-new-privileges` on every compose service; nothing but
  AMQP may listen on the `jobs` network.
- Keep changes minimal and on-task.
