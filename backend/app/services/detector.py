import os
import re
import logging
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any
from app.models.analysis import SUPPORTED_LANGUAGES
from app.services.llm_service import execute_with_retry_and_fallback, sanitize_sensitive_data

logger = logging.getLogger(__name__)

# File extension to language mapping (Signal 1)
EXTENSION_TO_LANGUAGE = {
    ".py": "Python",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".cs": "C#",
    ".go": "Go",
    ".rs": "Rust",
    ".php": "PHP",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".swift": "Swift",
    ".sql": "SQL",
}

UNSUPPORTED_EXTENSIONS = {
    ".rb": "Ruby",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".sh": "Bash",
    ".bash": "Bash",
    ".pl": "Perl",
    ".lua": "Lua",
    ".hs": "Haskell",
    ".r": "R",
    ".m": "Objective-C",
    ".dart": "Dart",
    ".scala": "Scala",
}


@dataclass
class DetectionResult:
    language: Optional[str] = None
    confidence: str = "low"  # "high", "moderate", "low"
    is_ambiguous: bool = False
    is_unsupported: bool = False
    unsupported_language: Optional[str] = None
    source: str = "none"  # "extension", "local_heuristics", "gemini"


def detect_by_extension(filename: str) -> Optional[DetectionResult]:
    """Signal 1: Detect programming language or unsupported status from uploaded file extension."""
    if not filename:
        return None

    _, ext = os.path.splitext(filename.strip().lower())
    if not ext:
        return None

    if ext in EXTENSION_TO_LANGUAGE:
        return DetectionResult(
            language=EXTENSION_TO_LANGUAGE[ext],
            confidence="high",
            source="extension",
        )

    if ext in UNSUPPORTED_EXTENSIONS:
        return DetectionResult(
            is_unsupported=True,
            unsupported_language=UNSUPPORTED_EXTENSIONS[ext],
            confidence="high",
            source="extension",
        )

    return None


def is_clearly_unsupported(code: str) -> Optional[str]:
    """Check for distinctive signatures of languages not in the 13 supported languages."""
    stripped = code.strip()

    # HTML
    if re.search(r"<!DOCTYPE\s+html|<html[\s>]|</html|<body[\s>]|</body|<div[\s>]|</div|<p[\s>]|</p", stripped, re.IGNORECASE):
        return "HTML"

    # Ruby (e.g. def foo ... end, puts, attr_accessor)
    if (re.search(r"\bdef\s+[a-zA-Z_]\w*(\s*\(.*?\))?\s*\n[\s\S]*?\bend\b", stripped) and
        not re.search(r"[\{\}:;]", stripped)) or re.search(r"\bputs\s+[\"']", stripped):
        return "Ruby"

    # CSS (e.g. selector { property: value; })
    if re.search(r"[.#]?[a-zA-Z0-9_-]+\s*\{[\s\S]*?(?:display|margin|padding|border|color|background)\s*:", stripped):
        return "CSS"

    # Shell / Bash
    if re.match(r"^#!\s*/bin/(?:bash|sh)", stripped) or re.search(r"\b(?:fi|esac)\b", stripped):
        return "Bash"

    return None


def is_very_short_ambiguous(code: str) -> bool:
    """
    Check if a snippet is too short or ambiguous to identify the language with confidence.
    Examples: 'x = 10', 'a = b', 'foo()', 'i = 0'.
    """
    lines = [line.strip() for line in code.strip().splitlines() if line.strip() and not line.strip().startswith(("#", "//", "--"))]
    if not lines:
        return True

    # Single-line checks
    if len(lines) == 1:
        line = lines[0]
        # Simple variable assignment: identifier = literal/identifier (without types, semicolons, or keywords)
        if re.match(r"^[a-zA-Z_]\w*\s*=\s*(?:-?\d+(?:\.\d+)?|['\"].*?['\"]|[a-zA-Z_]\w*)$", line):
            return True
        # Simple arithmetic/expression: x + y, 10 > 5
        if re.match(r"^[a-zA-Z_]\w*\s*[\+\-\*/%]\s*[a-zA-Z_0-9]+$", line):
            return True
        # Simple generic function call: foo(), print(x) without distinctive context
        if re.match(r"^[a-zA-Z_]\w*\s*\([a-zA-Z_0-9,\s\"']*\)$", line) and not any(kw in line for kw in ("printf", "println!", "System.out", "Console.Write", "fmt.Print")):
            return True

    return False


