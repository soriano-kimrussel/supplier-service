from fastapi import APIRouter

from app.api.v1 import ingestion, suppliers

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(suppliers.router)
api_router.include_router(ingestion.router)
