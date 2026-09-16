"""Ingestion: pull one supplier from the external directory into our database.

Fetch, normalise, upsert, queue enrichment. Running it twice for the same
supplier updates the existing row rather than creating a second one, so the
endpoint is safe to retry and safe to replay.
"""

import logging
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import SupplierSource
from app.models import EnrichmentStatus, Supplier
from app.repositories import EnrichmentJobRepository, SupplierRepository

logger = logging.getLogger(__name__)


class IngestionResult:
    def __init__(self, supplier: Supplier, *, created: bool, job_id: int | None) -> None:
        self.supplier = supplier
        self.created = created
        self.job_id = job_id


class SupplierIngestionService:
    def __init__(
        self,
        session: AsyncSession,
        source: SupplierSource,
        suppliers: SupplierRepository,
        jobs: EnrichmentJobRepository,
    ) -> None:
        self._session = session
        self._source = source
        self._suppliers = suppliers
        self._jobs = jobs

    async def ingest(self, external_id: str) -> IngestionResult:
        raw = await self._source.fetch(external_id)
        values = self.normalize(raw)

        supplier, created = await self._upsert(values)

        # Upstream data changed, so whatever the model said about it is stale.
        supplier.enrichment_status = EnrichmentStatus.PENDING
        job = await self._jobs.enqueue(supplier.id)
        # The supplier row and its enrichment job are committed together: the
        # queue can never point at a supplier that was never stored.
        await self._session.commit()

        logger.info(
            "ingested supplier external_id=%s created=%s job=%s",
            supplier.external_id,
            created,
            job.id,
        )
        return IngestionResult(supplier, created=created, job_id=job.id)

    async def _upsert(self, values: dict[str, Any]) -> tuple[Supplier, bool]:
        existing = await self._suppliers.find_by_external_id(values["external_id"])
        if existing is not None:
            return await self._suppliers.update(existing, values), False

        try:
            return await self._suppliers.create(values), True
        except IntegrityError:
            # Another ingest of the same supplier got there first. Retry as an
            # update instead of failing - re-ingesting must stay idempotent.
            await self._session.rollback()
            existing = await self._suppliers.find_by_external_id(values["external_id"])
            if existing is None:
                raise
            return await self._suppliers.update(existing, values), False

    @staticmethod
    def normalize(raw: dict[str, Any]) -> dict[str, Any]:
        """Map the directory's field names and shapes onto ours.

        The upstream API is inconsistent - names carry whitespace, country is
        sometimes a full name, status is sometimes missing - so normalising is
        its own step with its own tests.
        """
        country = raw.get("country") or raw.get("country_code")
        return {
            "external_id": str(raw["id"]),
            "name": (raw.get("company_name") or raw.get("name") or "").strip(),
            "country": _country_code(country),
            "status": (raw.get("status") or "active").lower(),
            "source_payload": raw,
        }


_COUNTRY_NAMES = {
    "netherlands": "NL",
    "germany": "DE",
    "france": "FR",
    "united kingdom": "GB",
}


def _country_code(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if len(text) == 2:
        return text.upper()
    return _COUNTRY_NAMES.get(text.lower())
