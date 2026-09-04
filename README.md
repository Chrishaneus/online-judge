# oj-deploy

Docker Compose deployment for the Online Judge.

## Repositories

| Repo          | Language                      | Role                                                                 |
|---------------|-------------------------------|----------------------------------------------------------------------|
| `oj-proto`    | Protobuf (buf)                | **Shared contract**: gRPC APIs, RabbitMQ messages, JSON types; generates code into every repo |
| `oj-webapp`   | SvelteKit 3 / Svelte 5 / TS   | Web UI; talks to oj-rest server-side (proto JSON)                   |
| `oj-rest`     | Go                            | Public REST edge `/api/v1`: proto JSON ⇄ gRPC, auth, rate limits, CORS |
| `oj-midlayer` | Python (grpc.aio, aio-pika)   | Business logic: validation, judging rules and verdicts, job publishing |
| `oj-runner`   | Go                            | RabbitMQ consumer: sandboxed compile & execute (Python, C, C++, JavaScript) |
| `oj-dao`      | Go + PostgreSQL               | Persistence (gRPC); the only service that touches the DB            |
| `oj-deploy`   | Compose                       | This repo: wiring, networks, broker setup, hardening, smoke test    |

Clone them side by side:

```
online-judge/
├── oj-proto/  oj-dao/  oj-runner/  oj-midlayer/  oj-rest/  oj-webapp/
└── oj-deploy/   <- run commands here
```

## Architecture

```
browser ─> webapp (:3000, published :8080)
             │ HTTP, proto JSON
             v
           rest (:8000) ─gRPC─> midlayer (:50051) ─gRPC─> dao (:50052) ─> postgres
                                   │ AMQP, binary protobuf
                                   v
                                rabbitmq ── judge.jobs ──> runner × RUNNER_REPLICAS
                                         <─ judge.events ──┘
```

A submission is stored as `PENDING` and published to `judge.jobs`, a durable
quorum queue. The first free runner takes it, reports `started` (the
submission becomes `JUDGING`), compiles once, runs every test and publishes
the raw results. The midlayer compares outputs and stores the verdict. A
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
| `frontend` | webapp, rest | webapp published; rest published on loopback only |
| `backend` (internal) | rest, midlayer, dao, rabbitmq | |
| `db` (internal) | dao, postgres | |
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
make smoke   # end-to-end test against the running stack
```

Open http://localhost:8080. Sign in on the **Admin** page with the
`ADMIN_TOKEN` from `.env` to manage problems. Three starter problems are
seeded.

`make logs`, `make ps`, `make down`; `make clean` also deletes the database
and broker volumes. `make proto-check` verifies every repo's generated code
matches `../oj-proto`.

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

The public API is served by oj-rest and uses canonical proto JSON:
camelCase fields, enums by name, and int64 values as strings. The request and
response messages are in `../oj-proto/oj/v1/judge.proto`.

```bash
curl localhost:8000/api/v1/problems
curl -XPOST localhost:8000/api/v1/submissions -H 'Content-Type: application/json' \
  -d '{"problemId":"1","language":"LANGUAGE_PYTHON","source":"a,b=map(int,input().split());print(a+b)","username":"me"}'
curl localhost:8000/api/v1/submissions/1
```
