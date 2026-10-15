# AGENTS.md

Instructions for any AI coding agent (Claude Code, Codex, Cursor, Gemini, Aider, Copilot…) working in this repo.
Each service directory has its own `AGENTS.md` with its layout and rules; read it before changing that service.

## Layout

| Path | What |
|---|---|
| `proto/` | **Single source of truth for types shared by every service.** `oj/v1/*.proto` + `generate.py` |
| `webapp/` | SvelteKit 3 + Svelte 5 (runes) + Tailwind 4 + shadcn-svelte. Calls rest server-side |
| `rest/` | Go public REST edge `/api/v1`: proto JSON ⇄ gRPC, admin auth, rate limits, CORS |
| `midlayer/` | Python 3.13 grpc.aio `JudgeService`: business logic, judging rules, RabbitMQ publisher/consumer |
| `dao/` | Go gRPC `DaoService`: the only service that touches PostgreSQL |
| `runner/` | Go RabbitMQ consumer: sandboxed compile & execute of untrusted code |
| `rabbitmq/` | Broker config + `render_definitions.py` (users, permissions, queues) |
| `scripts/` | `setup.sh` (dev deps), `smoke.py` (end-to-end test of the running stack) |
| `docker-compose.yml` | postgres + dao + rabbitmq + runner × N + midlayer + rest + webapp |

```
browser ─> webapp ─proto JSON─> rest ─gRPC─> midlayer ─gRPC─> dao ─> postgres
                                               │ AMQP
                                               v
                                            rabbitmq ── judge.jobs ──> runner × N
                                                     <─ judge.events ──┘
```

## Architecture rules (reviewers enforce these)

- **Dependencies point one way**: webapp → rest → midlayer → dao. Only dao touches the DB;
  only midlayer and runner touch RabbitMQ; the browser never calls rest directly.
- **rest is translation only**: parse → one RPC → write. No business rules.
- **midlayer has three layers** (`app/transport` → `app/services` → `app/repositories`), as in
  `midlayer/AGENTS.md`. Services take and return proto messages and never import grpc/aio_pika.
- **runner never weakens the sandbox**: it stays on the internal `jobs` network, acks a job only
  after its result is confirmed, and never sees expected outputs (judging happens in midlayer).

### Shared types (protobuf)
- To change any request/response/message shape, edit `proto/oj/v1/*.proto` and run `make gen`.
  It lints and regenerates `dao/internal/gen`, `rest/internal/gen`, `runner/internal/gen`,
  `midlayer/app/gen` and `webapp/src/lib/gen`. Commit the `.proto` and the generated code together.
- **Never hand-edit generated code.** `make check-proto` (CI) fails if it is stale.
- Over HTTP: canonical proto JSON (camelCase, enums by name, int64 as strings → `bigint` in TS).
  Between services: binary protobuf over gRPC or RabbitMQ.
- Keep the contract wire compatible (services deploy independently): never renumber, reuse or retype fields.
- The RabbitMQ topology is specified in the header of `proto/oj/v1/runner.proto`;
  `rabbitmq/render_definitions.py` and midlayer must match it exactly.

## Commands (repo root)

| What | Command |
|---|---|
| Install dev deps | `make setup` |
| Regenerate code from protos | `make gen` |
| Run every gate | `make check` (or `check-proto`, `check-dao`, `check-rest`, `check-runner`, `check-midlayer`, `check-webapp`) |
| Broker integration tests | `make test-broker`, then `RABBITMQ_TEST_URL=amqp://oj:oj@127.0.0.1:5673/` + the runner/midlayer tests |
| Full stack | `make env && make up` → http://localhost:8080 (rest on 127.0.0.1:8000) |
| End-to-end | `make smoke` (API, verdicts, sandbox isolation), `make e2e` (Playwright vs the stack) |

## Test levels: put each test where it belongs
- **Unit**: Go packages with fakes; midlayer services with fake repositories (`midlayer/tests/unit`);
  webapp pure TS (`src/**/*.spec.ts`).
- **Functional**: gRPC servers over bufconn / an in-process server (dao, rest, midlayer); stores and
  broker code against real Postgres / RabbitMQ (gated on `TEST_DATABASE_URL` / `RABBITMQ_TEST_URL`);
  Svelte components in a real browser (`src/**/*.svelte.spec.ts`).
- **E2E**: the real stack: `scripts/smoke.py` and `webapp/e2e/*.e2e.ts`.

## Hard rules
- Never delete, skip or loosen a test or smoke check to make it pass (the only allowed skips are the
  env-gated Postgres/RabbitMQ tests).
- Never commit secrets. Configuration comes from env vars (see `.env.example`); new secrets also go in
  `SECRETS` in the Makefile.
- Keep `cap_drop: [ALL]`, `read_only` and `no-new-privileges` on every compose service; nothing but
  AMQP may listen on the `jobs` network.
- Keep changes minimal and on-task.