def score_supported_languages(code: str) -> Dict[str, float]:
    """
    Signal 2: Analyze source code for distinctive syntax characteristics across the 13 supported languages.
    Returns weighted score for each language.
    """
    scores = {lang: 0.0 for lang in SUPPORTED_LANGUAGES}
    stripped = code.strip()
    lines = stripped.splitlines()

    has_semicolons = sum(1 for line in lines if line.strip().endswith(";"))
    has_braces = "{" in stripped and "}" in stripped

    # --- 1. SQL ---
    sql_patterns = [
        (r"\bSELECT\b[\s\S]+\bFROM\b", 12.0),
        (r"\bINSERT\s+INTO\b", 10.0),
        (r"\bUPDATE\b\s+\w+\s+\bSET\b", 10.0),
        (r"\bDELETE\s+FROM\b", 10.0),
        (r"\bCREATE\s+TABLE\b", 10.0),
        (r"\bDROP\s+TABLE\b", 8.0),
        (r"\bWHERE\b", 3.0),
        (r"\bGROUP\s+BY\b", 5.0),
        (r"\bORDER\s+BY\b", 5.0),
        (r"\b(?:INNER|LEFT|RIGHT|FULL)?\s*JOIN\b", 6.0),
        (r"--\s.*", 2.0),
    ]
    for pattern, weight in sql_patterns:
        if re.search(pattern, stripped, re.IGNORECASE):
            scores["SQL"] += weight

    # --- 2. Go ---
    go_patterns = [
        (r"^package\s+\w+", 10.0),
        (r'\bimport\s+(?:\(\s*".*?"|"[^"]+")', 8.0),
        (r"\bfunc\s+(?:\([^)]+\)\s*)?[a-zA-Z_]\w*\s*\(", 8.0),
        (r"\bfmt\.(?:Println|Printf|Sprintf|Print)\b", 10.0),
        (r":=", 7.0),
        (r"\bdefer\b", 6.0),
        (r"\bgo\s+func\b", 8.0),
        (r"\bchan\b", 6.0),
        (r"\btype\s+\w+\s+struct\s*\{", 8.0),
        (r"\bnil\b", 2.0),
    ]
    for pattern, weight in go_patterns:
        if re.search(pattern, stripped):
            scores["Go"] += weight

    # --- 3. Rust ---
    rust_patterns = [
        (r"\bfn\s+[a-zA-Z_]\w*\s*\(", 7.0),
        (r"\blet\s+mut\s+", 9.0),
        (r"\b(?:println|eprintln|format|vec)!", 10.0),
        (r"\bimpl\s+(?:\w+\s+for\s+)?\w+", 8.0),
        (r"\bpub\s+fn\b", 7.0),
        (r"\bmatch\s+\w+\s*\{", 6.0),
        (r"\buse\s+std::", 8.0),
        (r"->\s*(?:Result|Option|i32|u32|usize|bool|String|&str)\b", 7.0),
        (r"\bunwrap\(\)", 6.0),
        (r"&mut\s+", 6.0),
    ]
    for pattern, weight in rust_patterns:
        if re.search(pattern, stripped):
            scores["Rust"] += weight

    # --- 4. Python ---
    py_patterns = [
        (r"^\s*def\s+[a-zA-Z_]\w*\s*\(.*?\)\s*:", 9.0),
        (r"^\s*class\s+[a-zA-Z_]\w*(?:\(.*?\))?\s*:", 7.0),
        (r"^\s*elif\s+.*?:", 7.0),
        (r"^\s*for\s+[a-zA-Z_]\w*\s+in\s+.*?:", 7.0),
        (r"^\s*if\s+.*?:", 4.0),
        (r"^\s*while\s+.*?:", 4.0),
        (r"^\s*try\s*:", 5.0),
        (r"^\s*except(?:\s+.*?)?:", 7.0),
        (r"\bself\.[a-zA-Z_]\w*", 6.0),
        (r"\b__init__\b", 8.0),
        (r"\bprint\s*\(", 3.0),
        (r"\bin\s+range\s*\(", 8.0),
        (r"^\s*from\s+[a-zA-Z_]\w*\s+import\s+", 8.0),
        (r"^\s*import\s+[a-zA-Z_]\w*", 4.0),
        (r"\bNone\b", 3.0),
        (r"\bTrue\b|\bFalse\b", 2.0),
        (r"\blambda\b", 4.0),
    ]
    for pattern, weight in py_patterns:
        if re.search(pattern, stripped, re.MULTILINE):
            scores["Python"] += weight
    if not has_braces and not has_semicolons and scores["Python"] > 0:
        scores["Python"] += 3.0

    # --- 5. PHP ---
    php_patterns = [
        (r"<\?php", 15.0),
        (r"\$[a-zA-Z_\x7f-\xff][a-zA-Z0-9_\x7f-\xff]*", 7.0),
        (r"\becho\s+", 5.0),
        (r"\bprint_r\s*\(|\bvar_dump\s*\(", 8.0),
        (r"->", 2.0),
        (r"\bfunction\s+[a-zA-Z_]\w*\s*\(", 3.0),
    ]
    for pattern, weight in php_patterns:
        if re.search(pattern, stripped):
            scores["PHP"] += weight

    # --- 6. Kotlin ---
    kt_patterns = [
        (r"\bfun\s+[a-zA-Z_]\w*\s*\(", 8.0),
        (r"\bval\s+[a-zA-Z_]\w*", 5.0),
        (r"\bvar\s+[a-zA-Z_]\w*", 2.0),
        (r"\bprintln\s*\(", 4.0),
        (r"\bdata\s+class\s+\w+", 10.0),
        (r"\bwhen\s*[\(\{]", 8.0),
        (r"\bcompanion\s+object\b", 10.0),
        (r":\s*(?:String|Int|Double|Boolean|List<|Map<)\b", 4.0),
    ]
    for pattern, weight in kt_patterns:
        if re.search(pattern, stripped):
            scores["Kotlin"] += weight

    # --- 7. Swift ---
    swift_patterns = [
        (r"\bimport\s+(?:Foundation|UIKit|SwiftUI)", 10.0),
        (r"\bfunc\s+[a-zA-Z_]\w*\s*\(", 6.0),
        (r"\bguard\s+let\b", 10.0),
        (r"\bif\s+let\b", 6.0),
        (r"\blet\s+[a-zA-Z_]\w*", 3.0),
        (r"\bvar\s+[a-zA-Z_]\w*", 2.0),
        (r"\bmutating\s+func\b", 10.0),
        (r"->\s*(?:Void|String|Int|Double|Bool)\b", 5.0),
        (r"\bprint\s*\(", 2.0),
    ]
    for pattern, weight in swift_patterns:
        if re.search(pattern, stripped):
            scores["Swift"] += weight

    # --- 8. Java ---
    java_patterns = [
        (r"\bpublic\s+class\s+\w+", 9.0),
        (r"\bclass\s+\w+\s*\{[\s\S]*?\b(?:public|private|protected)\b", 8.0),
        (r"\bpublic\s+static\s+void\s+main\b", 12.0),
        (r"\bSystem\.(?:out|err)\.(?:println|print|printf)\b", 10.0),
        (r"\bString\[\]\s+args\b", 8.0),
        (r"\bimport\s+java\.[a-zA-Z0-9_.*]+\s*;", 10.0),
        (r"\bpackage\s+[a-zA-Z0-9_.]+\s*;", 8.0),
        (r"\b(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?(?:void|int|double|float|boolean|String|long|char|[A-Z]\w*(?:<.*?>)?(?:\[\])?)\s+[a-zA-Z_]\w*\s*\(", 9.0),
        (r"\bextends\s+\w+|\bimplements\s+\w+", 6.0),
        (r"@Override\b|@Test\b|@Nullable\b|@NonNull\b", 6.0),
        (r"\bnew\s+(?:ArrayList|HashMap|HashSet|LinkedList|Scanner|StringBuilder|Random)<*.*?>*\(", 8.0),
        (r"\bthrows\s+(?:Exception|[A-Z]\w*Exception)\b", 8.0),
        (r"\bcatch\s*\(\s*(?:Exception|[A-Z]\w*Exception)\s+\w+\s*\)", 7.0),
        (r"\bboolean\b|\bint\b|\bdouble\b|\bfloat\b|\bString\b", 2.0),
    ]
    for pattern, weight in java_patterns:
        if re.search(pattern, stripped):
            scores["Java"] += weight

    # --- 9. C# ---
    cs_patterns = [
        (r"\busing\s+System(?:\.[a-zA-Z0-9_]+)?\s*;", 10.0),
        (r"\bnamespace\s+[a-zA-Z0-9_.]+", 7.0),
        (r"\bConsole\.(?:WriteLine|Write|ReadLine)\b", 10.0),
        (r"\bstatic\s+void\s+Main\b", 10.0),
        (r"\bstring\[\]\s+args\b", 7.0),
        (r"\{\s*get;\s*set;\s*\}", 8.0),
        (r"\bnameof\s*\(", 6.0),
        (r"\basync\s+Task\b", 6.0),
    ]
    for pattern, weight in cs_patterns:
        if re.search(pattern, stripped):
            scores["C#"] += weight

    # --- 10. C++ ---
    cpp_patterns = [
        (r"#include\s*<iostream>|#include\s*<vector>|#include\s*<string>|#include\s*<algorithm>", 10.0),
        (r"\bstd::(?:cout|cin|endl|vector|string|map|set)\b", 10.0),
        (r"\bcout\s*<<|\bcin\s*>>", 8.0),
        (r"\busing\s+namespace\s+std\s*;", 8.0),
        (r"\btemplate\s*<\s*(?:typename|class)\s+", 8.0),
        (r"\bnullptr\b", 5.0),
        (r"\bclass\s+\w+\s*\{[\s\S]*?(?:public|private|protected)\s*:", 7.0),
    ]
    for pattern, weight in cpp_patterns:
        if re.search(pattern, stripped):
            scores["C++"] += weight

    # --- 11. C ---
    c_patterns = [
        (r"#include\s*<stdio\.h>|#include\s*<stdlib\.h>|#include\s*<string\.h>", 10.0),
        (r"\bprintf\s*\(", 8.0),
        (r"\bscanf\s*\(", 8.0),
        (r"\bmalloc\s*\(|\bfree\s*\(", 7.0),
        (r"\bsizeof\s*\(", 5.0),
        (r"\bint\s+main\s*\(\s*(?:void)?\s*\)", 6.0),
        (r"\bstruct\s+\w+\s*\{", 4.0),
    ]
    for pattern, weight in c_patterns:
        if re.search(pattern, stripped):
            scores["C"] += weight
    # If C++ markers exist, penalize C
    if scores["C++"] > 5.0:
        scores["C"] = 0.0

    # --- 12. JavaScript & 13. TypeScript ---
    ts_specific_patterns = [
        (r"\binterface\s+\w+\s*\{", 9.0),
        (r"\btype\s+\w+\s*=", 8.0),
        (r":\s*(?:string|number|boolean|any|void|unknown|never)\b", 7.0),
        (r":\s*(?:Array<|Promise<)", 7.0),
        (r"\bas\s+(?:string|number|boolean|any|const)\b", 6.0),
        (r"\benum\s+\w+\s*\{", 7.0),
        (r"\breadonly\s+", 5.0),
    ]
    for pattern, weight in ts_specific_patterns:
        if re.search(pattern, stripped):
            scores["TypeScript"] += weight

    js_patterns = [
        (r"\bconsole\.(?:log|error|warn|info)\b", 8.0),
        (r"\bconst\s+[a-zA-Z_]\w*\s*=", 4.0),
        (r"\blet\s+[a-zA-Z_]\w*\s*=", 3.0),
        (r"\bvar\s+[a-zA-Z_]\w*\s*=", 3.0),
        (r"=>", 3.0),
        (r"===|!==", 4.0),
        (r"\bfunction\s+[a-zA-Z_]\w*\s*\(", 4.0),
        (r"\bdocument\.\w+|\bwindow\.\w+", 7.0),
        (r"\brequire\s*\(|\bmodule\.exports\b", 7.0),
        (r"\bexport\s+default\b|\bexport\s+const\b", 6.0),
        (r"\basync\s+function\b|\bawait\s+", 4.0),
    ]
    for pattern, weight in js_patterns:
        if re.search(pattern, stripped):
            scores["JavaScript"] += weight
            scores["TypeScript"] += weight * 0.7  # TS also matches JS patterns

    return scores


