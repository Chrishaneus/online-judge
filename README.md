# oj-deploy

Docker Compose deployment for the Online Judge.

## Repositories

| Repo          | Language        | Role                                                        |
|---------------|-----------------|-------------------------------------------------------------|
| `oj-webapp`   | HTML/CSS/JS     | Web UI, served by nginx; proxies `/api/`                    |
| `oj-rest`     | Go              | Public REST API: routing allowlist, auth, rate limits, CORS |
| `oj-midlayer` | Python/FastAPI  | Business logic: judging queue, verdicts, data shaping       |
| `oj-runner`   | Go              | Sandboxed compile & execute (Python, C, C++, JavaScript)    |
| `oj-dao`      | Go + PostgreSQL | Repository layer: the only service that touches the DB      |
| `oj-deploy`   | Compose         | This repo: wiring, networks, hardening, smoke test          |

Clone them side by side:

```
online-judge/
├── oj-dao/  oj-runner/  oj-midlayer/  oj-rest/  oj-webapp/
└── oj-deploy/   <- run commands here
```

## Architecture

```
browser ──> webapp (nginx :8080) ──> rest (:8000) ──> midlayer (:8003) ──> dao (:8001) ──> postgres
                                                           │
                                                           └── unix socket ──> runner  (network_mode: none)
```

Networks:

* `frontend`: webapp, rest (webapp port published)
* `backend` (internal, no internet): rest, midlayer, dao
* `db` (internal): dao, postgres
* runner has **no network**. The midlayer reaches it through a unix socket
  on a shared volume, so submitted code cannot reach the DAO, the database,
  or the internet.

All containers drop every Linux capability (the runner keeps only the
six it needs to switch to sandbox users), use read-only root filesystems
and `no-new-privileges`.

## Usage

```bash
make env     # generate .env with random POSTGRES_PASSWORD and ADMIN_TOKEN
make up      # build + start everything, wait for healthchecks
make smoke   # end-to-end test: submits real code and checks verdicts
```

Open http://localhost:8080. Use the **Admin** page with the `ADMIN_TOKEN`
from `.env` to add problems. Three starter problems are seeded.

API examples:

```bash
curl localhost:8080/api/v1/problems
curl -XPOST localhost:8080/api/v1/submissions -H 'Content-Type: application/json' \
  -d '{"problem_id":1,"language":"python","source":"a,b=map(int,input().split());print(a+b)","username":"me"}'
curl localhost:8080/api/v1/submissions/1
```

`make logs`, `make ps`, `make down`; `make clean` also deletes the database.
