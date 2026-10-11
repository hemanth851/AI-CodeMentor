from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator

MAX_CODE_SIZE_BYTES = 100 * 1024  # 100 KB

SUPPORTED_LANGUAGES = (
    "Python",
    "Java",
    "C",
    "C++",
    "JavaScript",
    "TypeScript",
    "C#",
    "Go",
    "Rust",
    "PHP",
    "Kotlin",
    "Swift",
    "SQL",
)

SUPPORTED_LEVELS = ("Beginner", "Intermediate", "Advanced")


class LineExplanation(BaseModel):
    """Explanation of an individual code line or statement."""
    line: int = Field(description="1-indexed line number")
    code: str = Field(description="The exact line or statement from submitted code")
    explanation: str = Field(description="Clear educational explanation of what this line does")


class VariableInfo(BaseModel):
    """Information about a variable identified in the code."""
    name: str = Field(description="Variable identifier name")
    purpose: str = Field(description="Role and purpose of this variable in the snippet")


class FunctionInfo(BaseModel):
    """Information about a function identified in the code."""
    name: str = Field(description="Function identifier name")
    parameters: List[str] = Field(default_factory=list, description="List of parameter names or types")
    purpose: str = Field(description="Summary of what the function performs")
    return_value: Optional[str] = Field(default="", description="Description of return value or type")


class PotentialIssue(BaseModel):
    """Definite bug, potential runtime problem, edge case, or suspicious code."""
    severity: str = Field(
        default="possible",
        description="Severity or type: 'definite', 'possible', 'low', 'medium', or 'high'",
    )
    description: str = Field(description="Explanation of the issue or edge case")


class CodeAnalysis(BaseModel):
    """Structured educational explanation payload."""
    overall_purpose: str = Field(description="High-level explanation of what the submitted code does")
    how_it_works: str = Field(description="Step-by-step walkthrough of the flow and execution")
    line_by_line: List[LineExplanation] = Field(default_factory=list, description="Line-by-line explanation of submitted lines")
    variables: List[VariableInfo] = Field(default_factory=list, description="Variables identified in the snippet")
    functions: List[FunctionInfo] = Field(default_factory=list, description="Functions identified in the snippet")
    algorithm_logic: str = Field(description="Algorithm or logical approach demonstrated in the snippet")
    time_complexity: str = Field(description="Time complexity estimate or explanation if not applicable")
    space_complexity: str = Field(description="Space complexity estimate or explanation if not applicable")
    potential_issues: List[PotentialIssue] = Field(default_factory=list, description="Potential issues, bugs, or edge cases")
    key_learning_points: List[str] = Field(default_factory=list, description="Core programming concepts demonstrated")


class AnalyzeCodeRequest(BaseModel):
    """Payload for code explanation requests."""
    code: str = Field(
        ...,
        description="Source code to analyze",
        min_length=1,
    )
    learning_level: str = Field(
        default="Beginner",
        description="Depth of explanation (Beginner, Intermediate, Advanced)",
    )
    language: Optional[str] = Field(
        default=None,
        description="Optional internal language hint or uploaded file metadata",
    )
    filename: Optional[str] = Field(
        default=None,
        description="Optional uploaded filename for extension detection",
    )

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Code must not be empty.")
        if len(v.encode("utf-8")) > MAX_CODE_SIZE_BYTES:
            raise ValueError("Code exceeds maximum permitted size of 100 KB.")
        return v

    @field_validator("learning_level")
    @classmethod
    def validate_learning_level(cls, v: str) -> str:
        for valid_level in SUPPORTED_LEVELS:
            if v.strip().lower() == valid_level.lower():
                return valid_level
        raise ValueError(
            f"Invalid learning level '{v}'. Must be one of: {', '.join(SUPPORTED_LEVELS)}"
        )

    @field_validator("language")
    @classmethod
    def validate_optional_language(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        stripped = v.strip()
        for valid_lang in SUPPORTED_LANGUAGES:
            if stripped.lower() == valid_lang.lower():
                return valid_lang
        # If user explicitly supplied an invalid language string
        raise ValueError(
            f"Unsupported language '{v}'. Must be one of: {', '.join(SUPPORTED_LANGUAGES)}"
        )


class StructureSummary(BaseModel):
    """Educational summary of code structure metrics."""
    variables: Optional[int] = Field(default=None, description="Number of variables identified")
    functions: Optional[int] = Field(default=None, description="Number of functions/methods identified")
    loops: Optional[int] = Field(default=None, description="Number of loops identified")
    conditionals: Optional[int] = Field(default=None, description="Number of conditional statements identified")
    recursion: Optional[bool] = Field(default=None, description="Whether recursive calls were detected")
    classes: Optional[int] = Field(default=None, description="Number of classes identified")
    imports: Optional[int] = Field(default=None, description="Number of imports/includes identified")


class ComplexityEvidence(BaseModel):
    """Deterministic structural evidence for time/space complexity."""
    loops: Optional[int] = Field(default=0, description="Total number of loops")
    nested_loops: Optional[bool] = Field(default=False, description="Whether nested loops were detected")
    recursion_detected: Optional[bool] = Field(default=False, description="Whether recursion was detected")
    sorting_detected: Optional[bool] = Field(default=False, description="Whether sorting calls were detected")
    searching_detected: Optional[bool] = Field(default=False, description="Whether searching calls were detected")
    sequential_loops: Optional[bool] = Field(default=False, description="Whether sequential loops were detected")


class StaticAnalysisData(BaseModel):
    """Structured static analysis payload returned to frontend and Gemini."""
    parse_status: str = Field(
        default="success",
        description="Static parsing status: 'success', 'partial', or 'unavailable'",
    )
    structure: Optional[StructureSummary] = Field(default=None, description="Identified structure counts")
    complexity_evidence: Optional[ComplexityEvidence] = Field(default=None, description="Complexity evidence")


class AnalyzeCodeResponse(BaseModel):
    """Response containing Gemini analysis, language detection, or error information."""
    success: bool = Field(default=True, description="Whether the request succeeded")
    status: str = Field(
        default="success",
        description="Outcome status: 'success', 'ambiguous', 'unsupported', or 'error'",
    )
    detected_language: Optional[str] = Field(
        default=None,
        description="Detected programming language among the 13 supported languages",
    )
    confidence: Optional[str] = Field(
        default=None,
        description="Confidence level: 'high', 'moderate', or 'low'",
    )
    message: Optional[str] = Field(
        default=None,
        description="Informative message (e.g. request for more code or unsupported notice)",
    )
    overall_purpose: Optional[str] = Field(default=None)
    how_it_works: Optional[str] = Field(default=None)
    line_by_line: List[LineExplanation] = Field(default_factory=list)
    variables: List[VariableInfo] = Field(default_factory=list)
    functions: List[FunctionInfo] = Field(default_factory=list)
    algorithm_logic: Optional[str] = Field(default=None)
    time_complexity: Optional[str] = Field(default=None)
    space_complexity: Optional[str] = Field(default=None)
    potential_issues: List[PotentialIssue] = Field(default_factory=list)
    key_learning_points: List[str] = Field(default_factory=list)
    static_analysis: Optional[StaticAnalysisData] = Field(
        default=None,
        description="Lightweight static code analysis summary and evidence",
    )
    error: Optional[str] = Field(default=None, description="User-safe error description if failed")

