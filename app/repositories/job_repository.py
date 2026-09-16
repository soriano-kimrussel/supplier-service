"""Persistence for the enrichment job queue."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EnrichmentJob, JobStatus


class EnrichmentJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, supplier_id: int) -> EnrichmentJob:
        job = EnrichmentJob(supplier_id=supplier_id, status=JobStatus.PENDING)
        self._session.add(job)
        await self._session.flush()
        return job

    async def claim_pending(self, limit: int) -> list[EnrichmentJob]:
        """Take up to `limit` pending jobs and mark them running.

        On PostgreSQL the rows are locked with SKIP LOCKED, so several workers
        can run against the same queue without handing out the same job twice.
        SQLite has no such lock, which is fine - tests run one worker.
        """
        query = (
            select(EnrichmentJob)
            .where(EnrichmentJob.status == JobStatus.PENDING)
            .order_by(EnrichmentJob.id)
            .limit(limit)
        )
        if self._session.get_bind().dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)

        jobs = list((await self._session.execute(query)).scalars())
        for job in jobs:
            job.status = JobStatus.RUNNING
            job.attempts += 1
        await self._session.flush()
        return jobs

    async def mark_done(self, job: EnrichmentJob) -> None:
        job.status = JobStatus.DONE
        job.last_error = None
        await self._session.flush()

    async def mark_failed(self, job: EnrichmentJob, error: str, *, retry: bool) -> None:
        job.status = JobStatus.PENDING if retry else JobStatus.FAILED
        job.last_error = error[:500]
        await self._session.flush()

    async def get(self, job_id: int) -> EnrichmentJob | None:
        return await self._session.get(EnrichmentJob, job_id)
