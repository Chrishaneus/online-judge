#!/usr/bin/env bash
# Install all dev dependencies for Linux / WSL / macOS. No sudo needed.
#   bash scripts/setup.sh      (or: make setup)
#
# Needs: go (any recent version; the right toolchain is downloaded automatically),
# node >= 24 + npm, docker. Installs uv if missing.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

if ! command -v uv >/dev/null; then
  step "Installing uv (Python venv/package manager, no sudo)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

step "proto: buf + protoc-gen-es, grpcio-tools, Go plugins"
make -C proto setup

step "api: virtualenv + Python deps"
uv venv --quiet --allow-existing --python 3.13 api/.venv
uv pip install --quiet --python api/.venv/bin/python -r api/requirements-dev.txt

step "runner: Go modules"
(cd runner && go mod download)

step "webapp: npm deps + Playwright Chromium"
(cd webapp && npm ci --no-audit --no-fund && npx playwright install chromium)

step "Done. Verify with: make check"
