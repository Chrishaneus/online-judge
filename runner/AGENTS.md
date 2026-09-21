# AGENTS.md

Instructions for any AI coding agent (Claude Code, Codex, Cursor, Gemini, Aider, Copilot…) working in this repo.

oj-runner executes untrusted code. It consumes `oj.v1.ExecuteJob` from
RabbitMQ and publishes `oj.v1.JobEvent`s. See README.md for the flow and
the security model.

## Layout

| Path | What |
|---|---|
| `cmd/runner/` | Entrypoint: env config, `RABBITMQ_URL` unset, `runner healthcheck` |
| `internal/consumer/` | RabbitMQ: connection/reconnect/shutdown loop (`consumer.go`), per-delivery logic (`handler.go`), proto ↔ executor mapping (`mapping.go`), heartbeat (`health.go`) |
| `internal/executor/` | Validates a request, compiles once, runs every test on a pool of slots with per-slot UIDs |
| `internal/sandbox/` | Runs one untrusted process: rlimits (prlimit), wall timeout, output caps, UID drop, explicit env |
| `internal/lang/` | Language registry (compile/run commands) |
| `internal/gen/oj/v1/` | **Generated** protobuf code (package `ojv1`) |

## Rules (reviewers enforce these)

### Sandbox
- **Never weaken the sandbox**: don't remove or loosen rlimits, timeouts, output caps, the UID drop, the cleared supplementary groups or the per-UID kill sweep.
- Sandboxed processes always get an explicit environment. Never let `exec.Cmd.Env` be nil for anything that runs as a sandbox UID, and never pass the runner's own environment.
- Never write credentials to files, and never log `RABBITMQ_URL` (dial errors go through `redact`).

### Consumer
- **Ack a job only after its `finished` event is confirmed** by the broker (publisher confirms). Anything else loses results.
- Settle every delivery exactly once: bad message → `Nack(requeue=false)`; job problem → `finished` with `REJECTED`/`COMPILATION_ERROR` + ack; infrastructure error → requeue (dead-letter on the last attempt).
- Don't declare queues or exchanges: the runner's broker user has no configure permission; topology comes from oj-deploy.
- AMQP access goes through the small interfaces in `handler.go` (`Executor`, `Publisher`, `amqp.Acknowledger`) so the logic stays unit-testable with fakes.

### Contract
- The contract is `oj-proto/oj/v1/runner.proto` (its header defines topology, properties and ack semantics). To change it, edit oj-proto and run `make gen` there; it regenerates `internal/gen/`.
- **Never hand-edit `internal/gen/`.**

## Commands

| What | Command |
|---|---|
| Unit tests | `make test` (`go test ./...`; sandbox tests need `prlimit`, `python3`, `g++`) |
| + broker integration tests | `make test-integration` (uses `RABBITMQ_TEST_URL`, default `amqp://oj:oj@127.0.0.1:5673/`) |
| Lint | `make lint` (`go vet ./...`, `gofmt -l .` must be empty) |
| Image | `make docker` → `online-judge/runner:latest` |

## Tests
- Consumer logic: unit tests with fakes (`handler_test.go`). Broker behaviour: `integration_test.go`, skipped only when `RABBITMQ_TEST_URL` is unset. Integration tests declare uniquely named queues (the test broker is shared).
- Sandbox guarantees (limits, env isolation) are tested in `internal/sandbox` and `internal/executor`.

## Hard rules
- Never delete, skip or loosen a test to make it pass.
- Never commit secrets. Configuration comes from env vars (see README.md).
- Keep changes minimal and on-task.
