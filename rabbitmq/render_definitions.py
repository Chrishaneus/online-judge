"""Render RabbitMQ definitions (users, permissions, queues) from env vars.

Runs once before the broker starts (broker-setup service). The topology must
match the header of proto/oj/v1/runner.proto exactly: midlayer re-declares
the same queues and RabbitMQ rejects a declare whose arguments differ.

    MIDLAYER_PASSWORD, RUNNER_PASSWORD  required
    OUT                                 default /defs/definitions.json
"""

import base64
import hashlib
import json
import os
import secrets
import sys


def password_hash(password: str) -> str:
    # rabbit_password_hashing_sha256: base64(salt || sha256(salt || password))
    salt = secrets.token_bytes(4)
    return base64.b64encode(salt + hashlib.sha256(salt + password.encode()).digest()).decode()


def user(name: str, password: str) -> dict:
    return {
        "name": name,
        "password_hash": password_hash(password),
        "hashing_algorithm": "rabbit_password_hashing_sha256",
        "tags": [],
        "limits": {},
    }


def quorum(name: str, **arguments: object) -> dict:
    return {
        "name": name,
        "vhost": "/",
        "durable": True,
        "auto_delete": False,
        "arguments": {"x-queue-type": "quorum", **arguments},
    }


def main() -> None:
    passwords = {k: os.environ.get(k, "") for k in ("MIDLAYER_PASSWORD", "RUNNER_PASSWORD")}
    missing = [k for k, v in passwords.items() if not v]
    if missing:
        sys.exit(f"missing env: {', '.join(missing)}")

    definitions = {
        "vhosts": [{"name": "/"}],
        "users": [
            user("midlayer", passwords["MIDLAYER_PASSWORD"]),
            user("runner", passwords["RUNNER_PASSWORD"]),
        ],
        "permissions": [
            # Declares the judge.* queues (incl. its exclusive judge.rpc.<uuid> reply
            # queue), publishes via the default exchange, consumes events / dead jobs / replies.
            {
                "user": "midlayer",
                "vhost": "/",
                "configure": r"^judge\..*$",
                "write": r"^amq\.default$",
                "read": r"^judge\..*$",
            },
            # Least privilege: consume judge.jobs, publish events via the default exchange.
            {"user": "runner", "vhost": "/", "configure": "^$", "write": r"^amq\.default$", "read": r"^judge\.jobs$"},
        ],
        "queues": [
            quorum(
                "judge.jobs",
                **{
                    "x-delivery-limit": 3,
                    "x-dead-letter-exchange": "",
                    "x-dead-letter-routing-key": "judge.jobs.dead",
                },
            ),
            quorum("judge.jobs.dead"),
            quorum("judge.events"),
        ],
    }
    out = os.environ.get("OUT", "/defs/definitions.json")
    with open(out, "w") as f:
        json.dump(definitions, f, indent=2)
    os.chmod(out, 0o644)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