def detect_by_heuristics(code: str) -> DetectionResult:
    """Signal 2: Analyze code snippet characteristics and return detection result with confidence."""
    # Check unsupported language first
    unsupported = is_clearly_unsupported(code)
    if unsupported:
        return DetectionResult(
            is_unsupported=True,
            unsupported_language=unsupported,
            confidence="high",
            source="local_heuristics",
        )

    # Check ambiguous / too short
    if is_very_short_ambiguous(code):
        return DetectionResult(
            is_ambiguous=True,
            confidence="low",
            source="local_heuristics",
        )

    # Score against 13 languages
    scores = score_supported_languages(code)
    sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_lang, top_score = sorted_scores[0]
    runner_up_lang, runner_up_score = sorted_scores[1]

    # Threshold evaluation
    if top_score >= 7.0 and (top_score - runner_up_score >= 3.0 or top_score >= 10.0):
        return DetectionResult(
            language=top_lang,
            confidence="high",
            source="local_heuristics",
        )

    if top_score >= 4.0:
        return DetectionResult(
            language=top_lang,
            confidence="moderate",
            source="local_heuristics",
        )

    return DetectionResult(
        is_ambiguous=True,
        confidence="low",
        source="local_heuristics",
    )


def detect_language_with_gemini(code: str, client: Any) -> DetectionResult:
    """
    Signal 3: Gemini fallback when local heuristics cannot confidently determine language.
    Strictly restricted to the 13 supported languages.
    """
    from google.genai import types
    from pydantic import BaseModel, Field

    class DetectionPayload(BaseModel):
        detected_language: Optional[str] = Field(
            default=None,
            description="One of: Python, Java, C, C++, JavaScript, TypeScript, C#, Go, Rust, PHP, Kotlin, Swift, SQL. Null if ambiguous or unsupported.",
        )
        confidence: str = Field(
            description="'high', 'moderate', or 'low'",
        )
        is_ambiguous: bool = Field(
            default=False,
            description="True if the snippet is too short, ambiguous, or lacks distinctive syntax to determine the language (e.g. 'x = 10', 'a = b', 'foo()').",
        )
        is_unsupported: bool = Field(
            default=False,
            description="True if the code snippet clearly belongs to a programming language outside the 13 supported languages.",
        )
        unsupported_language: Optional[str] = Field(
            default=None,
            description="Name of the unsupported language if is_unsupported is true.",
        )

    model_name = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()

    prompt = (
        "You are an expert programming language identification system for AI CodeMentor.\n"
        "AI CodeMentor officially supports ONLY these 13 programming languages:\n"
        "1. Python\n"
        "2. Java\n"
        "3. C\n"
        "4. C++\n"
        "5. JavaScript\n"
        "6. TypeScript\n"
        "7. C#\n"
        "8. Go\n"
        "9. Rust\n"
        "10. PHP\n"
        "11. Kotlin\n"
        "12. Swift\n"
        "13. SQL\n\n"
        "Rules:\n"
        "- Analyze the entire submitted code snippet, considering syntax, structure, keywords, and style.\n"
        "- If the snippet clearly belongs to a language outside the 13 supported languages (e.g. Ruby, HTML, CSS, Bash, Perl, Lua, Haskell), set is_unsupported=true and name the language.\n"
        "- If the snippet is too short or ambiguous to identify the language confidently (e.g. 'x = 10', 'a = b + c', 'foo()', 'y = 5'), set confidence='low' and is_ambiguous=true. Avoid guessing!\n"
        "- Otherwise, identify the most likely supported language from the 13 languages. Set confidence to 'high' (if distinctive) or 'moderate' (if plausible but partial).\n\n"
        f"Submitted code:\n```\n{code}\n```"
    )

    try:
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DetectionPayload,
            temperature=0.0,
        )
        response = execute_with_retry_and_fallback(
            client=client,
            contents=prompt,
            config=config,
            primary_model=model_name,
            default_msg="Language detection failed.",
        )

        payload = DetectionPayload.model_validate_json(response.text.strip())

        if payload.is_unsupported:
            return DetectionResult(
                is_unsupported=True,
                unsupported_language=payload.unsupported_language,
                confidence="high",
                source="gemini",
            )

        if payload.is_ambiguous or payload.confidence.lower() == "low" or not payload.detected_language:
            return DetectionResult(
                is_ambiguous=True,
                confidence="low",
                source="gemini",
            )

        # Ensure detected language is normalized to supported list
        matched_lang = None
        for lang in SUPPORTED_LANGUAGES:
            if payload.detected_language.strip().lower() == lang.lower():
                matched_lang = lang
                break

        if not matched_lang:
            return DetectionResult(
                is_unsupported=True,
                unsupported_language=payload.detected_language,
                confidence="high",
                source="gemini",
            )

        norm_confidence = payload.confidence.lower()
        if norm_confidence not in ("high", "moderate"):
            norm_confidence = "moderate"

        return DetectionResult(
            language=matched_lang,
            confidence=norm_confidence,
            source="gemini",
        )

    except Exception as e:
        logger.warning(f"Gemini language detection fallback encountered error: {e}")
        # If Gemini fallback fails, return low confidence / ambiguous safely
        return DetectionResult(
            is_ambiguous=True,
            confidence="low",
            source="gemini_error",
        )


