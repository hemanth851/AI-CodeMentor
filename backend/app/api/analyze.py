import logging
from fastapi import APIRouter, HTTPException, status
from app.models.analysis import (
    AnalyzeCodeRequest,
    AnalyzeCodeResponse,
    PotentialIssue,
    SUPPORTED_LANGUAGES,
)
from app.services.detector import detect_language
from app.services.static_analyzer import analyze_static
from app.services.analysis_cache import analysis_cache
from app.services import llm_service
from app.services.llm_service import analyze_code, get_gemini_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Analysis"])

AMBIGUOUS_SNIPPET_MESSAGE = (
    "The code snippet is too short to confidently determine the programming language.\n\n"
    "Please provide a few more lines of code so I can identify the language and explain it accurately."
)

UNSUPPORTED_LANGUAGE_MESSAGE = (
    "This programming language is not currently supported by AI CodeMentor."
)


@router.post(
    "/analyze",
    response_model=AnalyzeCodeResponse,
    response_model_exclude_none=True,
    summary="Analyze Code",
    description="Automatically detects programming language across 13 supported languages and generates structured AI explanation.",
)
def analyze_code_endpoint(payload: AnalyzeCodeRequest) -> AnalyzeCodeResponse:
    """
    Validate request, automatically detect language using deterministic heuristics before Gemini,
    reuse cached analysis matching code fingerprint, and generate structured educational explanation.
    """
    # 1. Run Deterministic Hybrid Language Detection (Signal 1 & 2 without separate Gemini request)
    detection = detect_language(
        code=payload.code,
        filename=payload.filename,
    )

    # If an optional internal language was explicitly provided and code has some ambiguity,
    # honor the explicit supported language hint
    if not detection.language and payload.language and payload.language in SUPPORTED_LANGUAGES:
        detection.language = payload.language
        detection.confidence = "high"
        detection.is_ambiguous = False
        detection.is_unsupported = False

    # 2. Handle Unsupported Language deterministically (0 Gemini calls)
    if detection.is_unsupported:
        return AnalyzeCodeResponse(
            success=True,
            status="unsupported",
            message=UNSUPPORTED_LANGUAGE_MESSAGE,
        )

    # 3. Handle Ambiguous / Low-Confidence Snippet deterministically (0 Gemini calls)
    if detection.is_ambiguous or detection.confidence == "low" or not detection.language:
        return AnalyzeCodeResponse(
            success=True,
            status="ambiguous",
            confidence="low",
            message=AMBIGUOUS_SNIPPET_MESSAGE,
        )

    # 4. Fingerprint computation & Cache Lookup
    fingerprint = analysis_cache.compute_fingerprint(
        code=payload.code,
        language=detection.language,
        learning_level=payload.learning_level,
    )

    cached_resp = analysis_cache.get(fingerprint)
    if cached_resp is not None:
        logger.info(f"Reusing existing analysis for matching fingerprint {fingerprint[:12]} (0 Gemini calls).")
        return cached_resp

    # 5. Prevent duplicate concurrent submissions
    is_leader, in_flight_event = analysis_cache.acquire_in_flight(fingerprint)
    if not is_leader:
        if in_flight_event is not None:
            logger.info(f"Awaiting in-flight duplicate submission for fingerprint {fingerprint[:12]}...")
            in_flight_event.wait(timeout=45.0)
        try:
            completed_result = analysis_cache.get_in_flight_result(fingerprint)
            if completed_result is not None:
                logger.info(f"Reusing completed in-flight analysis for fingerprint {fingerprint[:12]} (0 duplicate Gemini calls).")
                return completed_result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"In-flight analysis leader failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to analyze the code right now. Please try again.",
            )

    try:
        # 6. Verify Gemini client configuration
        try:
            llm_service.get_gemini_client()
        except llm_service.LLMConfigurationError as e:
            logger.error(f"Configuration error: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(e),
            )

        # 7. Run Lightweight Static Code Analysis Engine
        static_result = None
        try:
            static_result = analyze_static(
                code=payload.code,
                language=detection.language,
            )
        except Exception as e:
            logger.exception(f"Static analysis failed unexpectedly: {e}")
            # Graceful degradation: continue with Gemini explanation

        # 8. Generate Structured Explanation
        try:
            analysis = analyze_code(
                code=payload.code,
                language=detection.language,
                learning_level=payload.learning_level,
                confidence=detection.confidence,
                static_analysis=static_result,
            )

            # Merge definite static issues into potential_issues if not already covered
            if static_result and static_result.issues:
                for s_issue in static_result.issues:
                    if s_issue.type == "definite":
                        desc_lower = s_issue.description.lower()
                        already_covered = any(
                            desc_lower in (p.description or "").lower() or (p.description or "").lower() in desc_lower
                            for p in analysis.potential_issues
                        )
                        if not already_covered:
                            analysis.potential_issues.append(
                                PotentialIssue(
                                    severity=s_issue.severity,
                                    description=s_issue.description,
                                )
                            )

            static_data = static_result.to_api_response() if static_result else None

            final_response = AnalyzeCodeResponse(
                success=True,
                status="success",
                detected_language=detection.language,
                confidence=detection.confidence,
                overall_purpose=analysis.overall_purpose,
                how_it_works=analysis.how_it_works,
                line_by_line=analysis.line_by_line,
                variables=analysis.variables,
                functions=analysis.functions,
                algorithm_logic=analysis.algorithm_logic,
                time_complexity=analysis.time_complexity,
                space_complexity=analysis.space_complexity,
                potential_issues=analysis.potential_issues,
                key_learning_points=analysis.key_learning_points,
                static_analysis=static_data,
                error=None,
            )

            # Cache completed analysis and notify any waiting concurrent requests
            analysis_cache.complete_in_flight(fingerprint, response=final_response)
            return final_response

        except llm_service.LLMConfigurationError as e:
            logger.error(f"Configuration error during analysis: {e}")
            err = HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(e),
            )
            analysis_cache.complete_in_flight(fingerprint, error=err)
            raise err

        except llm_service.LLMServiceError as e:
            logger.error(f"LLM service error during analysis: {e}")
            err = HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(e),
            )
            analysis_cache.complete_in_flight(fingerprint, error=err)
            raise err

        except Exception as e:
            logger.exception("Unexpected error while analyzing code")
            err = HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to analyze the code right now. Please try again.",
            )
            analysis_cache.complete_in_flight(fingerprint, error=err)
            raise err

    finally:
        if is_leader:
            analysis_cache.release_in_flight(fingerprint)
