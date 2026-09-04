# AGENTS.md

Instructions for AI coding agents working in oj-deploy (Docker Compose wiring
for the Online Judge). Architecture and the shared contract are described in
`../oj-proto/README.md`; each service repo has its own AGENTS.md.

## Rules
- The broker topology in `rabbitmq/render_definitions.py` must match the header
  of `../oj-proto/oj/v1/runner.proto` exactly (oj-midlayer re-declares the same
  queues; mismatched arguments make RabbitMQ refuse the declare).
- Never weaken isolation: the runner stays only on the internal `jobs` network,
  with least-privilege broker credentials; nothing but AMQP may listen on `jobs`.
  Keep `cap_drop: [ALL]`, `read_only`, `no-new-privileges` on every service.
- Never commit `.env` or secrets. New settings go in `.env.example`; new secrets
  also in `SECRETS` in the Makefile.
- Never delete, skip or loosen a smoke check to make it pass.

## Commands
| What | Command |
|---|---|
| Start / rebuild | `make env && make up` |
| End-to-end test | `make smoke` (`python3 scripts/smoke.py -k NAME -v`) |
| Generated code in sync | `make proto-check` |
| Lint scripts | `uvx ruff check . && uvx ruff format --check .` |
| Validate compose | `docker compose config -q` |
