from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.api.deps import get_supplier_source
from app.config import Settings
from app.db import Database
from app.errors import UpstreamNotFound, UpstreamUnavailable
from app.main import create_app


class StubDirectory:
    """Stand-in for the external supplier directory."""

    def __init__(self, records: dict[str, dict[str, Any]] | None = None) -> None:
        self.records = records or {}
        self.unavailable = False
        self.calls: list[str] = []

    async def fetch(self, external_id: str) -> dict[str, Any]:
        self.calls.append(external_id)
        if self.unavailable:
            raise UpstreamUnavailable("directory down")
        try:
            return self.records[external_id]
        except KeyError:
            raise UpstreamNotFound(external_id) from None


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
        create_schema_on_startup=True,
        anthropic_api_key=None,
    )


@pytest.fixture
def directory() -> StubDirectory:
    return StubDirectory(
        {
            "SUP-1": {
                "id": "SUP-1",
                "company_name": "  Northwind Foods  ",
                "country": "Netherlands",
                "status": "ACTIVE",
            }
        }
    )


@pytest.fixture
def app(settings: Settings, directory: StubDirectory) -> FastAPI:
    application = create_app(settings)
    application.dependency_overrides[get_supplier_source] = lambda: directory
    return application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as http_client:
            yield http_client


@pytest_asyncio.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    db = Database(settings.database_url)
    await db.create_schema()
    try:
        yield db
    finally:
        await db.dispose()
