from fastapi import APIRouter
from app.models.health import HealthCheckResponse

router = APIRouter(prefix="/api", tags=["Health"])


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Health Check",
    description="Returns the status of the AI CodeMentor backend API.",
)
def get_health() -> HealthCheckResponse:
    """Return health check status."""
    return HealthCheckResponse(
        status="ok",
        message="AI CodeMentor backend is running"
    )
