.PHONY: build test run docker

build:
	go build -o bin/dao ./cmd/dao

test:
	go test ./...

run:
	go run ./cmd/dao

docker:
	docker build -t oj-dao .
