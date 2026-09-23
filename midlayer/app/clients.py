"""Async HTTP clients for the downstream services (oj-dao and oj-runner)."""

from __future__ import annotations

from typing import Any

import httpx


class UpstreamError(Exception):
    """A downstream service answered with an error status."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


class NotFound(UpstreamError):
    pass


class Conflict(UpstreamError):
    pass


class Unavailable(Exception):
    """A downstream service could not be reached."""


def make_http_client(base_url: str, timeout: float) -> httpx.AsyncClient:
    """Build a client for ``http(s)://host:port`` or ``unix:///path.sock``."""
    if base_url.startswith("unix://"):
        transport = httpx.AsyncHTTPTransport(uds=base_url[len("unix://"):])
        return httpx.AsyncClient(transport=transport, base_url="http://runner", timeout=timeout)
    return httpx.AsyncClient(base_url=base_url, timeout=timeout)


async def _request(client: httpx.AsyncClient, method: str, path: str, **kw: Any) -> Any:
    try:
        resp = await client.request(method, path, **kw)
    except httpx.TransportError as exc:  # connection refused, timeouts, ...
        raise Unavailable(f"{client.base_url}: {exc!r}") from exc
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("error") or resp.text
        except ValueError:
            detail = resp.text
        cls = {404: NotFound, 409: Conflict}.get(resp.status_code, UpstreamError)
        raise cls(resp.status_code, detail)
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


class DaoClient:
    def __init__(self, client: httpx.AsyncClient):
        self._c = client

    async def aclose(self) -> None:
        await self._c.aclose()

    async def health(self) -> Any:
        return await _request(self._c, "GET", "/healthz")

    # problems
    async def list_problems(self) -> list[dict]:
        return await _request(self._c, "GET", "/problems")

    async def get_problem(self, pid: int) -> dict:
        return await _request(self._c, "GET", f"/problems/{pid}")

    async def create_problem(self, data: dict) -> dict:
        return await _request(self._c, "POST", "/problems", json=data)

    async def update_problem(self, pid: int, data: dict) -> dict:
        return await _request(self._c, "PUT", f"/problems/{pid}", json=data)

    async def delete_problem(self, pid: int) -> None:
        await _request(self._c, "DELETE", f"/problems/{pid}")

    # test cases
    async def list_testcases(self, pid: int, samples_only: bool = False) -> list[dict]:
        params = {"samples_only": "true"} if samples_only else None
        return await _request(self._c, "GET", f"/problems/{pid}/testcases", params=params)

    async def create_testcase(self, pid: int, data: dict) -> dict:
        return await _request(self._c, "POST", f"/problems/{pid}/testcases", json=data)

    async def delete_testcase(self, pid: int, tcid: int) -> None:
        await _request(self._c, "DELETE", f"/problems/{pid}/testcases/{tcid}")

    # submissions
    async def create_submission(self, data: dict) -> dict:
        return await _request(self._c, "POST", "/submissions", json=data)

    async def get_submission(self, sid: int) -> dict:
        return await _request(self._c, "GET", f"/submissions/{sid}")

    async def list_submissions(self, **filters: Any) -> list[dict]:
        params = {k: v for k, v in filters.items() if v not in (None, "")}
        return await _request(self._c, "GET", "/submissions", params=params)

    async def update_submission(self, sid: int, **fields: Any) -> dict:
        return await _request(self._c, "PATCH", f"/submissions/{sid}", json=fields)


class RunnerClient:
    def __init__(self, client: httpx.AsyncClient):
        self._c = client

    async def aclose(self) -> None:
        await self._c.aclose()

    async def health(self) -> Any:
        return await _request(self._c, "GET", "/healthz")

    async def languages(self) -> list[dict]:
        return await _request(self._c, "GET", "/languages")

    async def execute(
        self,
        language: str,
        source: str,
        tests: list[dict],
        time_limit_ms: int,
        memory_limit_mb: int,
    ) -> dict:
        return await _request(
            self._c,
            "POST",
            "/execute",
            json={
                "language": language,
                "source": source,
                "tests": tests,
                "time_limit_ms": time_limit_ms,
                "memory_limit_mb": memory_limit_mb,
            },
        )
