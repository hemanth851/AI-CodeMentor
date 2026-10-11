"""API router initialization."""
from app.api.health import router as health_router
from app.api.analyze import router as analyze_router

__all__ = ["health_router", "analyze_router"]
