# proto

**Single source of truth for every type shared between Online Judge services.**
The `.proto` files in `oj/v1/` define the gRPC APIs, the RabbitMQ job messages
and the JSON the webapp sees. Code is generated from them into each service
directory and committed there.

| File | Contents | Used by |
|---|---|---|
| `oj/v1/types.proto` | Domain types and enums (`Problem`, `Submission`, `Verdict`, `Language`, …) | everyone |
| `oj/v1/dao.proto` | `DaoService`: dao's persistence API (gRPC) | dao (server), midlayer (client) |
| `oj/v1/judge.proto` | `JudgeService`: midlayer's business API (gRPC); its HTTP mapping is served by rest | midlayer (server), rest (client), webapp (JSON types) |
| `oj/v1/runner.proto` | `ExecuteJob` / `JobEvent`: RabbitMQ messages + topology | midlayer (publisher), runner (consumer) |

## Architecture

```
browser ─> webapp (SvelteKit, node :3000)
             │  server-side fetch, canonical proto JSON
             v
           rest (Go :8000)  /api/v1, auth, rate limit, CORS
             │  gRPC  oj.v1.JudgeService
             v
           midlayer (Python :50051)  business logic, judging rules
             │  gRPC oj.v1.DaoService          │  AMQP (binary protobuf)
             v                                 v
           dao (Go :50052) ─> postgres    RabbitMQ  judge.jobs ─> runner × N
                                                       judge.events <─┘
```

* **Edge (webapp ⇄ rest): HTTP + canonical proto JSON.** camelCase fields,
  enums by name (`"LANGUAGE_PYTHON"`), int64 as JSON strings (`bigint` in
  the generated TS; protoc-gen-es v2 ignores `jstype`), Timestamps as RFC 3339. Each route's body
  is the RPC request message, its response is the RPC response message, and
  errors are `ErrorResponse`.
* **Inside: gRPC.** `GET /api/v1/admin/verify` is the only route without an RPC: rest
  answers it itself (`{"admin": true}`) to validate the admin token. Every gRPC server also serves the standard
  `grpc.health.v1.Health` service. Docker healthchecks use it.
* **Judging: RabbitMQ.** The midlayer publishes an `ExecuteJob` per
  submission to `judge.jobs`. Runners consume it, compile once, run every test
  and publish `JobEvent`s (`started`, then `finished`) to `judge.events`. The
  midlayer compares outputs, computes the verdict and stores it through dao.
  Custom runs (`RunCode`) use the same queue with an RPC reply queue. See the
  header of `oj/v1/runner.proto` for the exact topology, AMQP properties and
  permissions.

### gRPC status → HTTP (rest)

| gRPC | HTTP |
|---|---|
| `INVALID_ARGUMENT` | 422 (400 when rest itself can't parse the JSON) |
| `NOT_FOUND` | 404 |
| `ALREADY_EXISTS`, `FAILED_PRECONDITION` | 409 |
| `RESOURCE_EXHAUSTED` | 429 |
| `DEADLINE_EXCEEDED` | 504 |
| `UNAVAILABLE` | 503 |
| anything else | 502 (logged; details not leaked) |

## Generated code

| Service | Output (committed, never hand-edit) | Language | Files |
|---|---|---|---|
| dao | `internal/gen/oj/v1` (package `ojv1`) | Go + gRPC | types, dao |
| rest | `internal/gen/oj/v1` | Go + gRPC | types, judge |
| runner | `internal/gen/oj/v1` | Go | types, runner |
| midlayer | `app/gen/oj/v1` (imports rewritten to `app.gen.oj.v1`) | Python + grpc + `.pyi` | all |
| webapp | `src/lib/gen/oj/v1/*_pb.ts` | TypeScript (protobuf-es v2) | types, judge |

Runtime versions must match the generators:

| Generator (pinned here) | Runtime in the services |
|---|---|
| protoc-gen-go v1.36.12, protoc-gen-go-grpc v1.6.2 | `google.golang.org/protobuf` v1.36.x, `google.golang.org/grpc` v1.85.x (Go ≥ 1.26) |
| grpcio-tools 1.85.1 | `grpcio==1.85.1`, `protobuf>=7.35.1,<8` |
| @bufbuild/protoc-gen-es 2.17.0 | `@bufbuild/protobuf` ^2.17.0 |

## Usage

From the repo root (`make setup` / `make gen` there call into this directory) or from `proto/`:

```bash
make setup     # once: npm ci, .venv with grpcio-tools, Go plugins into .bin/
make gen       # buf lint + format check, then regenerate into every service
make check     # CI gate: fail if any service's generated code is stale
make breaking  # wire-compatibility check against main
```

### Changing the contract

1. Edit `oj/v1/*.proto`. Keep it wire compatible: never renumber or reuse
   field numbers, and never change a field's type. Services are deployed
   independently, so add new fields and leave old ones in place.
2. `make gen`, then commit the `.proto` change and the regenerated code
   together.
3. Update the server first, then the clients.
