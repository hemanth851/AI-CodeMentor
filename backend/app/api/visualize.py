import logging
from fastapi import APIRouter, HTTPException, status
from app.models.visualize import VisualizeRequest, VisualizeResponse
from app.services.visualizer import trace_python_code, visualize_any_code
from app.services.detector import detect_language

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Visualize"])


@router.post(
    "/visualize",
    response_model=VisualizeResponse,
    response_model_exclude_none=True,
    summary="Multi-Language Algorithm Execution Visualization",
    description="Traces the execution of supported code across all programming languages into step-by-step educational trace events.",
)
def visualize_endpoint(payload: VisualizeRequest) -> VisualizeResponse:
    """
    Deterministically or dynamically trace algorithm execution steps for any programming language.
    """
    try:
        lang = payload.language.strip() if payload.language else "Python"
        if not lang or lang.lower() in ("auto detect", "snippet"):
            detection = detect_language(payload.code)
            lang = detection.language or "Python"

        response = visualize_any_code(code=payload.code, language=lang)
        return response
    except Exception as e:
        logger.exception("Unexpected error during algorithm visualization tracing")
        return VisualizeResponse(
            status="error",
            supported=True,
            trace=[],
            total_steps=0,
            final_state={},
            termination_reason="runtime_error",
            error="An unexpected server error occurred during visualization. Please verify your code syntax.",
        )