def detect_language(
    code: str,
    filename: Optional[str] = None,
    gemini_client: Optional[Any] = None,
) -> DetectionResult:
    """
    Hybrid 3-signal language detector:
    1. Signal 1 — Uploaded file extension
    2. Signal 2 — Source-code multi-feature analysis
    3. Signal 3 — Gemini fallback for ambiguous / moderate-confidence snippets
    """
    # Signal 1: Uploaded file extension
    if filename:
        ext_result = detect_by_extension(filename)
        if ext_result:
            return ext_result

    # Signal 2: Source-code multi-feature analysis (deterministic heuristics)
    local_result = detect_by_heuristics(code)

    # Return immediately when code syntax is sufficiently distinctive (high or moderate),
    # clearly unsupported, or confirmed ambiguous
    if (
        local_result.confidence in ("high", "moderate")
        or local_result.is_unsupported
        or local_result.is_ambiguous
        or not gemini_client
    ):
        return local_result

    # Signal 3: Gemini fallback strictly as last resort only for unclassified code
    try:
        gemini_result = detect_language_with_gemini(code, gemini_client)
        if gemini_result.language or gemini_result.is_unsupported:
            return gemini_result
        if gemini_result.is_ambiguous:
            return gemini_result
    except Exception as e:
        logger.warning(f"Signal 3 Gemini fallback failed: {e}")

    return local_result
