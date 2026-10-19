# proto

**Single source of truth for every type shared between Online Judge services.**
The `.proto` files in `oj/v1/` define the HTTP API's JSON (shared by api and
webapp) and the RabbitMQ job messages (shared by api and runner). Code is
generated from them into each service directory and committed there.

| File | Contents | Used by |
|---|---|---|
| `oj/v1/types.proto` | Domain types and enums (`Problem`, `Submission`, `Verdict`, `Language`, …), `ErrorResponse` | everyone |
| `oj/v1/judge.proto` | Request/response message of every `/api/v1` route (route written above each request) | api (server), webapp (client) |
| `oj/v1/runner.proto` | `ExecuteJob` / `JobEvent`: RabbitMQ messages + topology | api (publisher, worker consumes events), runner (consumer) |

## Architecture

```
browser ─> webapp (SvelteKit, node :3000)
             │  server-side fetch, canonical proto JSON
             v
           api (Flask :8000)  /api/v1: controllers -> services -> repositories ─> postgres
           worker (same image)  consumes judge.events / judge.jobs.dead ──────────┘
             │  AMQP (binary protobuf)
             v
           RabbitMQ  judge.jobs ─> runner × N
                     judge.events <─┘
```

* **HTTP (webapp ⇄ api): canonical proto JSON.** camelCase fields, enums by
  name (`"LANGUAGE_PYTHON"`), int64 as JSON strings (`bigint` in the generated
  TS; protoc-gen-es v2 ignores `jstype`), Timestamps as RFC 3339, fields with
  default values included. Each route's body is its `*Request` message and its
  response the matching `*Response`; errors are `ErrorResponse` (the status
  codes are listed at the top of `judge.proto`). `GET /api/v1/admin/verify`
  and `GET /healthz` have no messages.
* **Judging: RabbitMQ.** api publishes an `ExecuteJob` per submission to
  `judge.jobs`. Runners consume it, compile once, run every test and publish
  `JobEvent`s (`started`, then `finished`) to `judge.events`. The api worker
  compares outputs, computes the verdict and stores it. Custom runs
  (`POST /api/v1/run`) use the same queue with an RPC reply queue. See the
  header of `oj/v1/runner.proto` for the exact topology, AMQP properties and
  permissions.

## Generated code

| Service | Output (committed, never hand-edit) | Language | Files |
|---|---|---|---|
| api | `app/gen/oj/v1` (imports rewritten to `app.gen.oj.v1`) | Python + `.pyi` | all |
| runner | `internal/gen/oj/v1` (package `ojv1`) | Go | types, runner |
| webapp | `src/lib/gen/oj/v1/*_pb.ts` | TypeScript (protobuf-es v2) | types, judge |

Runtime versions must match the generators:

| Generator (pinned here) | Runtime in the services |
|---|---|
| protoc-gen-go v1.36.12 | `google.golang.org/protobuf` v1.36.x |
| grpcio-tools 1.85.1 (only for its bundled protoc) | `protobuf` 7.x (≥ the gencode version) |
| @bufbuild/protoc-gen-es 2.17.0 | `@bufbuild/protobuf` ^2.17.0 |

## Usage

From the repo root (`make setup` / `make gen` there call into this directory) or from `proto/`:

```bash
make setup     # once: npm ci, .venv with grpcio-tools, protoc-gen-go into .bin/
make gen       # buf lint + format check, then regenerate into every service
make check     # CI gate: fail if any service's generated code is stale
make breaking  # wire-compatibility check against main
```

### Changing the contract

1. Edit `oj/v1/*.proto`. Keep it wire compatible: never renumber or reuse
   field numbers, and never change a field's type. Jobs can sit in RabbitMQ
   across a deploy and runners may run an older version, so add new fields
   and leave old ones in place. Renaming a field changes its JSON name: update
   the webapp in the same commit.
2. `make gen`, then commit the `.proto` change and the regenerated code
   together.
