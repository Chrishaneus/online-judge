.PHONY: build test run docker

build:
	go build -o bin/rest ./cmd/rest

test:
	go test ./...

run:
	go run ./cmd/rest

docker:
	docker build -t online-judge/rest:latest .
