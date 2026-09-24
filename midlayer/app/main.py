"""FastAPI application factory for the midlayer."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api import router
from .clients import Conflict, DaoClient, NotFound, RunnerClient, Unavailable, UpstreamError, make_http_client
from .config import Settings
from .judge import Judge

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("midlayer")


def create_app(settings: Settings | None = None, dao=None, runner=None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.dao = dao or DaoClient(make_http_client(settings.dao_url, settings.dao_timeout_s))
        app.state.runner = runner or RunnerClient(make_http_client(settings.runner_url, settings.runner_timeout_s))
        app.state.languages = []
        app.state.judge = Judge(app.state.dao, app.state.runner, settings.judge_workers)
        await app.state.judge.start(recover=True)
        log.info("midlayer started (dao=%s runner=%s workers=%d)",
                 settings.dao_url, settings.runner_url, settings.judge_workers)
        try:
            yield
        finally:
            await app.state.judge.stop()
            await app.state.dao.aclose()
            await app.state.runner.aclose()

    app = FastAPI(title="oj-midlayer", version="1.0.0", lifespan=lifespan)
    app.include_router(router)

    @app.exception_handler(NotFound)
    async def _not_found(_: Request, exc: NotFound):
        return JSONResponse({"detail": "not found"}, status_code=404)

    @app.exception_handler(Conflict)
    async def _conflict(_: Request, exc: Conflict):
        return JSONResponse({"detail": "already exists"}, status_code=409)

    @app.exception_handler(UpstreamError)
    async def _upstream(_: Request, exc: UpstreamError):
        log.error("upstream error: %s", exc)
        code = 400 if exc.status == 400 else 502
        return JSONResponse({"detail": exc.detail if code == 400 else "upstream error"}, status_code=code)

    @app.exception_handler(Unavailable)
    async def _unavailable(_: Request, exc: Unavailable):
        log.error("dependency unavailable: %s", exc)
        return JSONResponse({"detail": "service temporarily unavailable"}, status_code=503)

    return app


app = create_app()
