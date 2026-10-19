#!/usr/bin/env python3
"""End-to-end smoke test against a running Online Judge stack.

Talks to the api service (canonical proto JSON, see proto/) and checks
the webapp is serving. Standard library only.

    make smoke
    python3 scripts/smoke.py [--api URL] [--web URL] [--admin-token T] [-k PATTERN] [-v]

Defaults come from ./.env (API_PORT, WEB_PORT, ADMIN_TOKEN) when present.
Exit status is 0 only when every check passed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------- configuration ----------


def read_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and not line.lstrip().startswith("#"):
                env[key.strip()] = value.strip()
    return env


def host_url(published: str, default_port: str) -> str:
    """Turn a compose port spec ("8080" or "127.0.0.1:8000") into a base URL."""
    host, _, port = published.rpartition(":")
    return f"http://{host or 'localhost'}:{port or default_port}"


@dataclass(frozen=True)
class Config:
    api: str
    web: str
    admin_token: str
    pattern: str
    verbose: bool
    timeout: float


def parse_args() -> Config:
    dotenv = read_dotenv(Path(__file__).resolve().parent.parent / ".env")

    def setting(key: str, default: str = "") -> str:
        return os.environ.get(key) or dotenv.get(key) or default

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", default=setting("API_URL", host_url(setting("API_PORT", "8000"), "8000") + "/api/v1"))
    p.add_argument("--web", default=setting("WEB_URL", host_url(setting("WEB_PORT", "8080"), "8080")))
    p.add_argument("--admin-token", default=setting("ADMIN_TOKEN"))
    p.add_argument("-k", dest="pattern", default="", help="only run checks whose name contains this")
    p.add_argument("-v", "--verbose", action="store_true", help="print response bodies of failed checks")
    p.add_argument("--timeout", type=float, default=90, help="seconds to wait for a verdict")
    a = p.parse_args()
    return Config(a.api.rstrip("/"), a.web.rstrip("/"), a.admin_token, a.pattern, a.verbose, a.timeout)


# ---------- HTTP ----------


@dataclass
class Response:
    status: int
    body: Any  # parsed JSON, or text when not JSON
    headers: dict[str, str] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return self.body[key]


class CheckFailed(AssertionError):
    def __init__(self, message: str, response: Response | None = None):
        super().__init__(message)
        self.response = response


class Client:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def request(
        self,
        method: str,
        url: str,
        body: Any = None,
        *,
        token: str | None = None,
        expect: int | tuple[int, ...] | None = 200,
    ) -> Response:
        """Send a request, waiting out 429s (honouring Retry-After) for up to a minute."""
        data = None if body is None else json.dumps(body).encode()
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        deadline = time.monotonic() + 60
        while True:
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    resp = Response(r.status, r.read(), dict(r.headers))
            except urllib.error.HTTPError as e:
                resp = Response(e.code, e.read(), dict(e.headers))
            except urllib.error.URLError as e:
                raise CheckFailed(f"{method} {url}: {e.reason}") from e
            if resp.status != 429 or time.monotonic() > deadline:
                break
            time.sleep(float(resp.headers.get("Retry-After") or 1))
        text = resp.body.decode(errors="replace")
        try:
            resp.body = json.loads(text) if text else None
        except ValueError:
            resp.body = text
        allowed = (expect,) if isinstance(expect, int) else expect
        if allowed and resp.status not in allowed:
            raise CheckFailed(f"{method} {url} -> HTTP {resp.status}, expected {allowed}", resp)
        return resp

    def get(self, path: str, **kw: Any) -> Response:
        return self.request("GET", self.cfg.api + path, **kw)

    def post(self, path: str, body: Any, **kw: Any) -> Response:
        return self.request("POST", self.cfg.api + path, body, **kw)

    def delete(self, path: str, **kw: Any) -> Response:
        return self.request("DELETE", self.cfg.api + path, **kw)


# ---------- judge helpers ----------

VERDICT_CODES = {
    "VERDICT_ACCEPTED": "AC",
    "VERDICT_WRONG_ANSWER": "WA",
    "VERDICT_TIME_LIMIT_EXCEEDED": "TLE",
    "VERDICT_MEMORY_LIMIT_EXCEEDED": "MLE",
    "VERDICT_OUTPUT_LIMIT_EXCEEDED": "OLE",
    "VERDICT_RUNTIME_ERROR": "RE",
    "VERDICT_COMPILATION_ERROR": "CE",
    "VERDICT_INTERNAL_ERROR": "IE",
}
DONE = {"SUBMISSION_STATUS_FINISHED", "SUBMISSION_STATUS_FAILED"}


class Judge:
    def __init__(self, client: Client, timeout: float):
        self.c = client
        self.timeout = timeout

    def submit(self, problem_id: str, language: str, source: str) -> dict:
        """Submit and poll until judged; return the final submission."""
        body = {
            "problemId": problem_id,
            "language": f"LANGUAGE_{language.upper()}",
            "source": source,
            "username": "smoke",
        }
        sid = self.c.post("/submissions", body, expect=202)["submission"]["id"]
        deadline, delay = time.monotonic() + self.timeout, 0.2
        while time.monotonic() < deadline:
            sub = self.c.get(f"/submissions/{sid}")["submission"]
            if sub["status"] in DONE:
                return sub
            time.sleep(delay)
            delay = min(delay * 1.5, 1.0)
        raise CheckFailed(f"submission {sid} not judged within {self.timeout:.0f}s (last status {sub['status']})")

    def expect(self, problem_id: str, language: str, verdict: str, source: str) -> str:
        sub = self.submit(problem_id, language, source)
        got = VERDICT_CODES.get(sub["verdict"], sub["verdict"])
        summary = f"{got} {sub['passed']}/{sub['total']} in {sub['timeMs']}ms"
        if got != verdict:
            raise CheckFailed(f"expected {verdict}, got {summary}: {sub.get('message', '')[:200]}")
        return summary

    def run(self, language: str, source: str, stdin: str = "") -> dict:
        body = {"language": f"LANGUAGE_{language.upper()}", "source": source, "stdin": stdin}
        return self.c.post("/run", body).body


# ---------- runner ----------


class Suite:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.passed = self.failed = self.skipped = 0

    def section(self, title: str) -> None:
        print(f"\n\033[1m== {title}\033[0m")

    def check(self, name: str, fn: Callable[[], str | None]) -> None:
        """Run fn; it raises on failure and may return a short detail string."""
        if self.cfg.pattern and self.cfg.pattern not in name:
            return
        start = time.monotonic()
        try:
            detail = fn()
        except Exception as e:  # noqa: BLE001 - every failure is reported, the suite goes on
            self.failed += 1
            print(f"  \033[31m✗\033[0m {name}: {e}")
            resp = getattr(e, "response", None)
            if self.cfg.verbose and resp is not None:
                print(f"      HTTP {resp.status}: {json.dumps(resp.body)[:2000]}")
            elif self.cfg.verbose and not isinstance(e, CheckFailed):
                traceback.print_exc()
            return
        self.passed += 1
        ms = (time.monotonic() - start) * 1000
        print(f"  \033[32m✓\033[0m {name}{f': {detail}' if detail else ''} \033[2m({ms:.0f}ms)\033[0m")

    def skip(self, name: str, reason: str) -> None:
        self.skipped += 1
        print(f"  - {name}: skipped ({reason})")


def ensure(condition: bool, message: str, response: Response | None = None) -> None:
    if not condition:
        raise CheckFailed(message, response)


# ---------- checks ----------

APB_PY = "a, b = map(int, input().split())\nprint(a + b)\n"


def main() -> int:
    cfg = parse_args()
    client, suite = Client(cfg), Suite(cfg)
    judge = Judge(client, cfg.timeout)
    print(f"api {cfg.api}\nweb {cfg.web}")
    problems: dict[str, str] = {}

    # --- health
    suite.section("health")

    def webapp_serves() -> str:
        r = client.request("GET", cfg.web + "/")
        ensure(isinstance(r.body, str) and "<html" in r.body.lower(), "home page is not HTML", r)
        return f"HTTP {r.status}"

    def status_healthy() -> str:
        s = client.get("/status").body
        ensure(s["healthy"] is True, f"unhealthy: {s}")
        ensure(s["runners"] >= 1, f"no runner is consuming judge.jobs: {s}")
        return f"database={s['database']} broker={s['broker']} runners={s['runners']} queue={s['queueDepth']}"

    suite.check("webapp serves the home page", webapp_serves)
    suite.check("all dependencies healthy, runners consuming", status_healthy)

    # --- catalogue
    suite.section("catalogue")

    def languages() -> str:
        got = sorted(lang["language"] for lang in client.get("/languages")["languages"])
        want = ["LANGUAGE_C", "LANGUAGE_CPP", "LANGUAGE_JAVASCRIPT", "LANGUAGE_PYTHON"]
        ensure(got == want, f"languages: {got}")
        return ", ".join(g.removeprefix("LANGUAGE_").lower() for g in got)

    def seeded() -> str:
        problems.update({p["slug"]: p["id"] for p in client.get("/problems")["problems"]})
        missing = {"a-plus-b", "reverse-string", "fibonacci"} - problems.keys()
        ensure(not missing, f"missing seeded problems: {missing}")
        return f"{len(problems)} problems"

    def samples_only() -> str:
        r = client.get(f"/problems/{problems['a-plus-b']}")
        p = r["problem"]
        ensure(len(p["samples"]) == 2, f"expected 2 samples, got {len(p['samples'])}", r)
        ensure("expectedOutput" not in json.dumps(r.body), "hidden test data leaked", r)
        return "2 samples, hidden tests not exposed"

    suite.check("languages", languages)
    suite.check("seeded problems", seeded)
    if "a-plus-b" not in problems:
        print("\ncannot continue without the seeded problems")
        return summary(suite)
    suite.check("problem exposes only samples", samples_only)

    # --- API contract: errors are oj.v1.ErrorResponse with the right status
    suite.section("errors")

    def error_case(method: str, path: str, body: Any, status: int) -> Callable[[], str]:
        def fn() -> str:
            r = client.request(method, cfg.api + path, body, expect=status)
            ensure(isinstance(r.body, dict) and r.body.get("error"), "body is not an ErrorResponse", r)
            return f"{status} {r.body['error'][:60]}"

        return fn

    apb = problems["a-plus-b"]
    suite.check("unknown problem -> 404", error_case("GET", "/problems/999999999", None, 404))
    suite.check("non-numeric id -> 400", error_case("GET", "/problems/abc", None, 400))
    suite.check("unknown JSON field -> 400", error_case("POST", "/run", {"bogus": 1}, 400))
    suite.check(
        "invalid username -> 422",
        error_case(
            "POST",
            "/submissions",
            {"problemId": apb, "language": "LANGUAGE_PYTHON", "source": "x", "username": "a b"},
            422,
        ),
    )
    suite.check(
        "unsupported language -> 422",
        error_case("POST", "/run", {"language": "LANGUAGE_UNSPECIFIED", "source": "x"}, 422),
    )

    # --- judging
    suite.section("judging (all four languages)")
    cases = [
        ("python AC", apb, "python", "AC", APB_PY),
        ("python WA", apb, "python", "WA", "a, b = map(int, input().split())\nprint(a - b)\n"),
        (
            "c AC",
            apb,
            "c",
            "AC",
            '#include <stdio.h>\nint main(void){ long long a,b; scanf("%lld %lld",&a,&b); printf("%lld\\n",a+b); return 0; }\n',
        ),
        (
            "cpp AC (fibonacci)",
            problems["fibonacci"],
            "cpp",
            "AC",
            (
                "#include <bits/stdc++.h>\nint main(){ int n; std::cin>>n; long long a=0,b=1;"
                ' for(int i=0;i<n;i++){ long long t=a+b; a=b; b=t; } std::cout<<a<<"\\n"; }\n'
            ),
        ),
        (
            "javascript AC (reverse)",
            problems["reverse-string"],
            "javascript",
            "AC",
            'const s = require("fs").readFileSync(0, "utf8").replace(/\\n$/, "");\nconsole.log([...s].reverse().join(""));\n',
        ),
        ("cpp CE", apb, "cpp", "CE", "int main( {"),
        ("python TLE", apb, "python", "TLE", "while True: pass\n"),
        ("python RE", apb, "python", "RE", 'raise ValueError("boom")\n'),
        ("python MLE", apb, "python", "MLE", "x = bytearray(1 << 30)\n"),
    ]
    for name, pid, lang, verdict, src in cases:
        suite.check(name, lambda pid=pid, lang=lang, verdict=verdict, src=src: judge.expect(pid, lang, verdict, src))

    def parallel() -> str:
        n = 8
        start = time.monotonic()
        with ThreadPoolExecutor(n) as pool:
            verdicts = list(pool.map(lambda _: judge.submit(apb, "python", APB_PY)["verdict"], range(n)))
        ensure(all(v == "VERDICT_ACCEPTED" for v in verdicts), f"verdicts: {verdicts}")
        return f"{n} submissions accepted in {time.monotonic() - start:.1f}s"

    suite.check("concurrent submissions across runners", parallel)

    # --- custom run (RPC over RabbitMQ)
    suite.section("custom run")

    def run_ok() -> str:
        r = judge.run("python", "print(input()[::-1])", "abc")
        ensure(r["status"] == "RUN_STATUS_OK" and r["stdout"].strip() == "cba", f"run: {r}")
        return f"stdout=cba in {r['timeMs']}ms"

    def run_ce() -> str:
        r = judge.run("c", "int main( {")
        ensure(r["status"] == "RUN_STATUS_COMPILATION_ERROR" and r["compileOutput"], f"run: {r}")
        return "compile output returned"

    suite.check("run python", run_ok)
    suite.check("run compilation error", run_ce)

    # --- sandbox: submitted code runs on the runners' `jobs` network
    suite.section("sandbox isolation")

    def sandbox(source: str) -> str:
        r = judge.run("python", source)
        ensure(r["status"] == "RUN_STATUS_OK", f"probe did not run: {r}")
        return r["stdout"].strip()

    probe_connect = (
        "import socket\n"
        "for host, port in {targets}:\n"
        "    try:\n"
        "        socket.create_connection((host, port), timeout=2).close(); print(f'OPEN {{host}}:{{port}}')\n"
        "    except OSError: pass\n"
    )

    def no_internal_services() -> str:
        targets = [("api", 8000), ("postgres", 5432), ("webapp", 3000)]
        out = sandbox(probe_connect.format(targets=targets))
        ensure(not out, out)
        return "api, postgres, webapp unreachable"

    def no_internet() -> str:
        out = sandbox(probe_connect.format(targets=[("1.1.1.1", 443), ("8.8.8.8", 53)]))
        ensure(not out, out)
        return "no route out"

    def no_credentials() -> str:
        out = sandbox(
            "import os\n"
            "leaks = [k for k, v in os.environ.items() if 'amqp' in v.lower() or 'RABBITMQ' in k]\n"
            "try:\n"
            "    open('/proc/1/environ', 'rb').read(); leaks.append('/proc/1/environ readable')\n"
            "except OSError: pass\n"
            "print(','.join(leaks))\n"
        )
        ensure(not out, f"broker credentials visible to submitted code: {out}")
        return "no broker credentials in env or /proc/1/environ"

    suite.check("cannot reach internal services", no_internal_services)
    suite.check("cannot reach the internet", no_internet)
    suite.check("cannot read the runner's credentials", no_credentials)

    # --- admin
    suite.section("admin")
    suite.check("admin without token rejected", error_case("POST", "/admin/problems", {}, 401))
    if not cfg.admin_token:
        suite.skip("create / judge / delete a problem", "ADMIN_TOKEN not set")
    else:
        created: dict[str, str] = {}

        def create() -> str:
            slug = f"smoke-{int(time.time())}"
            body = {
                "slug": slug,
                "title": "Smoke Square",
                "statement": "Print `n*n`.",
                "timeLimitMs": 1000,
                "memoryLimitMb": 64,
                "testCases": [
                    {"input": "3", "expectedOutput": "9", "isSample": True},
                    {"input": "12", "expectedOutput": "144"},
                ],
            }
            created["id"] = client.post("/admin/problems", body, token=cfg.admin_token, expect=201)["problem"]["id"]
            return f"#{created['id']} {slug}"

        def judge_new() -> str:
            return judge.expect(created["id"], "python", "AC", "n = int(input())\nprint(n * n)\n")

        def duplicate_slug() -> str:
            slug = client.get(f"/problems/{created['id']}")["problem"]["slug"]
            body = {"slug": slug, "title": "dup", "testCases": [{"input": "1", "expectedOutput": "1"}]}
            return client.post("/admin/problems", body, token=cfg.admin_token, expect=409)["error"][:60]

        def delete() -> str:
            client.delete(f"/admin/problems/{created['id']}", token=cfg.admin_token, expect=204)
            client.get(f"/problems/{created['id']}", expect=404)
            return "204, then 404 on read"

        try:
            suite.check("create problem", create)
            if "id" in created:
                suite.check("judge new problem", judge_new)
                suite.check("duplicate slug -> 409", duplicate_slug)
        finally:
            # Always clean up, even when a check above failed or was interrupted.
            if "id" in created:
                suite.check("delete problem", delete)

    return summary(suite)


def summary(suite: Suite) -> int:
    print(f"\npassed: {suite.passed}  failed: {suite.failed}  skipped: {suite.skipped}")
    return 0 if suite.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
