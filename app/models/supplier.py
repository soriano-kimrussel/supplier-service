from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class EnrichmentStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Identity in the upstream directory. Unique, so ingestion can be re-run safely.
    external_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str | None] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    # Written by the enrichment worker, never by the write endpoints.
    enrichment_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EnrichmentStatus.PENDING
    )
    categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    risk_summary: Mapped[str | None] = mapped_column(Text)

    # The upstream response as received, kept for debugging and re-normalisation.
    source_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    jobs: Mapped[list["EnrichmentJob"]] = relationship(
        back_populates="supplier", cascade="all, delete-orphan"
    )


class EnrichmentJob(Base, TimestampMixin):
    """One unit of background work: enrich a single supplier."""

    __tablename__ = "enrichment_jobs"
    __table_args__ = (Index("ix_enrichment_jobs_status_id", "status", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=JobStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)

    supplier: Mapped[Supplier] = relationship(back_populates="jobs")
