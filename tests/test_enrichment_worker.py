import httpx
from sqlalchemy import select

from app.clients import SupplierProfile
from app.db import Database
from app.errors import EnrichmentFailed
from app.models import EnrichmentJob, JobStatus, Supplier
from app.services import EnrichmentService


class StubEnricher:
    def __init__(self, profile: SupplierProfile | None = None, error: Exception | None = None):
        self.profile = profile
        self.error = error
        self.calls: list[dict] = []

    async def enrich(self, supplier: dict) -> SupplierProfile:
        self.calls.append(supplier)
        if self.error is not None:
            raise self.error
        return self.profile


async def _ingest(client: httpx.AsyncClient) -> int:
    response = await client.post("/api/v1/ingestion/suppliers/SUP-1")
    return response.json()["supplier"]["id"]


async def _load(database: Database, supplier_id: int) -> tuple[Supplier, EnrichmentJob]:
    async with database.session() as session:
        supplier = await session.get(Supplier, supplier_id)
        job = (
            await session.execute(
                select(EnrichmentJob)
                .where(EnrichmentJob.supplier_id == supplier_id)
                .order_by(EnrichmentJob.id.desc())
            )
        ).scalars().first()
        return supplier, job


async def test_worker_enriches_a_queued_supplier(
    client: httpx.AsyncClient, database: Database
):
    supplier_id = await _ingest(client)
    enricher = StubEnricher(
        SupplierProfile(categories=["dairy", "packaging"], risk_summary="Low risk.")
    )
    service = EnrichmentService(database, enricher)

    handled = await service.run_once(batch_size=5)

    assert handled == 1
    supplier, job = await _load(database, supplier_id)
    assert supplier.enrichment_status == "ready"
    assert supplier.categories == ["dairy", "packaging"]
    assert supplier.risk_summary == "Low risk."
    assert job.status == JobStatus.DONE
    # The model sees the stored record, including the raw upstream payload.
    assert enricher.calls[0]["external_id"] == "SUP-1"


async def test_queue_is_empty_after_a_successful_run(
    client: httpx.AsyncClient, database: Database
):
    await _ingest(client)
    service = EnrichmentService(database, StubEnricher(SupplierProfile(risk_summary="ok")))

    assert await service.run_once(batch_size=5) == 1
    assert await service.run_once(batch_size=5) == 0


async def test_retryable_failure_is_requeued_until_attempts_run_out(
    client: httpx.AsyncClient, database: Database
):
    supplier_id = await _ingest(client)
    enricher = StubEnricher(error=EnrichmentFailed("rate limited", retryable=True))
    service = EnrichmentService(database, enricher, max_attempts=2)

    await service.run_once(batch_size=5)
    _, job = await _load(database, supplier_id)
    assert job.status == JobStatus.PENDING  # queued for another attempt
    assert job.attempts == 1

    await service.run_once(batch_size=5)
    supplier, job = await _load(database, supplier_id)
    assert job.status == JobStatus.FAILED
    assert job.attempts == 2
    assert supplier.enrichment_status == "failed"
    assert len(enricher.calls) == 2


async def test_permanent_failure_is_not_retried(
    client: httpx.AsyncClient, database: Database
):
    supplier_id = await _ingest(client)
    enricher = StubEnricher(error=EnrichmentFailed("model declined", retryable=False))
    service = EnrichmentService(database, enricher, max_attempts=3)

    await service.run_once(batch_size=5)

    supplier, job = await _load(database, supplier_id)
    assert job.status == JobStatus.FAILED
    assert job.attempts == 1
    assert supplier.enrichment_status == "failed"


async def test_without_an_enricher_the_job_is_skipped_not_failed(
    client: httpx.AsyncClient, database: Database
):
    supplier_id = await _ingest(client)
    service = EnrichmentService(database, None)

    await service.run_once(batch_size=5)

    supplier, job = await _load(database, supplier_id)
    assert supplier.enrichment_status == "skipped"
    assert job.status == JobStatus.DONE


async def test_batch_size_bounds_the_work_per_cycle(
    client: httpx.AsyncClient, database: Database
):
    await client.post("/api/v1/ingestion/suppliers/SUP-1")
    await client.post("/api/v1/ingestion/suppliers/SUP-1")  # a second job, same supplier
    service = EnrichmentService(database, StubEnricher(SupplierProfile(risk_summary="ok")))

    assert await service.run_once(batch_size=1) == 1
    assert await service.run_once(batch_size=1) == 1
    assert await service.run_once(batch_size=1) == 0


async def test_a_supplier_created_through_the_api_is_queued_too(
    client: httpx.AsyncClient, database: Database
):
    response = await client.post(
        "/api/v1/suppliers", json={"name": "Direct Ltd", "external_id": "SUP-DIRECT"}
    )
    supplier_id = response.json()["id"]
    service = EnrichmentService(
        database, StubEnricher(SupplierProfile(categories=["dairy"], risk_summary="ok"))
    )

    assert await service.run_once(batch_size=5) == 1

    supplier, job = await _load(database, supplier_id)
    assert supplier.enrichment_status == "ready"
    assert job.status == JobStatus.DONE
