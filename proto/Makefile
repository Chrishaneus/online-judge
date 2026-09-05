GO_PLUGINS := google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.12 \
              google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.6.2
PY := .venv/bin/python

.PHONY: setup gen check lint breaking

## setup: install the pinned generators (buf + protoc-gen-es, grpcio-tools, Go plugins)
setup:
	npm ci --no-audit --no-fund
	uv venv --quiet --python 3.13 .venv
	uv pip install --quiet --python $(PY) -r requirements.txt
	GOBIN=$(CURDIR)/.bin go install $(GO_PLUGINS)

## gen: lint, then regenerate code into every sibling repo
gen:
	$(PY) generate.py

## check: fail if any sibling's generated code is stale (CI gate)
check:
	$(PY) generate.py --check

lint:
	npx buf lint && npx buf format --diff --exit-code

## breaking: compare against main (wire compatibility for rolling deploys)
breaking:
	npx buf breaking --against '.git#branch=main'
