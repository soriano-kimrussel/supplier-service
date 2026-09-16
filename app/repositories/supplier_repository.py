"""Persistence for suppliers. The only module that writes SQL for them."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Supplier


class SupplierRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, supplier_id: int) -> Supplier | None:
        return await self._session.get(Supplier, supplier_id)

    async def find_by_external_id(self, external_id: str) -> Supplier | None:
        result = await self._session.execute(
            select(Supplier).where(Supplier.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self, *, limit: int, offset: int, country: str | None = None
    ) -> tuple[list[Supplier], int]:
        query = select(Supplier)
        if country:
            query = query.where(Supplier.country == country)

        total = await self._session.scalar(
            select(func.count()).select_from(query.subquery())
        )
        result = await self._session.execute(
            query.order_by(Supplier.id).limit(limit).offset(offset)
        )
        return list(result.scalars()), total or 0

    async def create(self, values: dict[str, Any]) -> Supplier:
        supplier = Supplier(**values)
        self._session.add(supplier)
        await self._session.flush()
        return supplier

    async def update(self, supplier: Supplier, values: dict[str, Any]) -> Supplier:
        for key, value in values.items():
            setattr(supplier, key, value)
        await self._session.flush()
        return supplier
