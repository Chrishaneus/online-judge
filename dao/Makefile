.PHONY: build test test-pg vet fmt fmt-check check run healthcheck docker

IMAGE ?= online-judge/dao:latest

build:
	go build -o bin/dao ./cmd/dao

test:
	go test ./...

# Also runs the store tests against PostgreSQL. TEST_DATABASE_URL must point
# at a throwaway database: its tables are truncated.
test-pg:
	@test -n "$(TEST_DATABASE_URL)" || { echo "set TEST_DATABASE_URL"; exit 1; }
	go test -count=1 ./...

vet:
	go vet ./...

fmt:
	gofmt -w cmd internal/grpcapi internal/store

fmt-check:
	@test -z "$$(gofmt -l .)" || { echo "gofmt needed:"; gofmt -l .; exit 1; }

# CI gate.
check: fmt-check vet test

run:
	go run ./cmd/dao

healthcheck:
	go run ./cmd/dao healthcheck

docker:
	docker build -t $(IMAGE) .
