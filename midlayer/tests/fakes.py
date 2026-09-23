"""In-memory fakes for oj-dao and oj-runner used by the tests."""

from __future__ import annotations

import copy
import itertools
from datetime import datetime, timezone

from app.clients import Conflict, NotFound, Unavailable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakeDao:
    def __init__(self):
        self.problems: dict[int, dict] = {}
        self.testcases: dict[int, dict] = {}
        self.submissions: dict[int, dict] = {}
        self._ids = itertools.count(1)
        self.down = False

    def _check(self):
        if self.down:
            raise Unavailable("dao down")

    async def aclose(self):
        pass

    async def health(self):
        self._check()
        return {"status": "ok"}

    async def list_problems(self):
        self._check()
        return [copy.deepcopy(p) for _, p in sorted(self.problems.items())]

    async def get_problem(self, pid):
        self._check()
        if pid not in self.problems:
            raise NotFound(404, "not found")
        return copy.deepcopy(self.problems[pid])

    async def create_problem(self, data):
        if any(p["slug"] == data["slug"] for p in self.problems.values()):
            raise Conflict(409, "already exists")
        pid = next(self._ids)
        self.problems[pid] = {"id": pid, "created_at": _now(), **data}
        return copy.deepcopy(self.problems[pid])

    async def update_problem(self, pid, data):
        if pid not in self.problems:
            raise NotFound(404, "not found")
        self.problems[pid].update(data)
        return copy.deepcopy(self.problems[pid])

    async def delete_problem(self, pid):
        if self.problems.pop(pid, None) is None:
            raise NotFound(404, "not found")
        self.testcases = {k: v for k, v in self.testcases.items() if v["problem_id"] != pid}

    async def list_testcases(self, pid, samples_only=False):
        await self.get_problem(pid)
        out = [
            copy.deepcopy(tc)
            for tc in self.testcases.values()
            if tc["problem_id"] == pid and (tc["is_sample"] or not samples_only)
        ]
        return sorted(out, key=lambda t: (t["ordinal"], t["id"]))

    async def create_testcase(self, pid, data):
        await self.get_problem(pid)
        tid = next(self._ids)
        self.testcases[tid] = {"id": tid, "problem_id": pid, **data}
        return copy.deepcopy(self.testcases[tid])

    async def delete_testcase(self, pid, tcid):
        tc = self.testcases.get(tcid)
        if tc is None or tc["problem_id"] != pid:
            raise NotFound(404, "not found")
        del self.testcases[tcid]

    async def create_submission(self, data):
        await self.get_problem(data["problem_id"])
        sid = next(self._ids)
        self.submissions[sid] = {
            "id": sid, "status": "PENDING", "verdict": "", "passed": 0, "total": 0,
            "time_ms": 0, "message": "", "results": [], "created_at": _now(), "updated_at": _now(),
            **data,
        }
        return copy.deepcopy(self.submissions[sid])

    async def get_submission(self, sid):
        if sid not in self.submissions:
            raise NotFound(404, "not found")
        return copy.deepcopy(self.submissions[sid])

    async def list_submissions(self, problem_id=None, username=None, status=None, limit=50, offset=0):
        self._check()
        out = [
            s for s in self.submissions.values()
            if (not problem_id or s["problem_id"] == problem_id)
            and (not username or s["username"] == username)
            and (not status or s["status"] == status)
        ]
        out.sort(key=lambda s: -s["id"])
        return copy.deepcopy(out[offset: offset + limit])

    async def update_submission(self, sid, **fields):
        if sid not in self.submissions:
            raise NotFound(404, "not found")
        self.submissions[sid].update(fields, updated_at=_now())
        return copy.deepcopy(self.submissions[sid])


class FakeRunner:
    """Interprets a tiny 'language': the source names a behaviour.

    * ``echo``     -> stdout = stdin
    * ``double``   -> stdout = 2 * int(stdin)
    * ``tle``/``re``/``mle`` -> that runner status
    * ``ce``       -> compilation error
    * ``boom``     -> raises (simulates runner outage)
    """

    LANGS = [{"id": "python", "name": "Python 3"}, {"id": "cpp", "name": "C++17"}]

    def __init__(self):
        self.calls = []

    async def aclose(self):
        pass

    async def health(self):
        return {"status": "ok"}

    async def languages(self):
        return list(self.LANGS)

    async def execute(self, language, source, tests, time_limit_ms, memory_limit_mb):
        self.calls.append({"language": language, "source": source, "tests": tests})
        src = source.strip()
        if src == "boom":
            raise Unavailable("runner down")
        if src == "ce":
            return {"status": "CE", "compile_output": "main.cpp:1: error", "results": []}
        results = []
        for t in tests:
            res = {"id": t["id"], "status": "OK", "stdout": "", "stderr": "", "exit_code": 0, "time_ms": 5, "memory_kb": 1000}
            if src == "echo":
                res["stdout"] = t["stdin"]
            elif src == "double":
                res["stdout"] = f"{2 * int(t['stdin'])}\n"
            elif src in ("tle", "re", "mle"):
                res["status"] = src.upper()
            results.append(res)
        return {"status": "OK", "compile_output": "", "results": results}
