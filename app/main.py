"""Application factory and process wiring."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1 import health
from app.api.v1.router import api_router
from app.clients import SupplierDirectoryClient
from app.config import Settings, get_settings
from app.db import Database
from app.errors import (
    DomainError,
    SupplierAlreadyExists,
    SupplierNotFound,
    UpstreamNotFound,
    UpstreamUnavailable,
)

logger = logging.getLogger(__name__)

# The one place that knows which domain error means which status code.
STATUS_FOR_ERROR: list[tuple[type[DomainError], int]] = [
    (SupplierAlreadyExists, 409),
    (SupplierNotFound, 404),
    (UpstreamNotFound, 404),
    (UpstreamUnavailable, 502),
]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(settings.database_url, echo=settings.database_echo)
        if settings.create_schema_on_startup:
            await database.create_schema()

        headers = (
            {"Authorization": f"Bearer {settings.supplier_api_key}"}
            if settings.supplier_api_key
            else {}
        )
        http_client = httpx.AsyncClient(
            base_url=settings.supplier_api_base_url,
            timeout=settings.supplier_api_timeout_seconds,
            headers=headers,
        )

        app.state.settings = settings
        app.state.database = database
        app.state.supplier_source = SupplierDirectoryClient(
            http_client, max_attempts=settings.supplier_api_max_attempts
        )

        logger.info("%s started (%s)", settings.app_name, settings.environment)
        try:
            yield
        finally:
            await http_client.aclose()
            await database.dispose()

    app = FastAPI(
        title="Supplier Service",
        version="1.0.0",
        summary="Owns supplier records: ingestion from the external directory, "
        "storage, enrichment and read access for other services.",
        lifespan=lifespan,
    )

    app.include_router(health.router)
    app.include_router(api_router)

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        for error_type, status_code in STATUS_FOR_ERROR:
            if isinstance(exc, error_type):
                return JSONResponse({"detail": str(exc)}, status_code=status_code)

        logger.exception("unhandled domain error", exc_info=exc)
        return JSONResponse({"detail": "Internal error"}, status_code=500)

    return app


app = create_app()
