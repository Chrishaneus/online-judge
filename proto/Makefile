GO_PLUGINS := google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.12
PY := .venv/bin/python

.PHONY: setup gen check lint breaking

## setup: install the pinned generators (buf + protoc-gen-es, grpcio-tools for protoc, protoc-gen-go)
setup:
	npm ci --no-audit --no-fund
	uv venv --quiet --python 3.13 .venv
	uv pip install --quiet --python $(PY) -r requirements.txt
	GOBIN=$(CURDIR)/.bin go install $(GO_PLUGINS)

## gen: lint, then regenerate code into every service
gen:
	$(PY) generate.py

## check: fail if any service's generated code is stale (CI gate)
check:
	$(PY) generate.py --check

lint:
	npx buf lint && npx buf format --diff --exit-code

## breaking: compare against main (wire compatibility for rolling deploys)
breaking:
	npx buf breaking --against '.git#branch=main'
