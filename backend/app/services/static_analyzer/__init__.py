import logging
from app.services.static_analyzer.models import (
    StaticAnalysisResult,
    StaticIssue,
    LoopAnalysis,
    ConditionalAnalysis,
    ComplexityEvidenceData,
)
from app.services.static_analyzer.python_analyzer import analyze_python
from app.services.static_analyzer.generic_analyzer import analyze_generic

logger = logging.getLogger(__name__)


def analyze_static(code: str, language: str) -> StaticAnalysisResult:
    """
    Perform lightweight, deterministic educational static code analysis.
    
    Routes Python to AST-based analysis and all other supported languages
    to deterministic structural analysis.
    
    Never raises an uncaught exception: falls back to parse_status="unavailable".
    """
    if not code or not code.strip():
        return StaticAnalysisResult(
            language=language or "Unknown",
            parse_status="unavailable",
        )

    clean_lang = (language or "").strip()

    try:
        if clean_lang.lower() == "python":
            return analyze_python(code)
        else:
            return analyze_generic(code, clean_lang)
    except Exception as e:
        logger.exception(f"Unexpected error in static code analysis for {clean_lang}: {e}")
        return StaticAnalysisResult(
            language=clean_lang,
            parse_status="unavailable",
            issues=[
                StaticIssue(
                    type="possible",
                    severity="low",
                    description="Static analysis engine encountered an unexpected error for this snippet.",
                )
            ],
        )
