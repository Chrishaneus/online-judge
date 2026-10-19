# Online Judge

Submit code in Python, C, C++ or JavaScript and get it judged in a sandbox.
SvelteKit frontend, a Flask API, and Go runners that take judging jobs from
RabbitMQ. One repo, one `docker compose up`.

## Layout

| Path        | Language                      | Role                                                                 |
|-------------|-------------------------------|----------------------------------------------------------------------|
| `proto/`    | Protobuf (buf)                | **Shared contract**: HTTP JSON types and RabbitMQ messages; generates code into every service |
| `api/`      | Python 3.13 / Flask           | `/api/v1`: controllers → services → repositories (Postgres, RabbitMQ); plus the `worker` process that judges runner results |
| `webapp/`   | SvelteKit 3 / Svelte 5 / TS   | Web UI; talks to the api server-side (proto JSON)                    |
| `runner/`   | Go                            | RabbitMQ consumer: sandboxed compile & execute                       |
| `rabbitmq/` | RabbitMQ config               | Users, permissions and queues rendered from `.env` at startup        |
| `scripts/`  | bash / Python                 | `setup.sh` (dev deps), `smoke.py` (end-to-end test)                  |

Every directory has a README; `AGENTS.md` files hold the rules for coding agents.

## Architecture

```
browser ─> webapp (:3000, published :8080)
             │ HTTP, proto JSON
             v
           api (Flask :8000) ─────> postgres
           worker (same image) ─┘
             │ AMQP, binary protobuf
             v
           rabbitmq ── judge.jobs ──> runner × RUNNER_REPLICAS
                    <─ judge.events ──┘
```

A submission is stored as `PENDING` and published to `judge.jobs`, a durable
quorum queue. The first free runner takes it, reports `started` (the
submission becomes `JUDGING`), compiles once, runs every test and publishes
the raw results. The api worker compares outputs and stores the verdict. A
runner acknowledges a job only after its result is confirmed by the broker.
If a runner dies mid-job, the job is redelivered. After 3 failed deliveries
it goes to `judge.jobs.dead` and the submission is marked `FAILED`. Custom runs
(`POST /api/v1/run`) take the same path with an RPC reply queue.

Scale judging with `RUNNER_REPLICAS` (containers) × `RUNNER_WORKERS`
(concurrent jobs per container). `GET /api/v1/status` reports queue depth and
how many runners are consuming.

### Networks

| Network | Members | Notes |
|---|---|---|
| `frontend` | webapp, api | webapp published; api published on loopback only |
| `backend` (internal) | api, worker, rabbitmq | |
| `db` (internal) | api, worker, postgres | |
| `jobs` (internal) | runner, rabbitmq | the only network submitted code can touch |

### Security

* **Runners** execute untrusted code. Their only network is `jobs`, where the
  only listening port is RabbitMQ's AMQP port. Erlang distribution, epmd and
  Prometheus are bound to loopback inside the broker. The runner's broker user
  can only consume `judge.jobs` and publish to the default exchange. The
  runner removes its credentials from its environment before starting
  sandboxed processes, and those processes run as separate UIDs, so they can't
  read the credentials. **Residual risk:** sandboxed code can still open a TCP
  connection to the broker's AMQP port, but it has no credentials to use there.
  The smoke test checks all of this.
* RabbitMQ users and permissions come from `rabbitmq/render_definitions.py`.
  The one-shot `broker-setup` service runs it before the broker boots, and the
  passwords are stored hashed. No `guest` user exists.
* Every container drops all Linux capabilities and uses a read-only root
  filesystem with `no-new-privileges`. RabbitMQ runs as its own user from the
  start. The runner keeps only the six capabilities it needs to switch to
  sandbox UIDs.

## Usage

```bash
make env     # create/upgrade .env with random secrets (keeps existing values)
make up      # build + start everything, wait for healthchecks
make e2e     # Playwright browser flows against the running stack
make smoke   # end-to-end test against the running stack
```

Both suites come from the same address and share the per-client rate limit
(`RATE_LIMIT_PER_MIN`). `smoke` waits out 429s but the browser tests don't, so
run `e2e` first or a minute after `smoke`.

Open http://localhost:8080. Sign in on the **Admin** page with the
`ADMIN_TOKEN` from `.env` to manage problems. Three starter problems are
seeded.

`make logs`, `make ps`, `make down`; `make clean` also deletes the database
and broker volumes.

## Development

```bash
make setup   # proto generators, api venv, runner Go modules, npm + Playwright
make gen     # after editing proto/oj/v1/*.proto: regenerate every service
make check   # every CI gate: generated code, lint, types, unit + functional tests
```

### Smoke test

`scripts/smoke.py` (standard library only; `scripts/smoke.sh` wraps it) checks:
health and runner availability, the catalogue, the error contract
(`ErrorResponse` + status codes), all four languages and every verdict,
concurrent judging across runners, custom runs, sandbox isolation (no
internal services, no internet, no credentials) and the admin lifecycle. It
always deletes the problem it creates, even when a check fails.

```bash
python3 scripts/smoke.py -k sandbox -v        # only sandbox checks, show failing bodies
python3 scripts/smoke.py --api http://host:8000/api/v1 --web http://host:8080
```

### API

The public API is served by the api service and uses canonical proto JSON:
camelCase fields, enums by name, and int64 values as strings. The request and
response messages are in `proto/oj/v1/judge.proto`.

```bash
curl localhost:8000/api/v1/problems
curl -XPOST localhost:8000/api/v1/submissions -H 'Content-Type: application/json' \
  -d '{"problemId":"1","language":"LANGUAGE_PYTHON","source":"a,b=map(int,input().split());print(a+b)","username":"me"}'
curl localhost:8000/api/v1/submissions/1
```
