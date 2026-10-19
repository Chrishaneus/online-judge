COMPOSE := docker compose
PROTO_PY := proto/.venv/bin/python
# Throwaway broker for the RabbitMQ integration tests (make test-broker).
TEST_BROKER_URL := amqp://oj:oj@127.0.0.1:5673/

.PHONY: help setup gen check check-proto check-api check-runner check-webapp \
        test-broker env up down logs ps smoke e2e clean

help:
	@grep -E '^## ' Makefile | sed 's/^## //'

## setup: install every toolchain (proto generators, Python venv, npm, Playwright)
setup:
	bash scripts/setup.sh

## gen: lint the .proto files and regenerate code into every service
gen:
	$(PROTO_PY) proto/generate.py

## check: every gate CI runs (generated code, lint, types, unit + functional tests)
check: check-proto check-api check-runner check-webapp
	@echo "all checks passed"

check-proto:
	$(PROTO_PY) proto/generate.py --check

check-runner:
	cd runner && test -z "$$(gofmt -l .)" && go vet ./... && go test ./...

check-api:
	cd api && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest -q

check-webapp:
	cd webapp && npm run lint && npm run check && npm run test:unit && npm run test:component

## test-broker: start a throwaway RabbitMQ on :5673; then run the broker tests with
##              RABBITMQ_TEST_URL=amqp://oj:oj@127.0.0.1:5673/ (runner, api)
test-broker:
	@docker start oj-test-rabbitmq >/dev/null 2>&1 || docker run -d --name oj-test-rabbitmq \
	  -p 127.0.0.1:5673:5672 -e RABBITMQ_DEFAULT_USER=oj -e RABBITMQ_DEFAULT_PASS=oj rabbitmq:4-alpine >/dev/null
	@echo "RABBITMQ_TEST_URL=$(TEST_BROKER_URL)   (stop: docker rm -f oj-test-rabbitmq)"

SECRETS := POSTGRES_PASSWORD RABBITMQ_API_PASSWORD RABBITMQ_RUNNER_PASSWORD ADMIN_TOKEN

## env: create .env, or add keys missing from an older one; every secret still
##      set to "change-me..." gets a random value. Existing values are kept.
env:
	@test -f .env || cp .env.example .env
	@grep -E '^[A-Z_]+=' .env.example | while IFS== read -r key _; do \
	  grep -q "^$$key=" .env || { grep "^$$key=" .env.example >> .env; echo "added $$key"; }; \
	done
	@for key in $(SECRETS); do \
	  if grep -qE "^$$key=change-me" .env; then \
	    sed -i "s/^$$key=.*/$$key=$$(openssl rand -hex 24)/" .env; echo "generated $$key"; \
	  fi; \
	done
	@echo ".env ready (admin token: $$(grep ^ADMIN_TOKEN= .env | cut -d= -f2))"

## up: build and start the whole stack, waiting until healthy (http://localhost:8080)
up:
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

## smoke: end-to-end API + sandbox test against the running stack
smoke:
	python3 scripts/smoke.py

## e2e: Playwright browser flows against the running stack
e2e:
	cd webapp && E2E_BASE_URL=http://localhost:$${WEB_PORT:-8080} \
	  E2E_ADMIN_TOKEN="$$(grep '^ADMIN_TOKEN=' ../.env | cut -d= -f2-)" npx playwright test

## clean: stop and delete all data (database and broker volumes included)
clean:
	$(COMPOSE) down -v
