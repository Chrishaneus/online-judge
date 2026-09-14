.PHONY: build test run docker

build:
	go build -o bin/runner ./cmd/runner

test:
	go test ./...

run:
	go run ./cmd/runner

docker:
	docker build -t oj-runner .
