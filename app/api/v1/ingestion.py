from fastapi import APIRouter, status

from app.api.deps import IngestionServiceDep
from app.schemas import ErrorResponse, IngestionResponse, SupplierResponse

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post(
    "/suppliers/{external_id}",
    response_model=IngestionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest one supplier from the external directory",
    responses={
        404: {"model": ErrorResponse, "description": "Unknown to the directory"},
        502: {"model": ErrorResponse, "description": "Directory unavailable"},
    },
)
async def ingest_supplier(external_id: str, service: IngestionServiceDep):
    """Fetch, normalise and store one supplier, then queue it for enrichment.

    202 rather than 201: the supplier is stored synchronously, but the
    enrichment it was queued for has not happened yet.
    """
    result = await service.ingest(external_id)
    return IngestionResponse(
        supplier=SupplierResponse.model_validate(result.supplier),
        created=result.created,
        enrichment_job_id=result.job_id,
    )
