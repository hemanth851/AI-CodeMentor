import logging
from fastapi import APIRouter, HTTPException, status
from app.models.tutor import (
    TutorRequest,
    TutorResponse,
)
from app.services.llm_service import (
    ask_tutor,
    get_gemini_client,
    LLMConfigurationError,
    LLMServiceError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Tutor"])


@router.post(
    "/tutor",
    response_model=TutorResponse,
    response_model_exclude_none=True,
    summary="Ask AI Tutor",
    description="Interactive educational Q&A grounded strictly in the currently analyzed source code, static facts, and previous analysis.",
)
def tutor_endpoint(payload: TutorRequest) -> TutorResponse:
    """
    Validate tutor question and grounded context, and return an educational answer.
    """
    # 1. Verify Gemini client configuration
    try:
        get_gemini_client()
    except LLMConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    # 2. Query Gemini Tutor with grounded context
    try:
        result = ask_tutor(
            code=payload.code,
            language=payload.language,
            learning_level=payload.learning_level,
            question=payload.question,
            static_analysis=payload.static_analysis,
            analysis=payload.analysis,
            history=payload.history,
        )

        return TutorResponse(
            success=True,
            answer=result.answer,
            key_points=result.key_points,
            related_code=result.related_code,
            grounded=result.grounded,
            error=None,
        )

    except LLMConfigurationError as e:
        logger.error(f"Configuration error during tutor request: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    except LLMServiceError as e:
        logger.error(f"LLM service error during tutor request: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        )

    except Exception as e:
        logger.exception("Unexpected error while answering tutor question")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The AI Tutor could not answer right now. Please try again.",
        )
