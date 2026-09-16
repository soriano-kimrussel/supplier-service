"""Background enrichment: hand a stored supplier to the model, save the result.

Claiming a job and processing it are separate transactions on purpose - the
model call can take seconds, and holding a database transaction open across it
would pin a connection for no reason.
"""

import logging

from app.clients import Enricher
from app.db import Database
from app.errors import EnrichmentFailed
from app.models import EnrichmentStatus
from app.repositories import EnrichmentJobRepository, SupplierRepository

logger = logging.getLogger(__name__)


class EnrichmentService:
    def __init__(
        self,
        database: Database,
        enricher: Enricher | None,
        *,
        max_attempts: int = 3,
    ) -> None:
        self._database = database
        self._enricher = enricher
        self._max_attempts = max_attempts

    async def run_once(self, batch_size: int) -> int:
        """Process one batch. Returns how many jobs were handled."""
        job_ids = await self._claim(batch_size)
        for job_id in job_ids:
            await self._process(job_id)
        return len(job_ids)

    async def _claim(self, batch_size: int) -> list[int]:
        async with self._database.session() as session:
            jobs = await EnrichmentJobRepository(session).claim_pending(batch_size)
            return [job.id for job in jobs]

    async def _process(self, job_id: int) -> None:
        async with self._database.session() as session:
            jobs = EnrichmentJobRepository(session)
            suppliers = SupplierRepository(session)

            job = await jobs.get(job_id)
            if job is None:
                return
            supplier = await suppliers.get(job.supplier_id)
            if supplier is None:
                await jobs.mark_failed(job, "supplier no longer exists", retry=False)
                return

            if self._enricher is None:
                supplier.enrichment_status = EnrichmentStatus.SKIPPED
                await jobs.mark_done(job)
                return

            try:
                profile = await self._enricher.enrich(
                    {
                        "external_id": supplier.external_id,
                        "name": supplier.name,
                        "country": supplier.country,
                        "status": supplier.status,
                        **supplier.source_payload,
                    }
                )
            except EnrichmentFailed as exc:
                retry = exc.retryable and job.attempts < self._max_attempts
                if not retry:
                    supplier.enrichment_status = EnrichmentStatus.FAILED
                logger.warning(
                    "enrichment failed job=%s attempts=%s retry=%s: %s",
                    job.id,
                    job.attempts,
                    retry,
                    exc,
                )
                await jobs.mark_failed(job, str(exc), retry=retry)
                return

            supplier.categories = profile.categories
            supplier.risk_summary = profile.risk_summary
            supplier.enrichment_status = EnrichmentStatus.READY
            await jobs.mark_done(job)
            logger.info("enriched supplier=%s job=%s", supplier.id, job.id)
