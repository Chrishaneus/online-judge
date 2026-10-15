# dao

Persistence service for the Online Judge: a gRPC server implementing
`oj.v1.DaoService` (contract: [`proto/oj/v1/dao.proto`](../proto/oj/v1/dao.proto)).

It is the **only** component that talks to PostgreSQL. Only midlayer calls
it; it holds no business rules.

```
webapp -> rest -> midlayer -> dao (gRPC :50052) -> postgres
```

## Configuration

| Variable       | Default   | Description |
|----------------|-----------|-------------|
| `DAO_ADDR`     | `:50052`  | gRPC listen address (also the address `dao healthcheck` dials) |
| `DATABASE_URL` | *(empty)* | PostgreSQL DSN. When empty an in-memory store is used (dev/tests only, nothing is persisted) |

Migrations (schema, seed problems, indexes) are embedded in the binary and run
on startup under an advisory lock, so several replicas can start at once.
Startup waits up to 60 s for the database.

## gRPC API

Service `oj.v1.DaoService` (plaintext gRPC, max message size 64 MiB both ways):

| RPC | Notes |
|-----|-------|
| `ListProblems`, `GetProblem` | ordered by id |
| `CreateProblem` | problem + test cases in one transaction; test case ordinals 1..n in list order. Zero limits default to 2000 ms / 256 MB |
| `UpdateProblem` | replaces slug, title, statement, difficulty, limits |
| `DeleteProblem` | cascades to test cases and submissions |
| `ListTestCases` | ordered by ordinal, optional `samples_only` |
| `CreateTestCase` | appended with ordinal = max + 1 |
| `DeleteTestCase` | |
| `CreateSubmission` | starts `PENDING`; empty username becomes `anonymous` |
| `GetSubmission` | |
| `ListSubmissions` | filters: problem, username, any-of statuses, `updated_before`; `limit` 1..500 (0 = 50), `offset`; newest first, complete rows |
| `UpdateSubmission` | partial update of set fields, `results` replaced when present, `update_time` always bumped; atomic compare-and-set via `expected_statuses` |

Errors:

| Code | When |
|------|------|
| `NOT_FOUND` | entity or referenced parent does not exist |
| `ALREADY_EXISTS` | duplicate problem slug |
| `INVALID_ARGUMENT` | missing id, invalid slug/title, `UNSPECIFIED`/unknown enum where a value is required, bad limit/offset |
| `FAILED_PRECONDITION` | `UpdateSubmission` status not in `expected_statuses` |
| `UNAVAILABLE` | database unreachable |
| `INTERNAL` | anything else (logged; generic message) |

Also served: `grpc.health.v1.Health`. Services `""` and `oj.v1.DaoService`
report `SERVING` only while the database answers pings (checked every 5 s).

Enums are stored as the strings used since v1, so existing data stays valid:
language `python|c|cpp|javascript`, difficulty `easy|medium|hard`, status
`PENDING|JUDGING|FINISHED|FAILED`, verdict `''|AC|WA|TLE|MLE|OLE|RE|CE|IE`.
`submissions.results` keeps the row format
`[{"test":1,"verdict":"AC","time_ms":12,"memory_kb":9000,"sample":true}]`.

## Commands

| What | Command |
|------|---------|
| Run (in-memory store) | `make run` |
| Health check | `dao healthcheck` / `make healthcheck` (exit 0 iff `SERVING`) |
| Tests (memory store) | `make test` |
| Tests incl. PostgreSQL | `TEST_DATABASE_URL=postgres://... make test-pg` (throwaway DB; tables are truncated) |
| CI gate (gofmt, vet, tests) | `make check` |
| Docker image | `make docker` (`online-judge/dao:latest`) |
| Try it | `grpcurl -plaintext -import-path ../proto -proto oj/v1/dao.proto localhost:50052 oj.v1.DaoService/ListProblems` |

Generated code in `internal/gen/oj/v1` comes from proto (`make gen` at the repo root);
never edit it here. See [AGENTS.md](AGENTS.md) for the code layout and rules.

## Docker

The image runs as `nonroot` on distroless, exposes `50052` and has a
`HEALTHCHECK` running `/usr/local/bin/dao healthcheck`.
