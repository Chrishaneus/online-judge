# AGENTS.md

Instructions for any AI coding agent working in `dao/` (the Online
Judge persistence service). The architecture of the whole system is described
in `../proto/README.md`.

## Layout

| Path | What |
|---|---|
| `cmd/dao/` | Entrypoint: env config, store selection, gRPC server, graceful shutdown, `dao healthcheck` subcommand |
| `internal/grpcapi/` | `oj.v1.DaoService` implementation: validation, proto <-> store conversion (`convert.go`), error -> gRPC code mapping (`errors.go`), interceptors and server options (`grpc.go`), DB-driven health (`health.go`) |
| `internal/store/` | Domain models, `Store` interface, `Memory` and `Postgres` implementations, embedded SQL migrations (`migrations/NNN_*.sql`) |
| `internal/gen/oj/v1/` | **Generated** Go code from `../proto` (package `ojv1`). Never hand-edit |

## Architecture rules (reviewers enforce these)

- **`internal/store` is the only database access.** No SQL or pgx anywhere else.
  Every behaviour must exist in both `Memory` and `Postgres` with the same
  semantics; the shared tests in `store_test.go` run against both.
- **`internal/grpcapi` translates only**: validate the request, convert to
  store types, make the store call(s), convert the result, map errors. No SQL,
  no business rules (those belong to midlayer).
- Enum <-> DB string mapping lives only in `internal/grpcapi/convert.go`. The
  stored strings and the `results` JSONB row format are part of the schema
  and must not change.
- Store errors are the sentinels in `store.go` (`ErrNotFound`, `ErrConflict`,
  `ErrPrecondition`, `ErrUnavailable`); `grpcapi/errors.go` maps them to the
  codes listed in the header of `dao.proto`. Unexpected errors are logged and
  returned as a generic `INTERNAL`.
- Schema changes: add a new `internal/store/migrations/NNN_*.sql`; never edit
  an applied migration. Existing deployments hold data.
- The contract is `../proto/oj/v1/dao.proto`. To change it, edit it there,
  run `make gen` at the repo root (it regenerates `internal/gen` here) and
  commit both in one commit. Never edit `internal/gen` by hand.

## Commands

| What | Command |
|---|---|
| CI gate (gofmt, vet, tests) | `make check` |
| Unit + functional tests | `go test ./...` |
| Store tests against Postgres | `TEST_DATABASE_URL=postgres://user:pw@host:port/db make test-pg` (throwaway DB, truncated) |
| Run locally (memory store) | `make run` (listens on `:50052`) |
| Health | `go run ./cmd/dao healthcheck` |
| Image | `make docker` |
| Regenerate gRPC code | `make gen` (repo root) |

Go 1.27 (`GOTOOLCHAIN=auto` downloads it when the local `go` is older).

## Test levels

- **Unit**: `internal/grpcapi/convert_test.go` (enum round trips, model
  conversion, validation), `grpc_test.go` (error codes, interceptors,
  health), `cmd/dao/main_test.go`.
- **Store contract**: `internal/store/store_test.go` runs against the memory
  store and, when `TEST_DATABASE_URL` is set, PostgreSQL;
  `postgres_test.go` covers Postgres-only behaviour (transactions, JSONB
  format).
- **Functional**: `internal/grpcapi/server_test.go` drives the real gRPC
  server over `bufconn` against the memory store.

## Hard rules

- Never delete, skip or loosen a test to make it pass. The only allowed skip
  is the Postgres suite when `TEST_DATABASE_URL` is unset.
- `gofmt -l .` must be empty and `go vet ./...` clean.
- Never commit secrets; configuration comes from env vars (`DAO_ADDR`,
  `DATABASE_URL`).
- Keep changes minimal and on-task.
