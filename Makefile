COMPOSE := docker compose

.PHONY: env up down logs ps smoke proto-check clean

SECRETS := POSTGRES_PASSWORD RABBITMQ_MIDLAYER_PASSWORD RABBITMQ_RUNNER_PASSWORD ADMIN_TOKEN

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

## up: build and start the whole stack, waiting until healthy
up:
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

## smoke: end-to-end test against the running stack
smoke:
	python3 scripts/smoke.py

## proto-check: fail if any service's generated code is stale vs ../oj-proto
proto-check:
	$(MAKE) -C ../oj-proto check

## clean: stop and delete all data (database and broker volumes included)
clean:
	$(COMPOSE) down -v
