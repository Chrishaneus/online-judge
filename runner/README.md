# oj-runner

Code execution service for the Online Judge. It compiles a submission once,
then runs it against a batch of inputs under resource limits and reports raw
results (stdout, exit status, time, memory). It **does not** know expected
outputs: judging is the midlayer's job.

## Supported languages

| id           | Toolchain                 |
|--------------|---------------------------|
| `python`     | CPython 3                 |
| `c`          | gcc, `-O2 -std=c17`       |
| `cpp`        | g++, `-O2 -std=c++17`     |
| `javascript` | Node.js                   |

## API

### `POST /execute`

```json
{
  "language": "python",
  "source": "print(sum(map(int, input().split())))",
  "tests": [{ "id": "1", "stdin": "1 2\n" }],
  "time_limit_ms": 1000,
  "memory_limit_mb": 128
}
```

Response:

```json
{
  "status": "OK",
  "compile_output": "",
  "results": [
    { "id": "1", "status": "OK", "stdout": "3\n", "stderr": "", "exit_code": 0, "time_ms": 14, "memory_kb": 9120 }
  ]
}
```

`status` is `OK` or `CE` (compilation error). Per-test `status` is one of
`OK`, `TLE`, `MLE`, `OLE` (output limit), `RE`.

Also: `GET /languages`, `GET /healthz`.

## Sandboxing

Defense in depth, without needing a privileged container:

* **No network** – in the compose deployment the container runs with
  `network_mode: none` and serves its API on a **Unix socket** in a shared
  volume (`RUNNER_ADDR=unix:///run/oj-runner/runner.sock`). The socket is
  only accessible to the configured group, not to sandboxed processes.
* **Per-slot unprivileged UIDs** – each worker slot runs code as its own UID
  (`RUNNER_UID_BASE + slot`), with supplementary groups cleared, inside a
  private `0700` work directory.
* **rlimits via `prlimit`** – CPU time, address space, process count (fork
  bombs), file size, open files, no core dumps.
* **Wall-clock timeout** that kills the whole process group, and a sweep that
  kills every remaining process of the slot UID after each execution.
* **Output caps** – stdout is capped (default 1 MiB, process is killed on
  overflow → `OLE`).
* Container capabilities are dropped to the minimum (`CHOWN`, `DAC_OVERRIDE`,
  `FOWNER`, `SETUID`, `SETGID`, `KILL`) in the compose file.

If you mount `/sandbox` as a tmpfs (recommended), it **must** be mounted with
the `exec` option. Docker mounts tmpfs `noexec` by default, which makes
every compiled C/C++ program fail with `Permission denied`.

When the process is not root (e.g. `go test` on a dev box) UID switching and
the process-count limit are skipped automatically.

## Configuration

| Variable             | Default                 | Description                                |
|----------------------|-------------------------|--------------------------------------------|
| `RUNNER_ADDR`        | `:8002`                 | `host:port` or `unix:///path/to.sock`      |
| `RUNNER_WORKERS`     | `2`                     | Concurrent executions                      |
| `RUNNER_SANDBOX_DIR` | `$TMPDIR/oj-sandbox`    | Where per-run work dirs are created        |
| `RUNNER_UID_BASE`    | `20000`                 | First sandbox UID                          |
| `RUNNER_SOCKET_GID`  | `-1`                    | Group allowed to use the Unix socket       |

`runner healthcheck` probes the configured address (used by Docker `HEALTHCHECK`).
