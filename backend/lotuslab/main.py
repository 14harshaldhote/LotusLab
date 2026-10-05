"""FastAPI application factory."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from . import MODEL_VERSION
from .api.routes import router
from .config import Settings
from .services.open_meteo import OpenMeteoClient
from .services.simulation import LotusService

log = logging.getLogger("lotuslab")


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = OpenMeteoClient(settings, transport=transport)
        app.state.service = LotusService(settings, client)
        try:
            yield
        finally:
            await client.aclose()

    app = FastAPI(
        title="LotusLab API",
        version=MODEL_VERSION,
        description="Weather-driven natural lotus pond simulation. Weather data by Open-Meteo.com (CC BY 4.0).",
        lifespan=lifespan,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["X-Result-Cache", "X-Weather-Cache", "Server-Timing", "X-Response-Time-Ms"],
    )

    @app.middleware("http")
    async def timing(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - start) * 1000.0
        response.headers["X-Response-Time-Ms"] = f"{ms:.2f}"
        log.info("%s %s -> %d in %.1f ms", request.method, request.url.path, response.status_code, ms)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Echoing raw input back can itself be invalid JSON (NaN, Infinity), so only
        # the location, message and type of each problem are returned.
        errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    app.include_router(router)
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = create_app()
