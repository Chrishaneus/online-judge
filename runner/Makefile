.PHONY: build test test-integration lint run docker

# Shared dev broker for the integration tests (the user needs configure rights).
RABBITMQ_TEST_URL ?= amqp://oj:oj@127.0.0.1:5673/

build:
	go build -o bin/runner ./cmd/runner

test:
	go test ./...

test-integration:
	RABBITMQ_TEST_URL=$(RABBITMQ_TEST_URL) go test -count=1 ./...

lint:
	go vet ./...
	test -z "$$(gofmt -l .)"

run:
	go run ./cmd/runner

docker:
	docker build -t online-judge/runner:latest .
