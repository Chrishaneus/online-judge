# AGENTS.md

Instructions for any AI coding agent working in this repo (oj-rest, the
public REST gateway of the Online Judge).

## Layout

| Path | What |
|---|---|
| `cmd/rest/main.go` | Entrypoint: env config, gRPC client to oj-midlayer, HTTP server, `rest healthcheck` |
| `internal/gateway/gateway.go` | `Config`, `New`, the route table (one line per RPC) |
| `internal/gateway/rpc.go` | Generic `rpc` handler (JSON ⇄ proto, deadline, metadata), gRPC → HTTP error mapping, path/query binding |
| `internal/gateway/middleware.go`, `ratelimit.go` | Request id, logging, recovery, CORS, admin auth, rate limit, body limit |
| `internal/gen/oj/v1/` | **Generated** from `../oj-proto` (package `ojv1`). Never edit. |

## Architecture rules (reviewers enforce these)

- **oj-rest is translation + cross-cutting concerns only.** A route parses
  HTTP into the RPC request message, makes **one** `JudgeService` call and
  writes the response message. No business logic, no validation of field
  *content* (lengths, enum values, limits): that is oj-midlayer's job and it
  answers `INVALID_ARGUMENT`. oj-rest only rejects what it cannot parse (bad
  JSON, unknown fields, non-numeric ids) with 400.
- No other upstreams: oj-rest talks only to oj-midlayer over gRPC. Never
  forward `Authorization` or cookies; forward `x-request-id` metadata.
- Wire format is canonical proto JSON (`protojson`, `EmitUnpopulated`).
  Never hand-write JSON structs for API types. Every error body is
  `ojv1.ErrorResponse` via `writeError`.
- gRPC → HTTP status mapping follows the table in `../oj-proto/README.md`.
  Only client-facing codes pass the midlayer's message through; others are
  logged and answered with a generic message.
- To change a request/response shape or add an RPC: edit
  `../oj-proto/oj/v1/*.proto`, run `make gen` in oj-proto, commit there and
  the regenerated `internal/gen` here, then add the route line in
  `gateway.go` and a test case.
- Standard library plus `google.golang.org/grpc` and
  `google.golang.org/protobuf` only.

## Commands

| What | Command |
|---|---|
| All gates (gofmt, vet, tests) | `make check` |
| Tests | `go test ./...` |
| Run locally | `MIDLAYER_ADDR=localhost:50051 ADMIN_TOKEN=dev-token-0123456789 make run` |
| Image | `docker build -t online-judge/rest:latest .` |
| Regenerate code | `make gen` in `../oj-proto` |

## Tests

- Handler tests run the real gateway against a fake `JudgeServiceServer`
  over `bufconn` (`gateway_test.go`): add a row to the route table test for
  every new route, and cover status mapping and JSON shape.
- Middleware and rate limiter have their own unit tests.

## Hard rules

- Never delete, skip or loosen a test to make it pass.
- Never commit secrets; configuration comes from env vars (see README).
- Keep changes minimal and on-task; Go 1.27, `gofmt` clean.
