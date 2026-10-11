import logging
from fastapi import APIRouter, HTTPException, status
from app.models.quiz import (
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizSubmitRequest,
    QuizSubmitResponse,
)
from app.services.quiz_service import (
    generate_quiz,
    score_quiz,
    QuizGenerationError,
)
from app.services.llm_service import (
    get_gemini_client,
    LLMConfigurationError,
    LLMServiceError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/quiz", tags=["Quiz"])


@router.post(
    "/generate",
    response_model=QuizGenerateResponse,
    response_model_exclude_none=True,
    summary="Generate Dynamic Code Assessment Quiz",
    description="Generates an interactive 5-question multiple choice assessment grounded in the user's code, language, and analysis facts.",
)
def generate_quiz_endpoint(payload: QuizGenerateRequest) -> QuizGenerateResponse:
    """
    Validate request, query Gemini to dynamically formulate 5 code-grounded questions,
    and return public questions with answers hidden behind a secure signed token.
    """
    # 1. Verify Gemini client configuration
    try:
        get_gemini_client()
    except LLMConfigurationError as e:
        logger.error(f"Quiz configuration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    # 2. Generate quiz
    try:
        result = generate_quiz(
            code=payload.code,
            language=payload.language,
            learning_level=payload.learning_level,
            analysis=payload.analysis,
            static_analysis=payload.static_analysis,
        )
        return result

    except LLMConfigurationError as e:
        logger.error(f"Configuration error during quiz generation: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    except QuizGenerationError as e:
        logger.warning(f"Generated quiz failed validation rules: {e}")
        err_msg = str(e)
        if "too short" in err_msg.lower() or "insufficient" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=err_msg,
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The AI assessment generator produced an invalid quiz format ({e}). Please try again.",
        )

    except LLMServiceError as e:
        logger.error(f"LLM service error during quiz generation: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        )

    except Exception as e:
        logger.exception("Unexpected error generating assessment quiz")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The quiz could not be generated right now. Please try again.",
        )


@router.post(
    "/submit",
    response_model=QuizSubmitResponse,
    response_model_exclude_none=True,
    summary="Submit and Deterministically Score Quiz",
    description="Evaluates user-selected answers deterministically, returns score, percentage, and reveals correct answers with explanations.",
)
def submit_quiz_endpoint(payload: QuizSubmitRequest) -> QuizSubmitResponse:
    """
    Deterministically score the user's answers against the signed/cached answer key.
    """
    try:
        result = score_quiz(
            quiz_id=payload.quiz_id,
            quiz_token=payload.quiz_token,
            user_answers=payload.answers,
        )
        return result
    except ValueError as val_err:
        logger.warning(f"Quiz submission rejected: {val_err}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except Exception as e:
        logger.exception("Unexpected error scoring quiz submission")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to score the quiz right now. Please try again.",
        )
