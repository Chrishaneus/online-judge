# runner

Code execution worker for the Online Judge. It takes `oj.v1.ExecuteJob`
messages from RabbitMQ, compiles each submission once, runs it against every
test input under resource limits and publishes the raw results (stdout, exit
status, time, memory) as `oj.v1.JobEvent`s. It **does not** know expected
outputs: judging is the api's job.

The runner has no listening port. It scales by adding replicas that consume
the same queue.

## Message flow

The contract (topology, AMQP properties, permissions) is the header of
[`proto/oj/v1/runner.proto`](../proto/oj/v1/runner.proto).

```
api ──────ExecuteJob──> judge.jobs ──> runner (prefetch = RUNNER_WORKERS)
                                          │ 1. JobEvent{started}
                                          │ 2. execute in the sandbox
                                          │ 3. JobEvent{finished: ExecuteResult}  (confirmed)
                                          │ 4. ack the job
api worker <──JobEvent── reply_to (judge.events, or the api's RPC queue)
```

Events go to the default exchange with routing key = the job's `reply_to` and
`correlation_id` = the job's `correlation_id`, with `content_type
application/x-protobuf`, `type oj.v1.JobEvent`, persistent. Publisher confirms
are on, and a job is **acked only after its `finished` event is confirmed**
(at-least-once: a job can be executed twice, never lost).

| Situation | Event | Settlement |
|---|---|---|
| Ran (any per-test outcome) | `finished` `EXECUTE_STATUS_OK` + one `TestRun` per input | ack |
| Compilation failed | `finished` `EXECUTE_STATUS_COMPILATION_ERROR` + `compile_output` | ack |
| Malformed job (unknown language, no source, 0 or >200 tests, ...) | `finished` `EXECUTE_STATUS_REJECTED` + `error` | ack |
| Not an `oj.v1.ExecuteJob` (`type` property), undecodable, or no `reply_to` | none | nack, no requeue → `judge.jobs.dead` |
| Infrastructure error (sandbox could not start, publish not confirmed) | `started` only | nack + requeue; on the 3rd attempt nack without requeue → `judge.jobs.dead` |
| Runner crashes / loses the connection mid-job | `started` only | broker redelivers; `x-delivery-limit=3` dead-letters crash loops |
| Shutdown timeout reached mid-job | `started` only | nack + requeue |

The runner counts attempts itself (from the `x-acquired-count` /
`x-delivery-count` headers) because RabbitMQ 4 quorum queues only count
deliveries returned by a closed channel against `x-delivery-limit`, not
explicit requeues.

Per-test `RunStatus`: `OK`, `TIME_LIMIT_EXCEEDED`, `MEMORY_LIMIT_EXCEEDED`,
`OUTPUT_LIMIT_EXCEEDED`, `RUNTIME_ERROR`. Time and memory limits are clamped to
100..15000 ms and 16..1024 MiB. The stdout+stderr of one `finished` event is
capped at `RUNNER_MAX_EVENT_BYTES` (8 MiB) in total so it fits in one AMQP
message (RabbitMQ's default `max_message_size` is 16 MiB); tests
after the cap keep their metrics, lose their output and are reported as
`OUTPUT_LIMIT_EXCEEDED`.

## Supported languages

| `oj.v1.Language`      | lang id      | Toolchain             |
|-----------------------|--------------|-----------------------|
| `LANGUAGE_PYTHON`     | `python`     | CPython 3             |
| `LANGUAGE_C`          | `c`          | gcc, `-O2 -std=c17`   |
| `LANGUAGE_CPP`        | `cpp`        | g++, `-O2 -std=c++17` |
| `LANGUAGE_JAVASCRIPT` | `javascript` | Node.js               |

`LANGUAGE_UNSPECIFIED` and unknown values are `REJECTED`.

## Lifecycle

* **Startup**: reads `RABBITMQ_URL`, removes it from its environment, then
  connects. If the broker is down or `judge.jobs` does not exist yet, it
  retries with backoff (0.5 s doubling to 30 s). The runner never declares
  queues: the topology comes from the broker definitions (`rabbitmq/render_definitions.py` at the repo root).
* **Connection loss**: in-flight jobs are aborted (they can no longer be
  acked, so the broker redelivers them) and the runner reconnects.
* **SIGTERM**: cancels the consumer (no new jobs), waits up to
  `RUNNER_SHUTDOWN_TIMEOUT_S` for in-flight jobs to finish and be acked, then
  aborts the rest (requeued) and exits 0. Give the container a stop grace
  period longer than that timeout.
* **Health**: while connected and consuming, the runner rewrites
  `RUNNER_HEALTH_FILE` every 5 s. `runner healthcheck` exits 0 iff that file
  is younger than 20 s (used by the Docker `HEALTHCHECK`).

## Sandboxing

Defense in depth, without needing a privileged container:

* **Per-slot unprivileged UIDs**: each worker slot runs code as its own UID
  (`RUNNER_UID_BASE + slot`), with supplementary groups cleared, inside a
  private `0700` work directory.
* **Explicit minimal environment**: sandboxed processes get only `PATH`,
  `HOME`, `TMPDIR`, `LANG` and `PYTHONDONTWRITEBYTECODE`. The sandbox never
  lets a child inherit the runner's environment (a test asserts this).
* **rlimits via `prlimit`**: CPU time, address space, process count (fork
  bombs), file size, open files, no core dumps.
* **Wall-clock timeout** that kills the whole process group, and a sweep that
  kills every remaining process of the slot UID after each execution.
* **Output caps**: stdout is capped (default 1 MiB, the process is killed on
  overflow → `OUTPUT_LIMIT_EXCEEDED`).
* **Container**: capabilities dropped to `CHOWN`, `DAC_OVERRIDE`, `FOWNER`,
  `SETUID`, `SETGID`, `KILL`; `no-new-privileges`; read-only root fs; pids
  limit.

### Credentials and network

The runner holds broker credentials, so they must stay out of reach of
sandboxed code:

* `RABBITMQ_URL` is read once and `os.Unsetenv`ed; sandboxed processes get an
  explicit environment anyway.
* `/proc/<pid>/environ` of the runner and of `tini` (PID 1) still contain the
  original environment, but they belong to root and are unreadable to the
  sandbox UIDs (verified in the container: `PermissionError`).
* No credentials are written to any file. Don't mount secrets into the
  container as files readable by other users.
* The broker user should be least-privilege: read `judge.jobs`, write the
  default exchange, no configure (see below).

**Residual risk.** The runner is on an internal network that contains only
RabbitMQ (no internet, no other services). Sandboxed code *can* open TCP
connections to the broker's AMQP port, but it has no credentials, so all it
can do is attempt logins (rate-limit/monitor failed authentications on the
broker) or try to exploit the broker's pre-auth protocol handling. Everything
else on the network is unreachable.

### Mounts

If you mount `/sandbox` as a tmpfs (recommended), it **must** be mounted with
the `exec` option. Docker mounts tmpfs `noexec` by default, which makes every
compiled C/C++ program fail with `Permission denied`. With a read-only root
fs, `/tmp` must be writable too (the heartbeat file lives there).

When the process is not root (e.g. `go test` on a dev box) UID switching and
the process-count limit are skipped automatically.

## Configuration

| Variable                    | Default                              | Description |
|-----------------------------|--------------------------------------|-------------|
| `RABBITMQ_URL`              | `amqp://guest:guest@localhost:5672/` | Broker URL incl. credentials; removed from the environment at startup |
| `RUNNER_QUEUE`              | `judge.jobs`                         | Queue to consume `ExecuteJob`s from |
| `RUNNER_WORKERS`            | `2`                                  | Concurrent jobs, and the consumer prefetch |
| `RUNNER_ID`                 | hostname                             | Reported in `JobEvent.runner_id` and the connection name |
| `RUNNER_SHUTDOWN_TIMEOUT_S` | `60`                                 | How long SIGTERM waits for in-flight jobs |
| `RUNNER_HEALTH_FILE`        | `/tmp/runner-healthy`                | Heartbeat file checked by `runner healthcheck` |
| `RUNNER_SANDBOX_DIR`        | `$TMPDIR/oj-sandbox`                 | Where per-run work dirs are created (`/sandbox` in the image) |
| `RUNNER_UID_BASE`           | `20000`                              | First sandbox UID |
| `RUNNER_MAX_OUTPUT_BYTES`   | `1048576`                            | Stdout cap per test |
| `RUNNER_MAX_EVENT_BYTES`    | `8388608`                            | Total stdout+stderr in one `finished` event; keep below the broker's `max_message_size` |
| `RUNNER_DISABLE_SETUID`     | unset                                | `1` keeps sandboxed code on the runner's UID (dev only) |

Broker permissions for the runner's user (vhost `/`): configure `^$`, write
`^amq\.default$` (RabbitMQ's permission name for the default exchange, through
which events are routed to the `reply_to` queue), read `^judge\.jobs$`.

## Development

```bash
make test               # unit tests (sandbox/executor tests need prlimit, python3, g++)
make test-integration   # + broker tests against RABBITMQ_TEST_URL (default amqp://oj:oj@127.0.0.1:5673/)
make lint               # go vet + gofmt
make docker             # online-judge/runner:latest
```

The integration tests declare their own uniquely named queues with the
arguments from `runner.proto`, so they need a broker user with configure
permission, and they are skipped when `RABBITMQ_TEST_URL` is unset.

Generated protobuf code lives in `internal/gen/oj/v1` and comes from
proto (`make gen` at the repo root). Never edit it by hand.
