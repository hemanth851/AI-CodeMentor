from pydantic import BaseModel, Field


class HealthCheckResponse(BaseModel):
    """Response model for the health check endpoint."""
    status: str = Field(
        default="ok",
        description="Status indicator of the service"
    )
    message: str = Field(
        default="AI CodeMentor backend is running",
        description="Informative status message"
    )
