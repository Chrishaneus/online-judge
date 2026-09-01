COMPOSE := docker compose

.PHONY: env up down logs ps smoke clean

## env: create .env with random secrets (won't overwrite an existing one)
env:
	@test -f .env && echo ".env already exists" || { \
	  cp .env.example .env; \
	  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$$(openssl rand -hex 16)/" .env; \
	  sed -i "s/^ADMIN_TOKEN=.*/ADMIN_TOKEN=$$(openssl rand -hex 24)/" .env; \
	  echo "wrote .env (admin token: $$(grep ^ADMIN_TOKEN .env | cut -d= -f2))"; }

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
	./scripts/smoke.sh

## clean: stop and delete all data (database volume included)
clean:
	$(COMPOSE) down -v
