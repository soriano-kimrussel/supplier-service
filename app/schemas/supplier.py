from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SupplierCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    external_id: Annotated[str, Field(min_length=1, max_length=100)]
    country: Annotated[str | None, Field(default=None, min_length=2, max_length=2)]

    @field_validator("name", "external_id")
    @classmethod
    def strip(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("country")
    @classmethod
    def upper(cls, value: str | None) -> str | None:
        return value.upper() if value else None


class SupplierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    name: str
    country: str | None
    status: str
    enrichment_status: str
    categories: list[str]
    risk_summary: str | None
    created_at: datetime
    updated_at: datetime


class SupplierPage(BaseModel):
    items: list[SupplierResponse]
    total: int
    limit: int
    offset: int


class IngestionResponse(BaseModel):
    supplier: SupplierResponse
    created: bool
    enrichment_job_id: int | None


class ErrorResponse(BaseModel):
    detail: str
