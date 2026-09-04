#!/usr/bin/env bash
# End-to-end smoke test against a running stack. The checks live in smoke.py
# (standard-library Python); this wrapper keeps `./scripts/smoke.sh` working.
#
#   ./scripts/smoke.sh [-k PATTERN] [-v] [--api URL] [--web URL]
set -euo pipefail
exec python3 "$(dirname "$0")/smoke.py" "$@"
