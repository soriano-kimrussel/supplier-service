from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import SupplierServiceDep
from app.schemas import ErrorResponse, SupplierCreate, SupplierPage, SupplierResponse

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.post(
    "",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse, "description": "external_id already used"}},
)
async def create_supplier(payload: SupplierCreate, service: SupplierServiceDep):
    return await service.create(payload)


@router.get("", response_model=SupplierPage)
async def list_suppliers(
    service: SupplierServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    country: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
):
    items, total = await service.list(
        limit=limit, offset=offset, country=country.upper() if country else None
    )
    return SupplierPage(
        items=[SupplierResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{supplier_id}",
    response_model=SupplierResponse,
    responses={404: {"model": ErrorResponse, "description": "No such supplier"}},
)
async def get_supplier(supplier_id: int, service: SupplierServiceDep):
    return await service.get(supplier_id)
