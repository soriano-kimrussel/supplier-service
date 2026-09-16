"""Business rules for suppliers.

No HTTP and no SQL: the API layer turns these errors into status codes and the
repository does the persistence. The service owns the transaction boundary -
one call, one committed unit of work.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import SupplierAlreadyExists, SupplierNotFound
from app.models import Supplier
from app.repositories import EnrichmentJobRepository, SupplierRepository
from app.schemas import SupplierCreate


class SupplierService:
    def __init__(
        self,
        session: AsyncSession,
        repository: SupplierRepository,
        jobs: EnrichmentJobRepository,
    ) -> None:
        self._session = session
        self._repository = repository
        self._jobs = jobs

    async def create(self, payload: SupplierCreate) -> Supplier:
        existing = await self._repository.find_by_external_id(payload.external_id)
        if existing is not None:
            raise SupplierAlreadyExists(payload.external_id)

        values = {
            "external_id": payload.external_id,
            "name": payload.name,
            "country": payload.country,
            "source_payload": {"origin": "api"},
        }
        try:
            supplier = await self._repository.create(values)
            # Every new supplier goes through the same enrichment queue,
            # however it arrived.
            await self._jobs.enqueue(supplier.id)
            await self._session.commit()
        except IntegrityError as exc:
            # Two requests for the same external_id can both pass the check
            # above; the unique index is what actually decides.
            await self._session.rollback()
            raise SupplierAlreadyExists(payload.external_id) from exc

        return supplier

    async def get(self, supplier_id: int) -> Supplier:
        supplier = await self._repository.get(supplier_id)
        if supplier is None:
            raise SupplierNotFound(supplier_id)
        return supplier

    async def get_by_external_id(self, external_id: str) -> Supplier:
        supplier = await self._repository.find_by_external_id(external_id)
        if supplier is None:
            raise SupplierNotFound(external_id)
        return supplier

    async def list(
        self, *, limit: int, offset: int, country: str | None = None
    ) -> tuple[list[Supplier], int]:
        return await self._repository.list(limit=limit, offset=offset, country=country)
