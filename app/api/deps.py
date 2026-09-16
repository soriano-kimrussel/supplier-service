"""Dependency wiring.

Every request gets its own session; the clients and the engine are built once
at startup and live on `app.state`. Nothing below this module imports FastAPI.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import SupplierSource
from app.db import Database
from app.repositories import EnrichmentJobRepository, SupplierRepository
from app.services import SupplierIngestionService, SupplierService


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_supplier_source(request: Request) -> SupplierSource:
    return request.app.state.supplier_source


async def get_session(
    database: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[AsyncSession]:
    async with database.session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_supplier_repository(session: SessionDep) -> SupplierRepository:
    return SupplierRepository(session)


def get_job_repository(session: SessionDep) -> EnrichmentJobRepository:
    return EnrichmentJobRepository(session)


def get_supplier_service(
    session: SessionDep,
    repository: Annotated[SupplierRepository, Depends(get_supplier_repository)],
    jobs: Annotated[EnrichmentJobRepository, Depends(get_job_repository)],
) -> SupplierService:
    return SupplierService(session, repository, jobs)


def get_ingestion_service(
    session: SessionDep,
    source: Annotated[SupplierSource, Depends(get_supplier_source)],
    suppliers: Annotated[SupplierRepository, Depends(get_supplier_repository)],
    jobs: Annotated[EnrichmentJobRepository, Depends(get_job_repository)],
) -> SupplierIngestionService:
    return SupplierIngestionService(session, source, suppliers, jobs)


SupplierServiceDep = Annotated[SupplierService, Depends(get_supplier_service)]
IngestionServiceDep = Annotated[SupplierIngestionService, Depends(get_ingestion_service)]
