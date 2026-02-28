"""
Health check endpoint.
"""

from fastapi import APIRouter

from app.models import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness check for Docker HEALTHCHECK and monitoring."""
    return HealthResponse(status="ok")
