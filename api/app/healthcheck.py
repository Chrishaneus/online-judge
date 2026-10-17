"""Docker HEALTHCHECK of the api: exit 0 iff GET /healthz answers 200 (liveness, no dependencies)."""

import os
import sys
import urllib.request


def check(url: str, timeout_s: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as res:
            return res.status == 200
    except OSError:
        return False


if __name__ == "__main__":
    sys.exit(0 if check(f"http://127.0.0.1:{os.environ.get('PORT', '8000')}/healthz") else 1)
