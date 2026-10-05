.PHONY: build test check run docker

build:
	go build -o bin/rest ./cmd/rest

test:
	go test ./...

# CI gate: formatting, vet and tests.
check:
	@test -z "$$(gofmt -l .)" || (gofmt -l . && echo "run gofmt -w ." && exit 1)
	go vet ./...
	go test ./...

run:
	go run ./cmd/rest

docker:
	docker build -t online-judge/rest:latest .
