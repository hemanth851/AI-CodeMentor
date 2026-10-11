from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator

MAX_CODE_SIZE_BYTES = 100 * 1024  # 100 KB


class TraceEvent(BaseModel):
    """Represents a single deterministic execution step in an algorithm trace."""
    step_number: int = Field(..., description="1-indexed step number")
    event_type: str = Field(
        ...,
        description="Event category: initialization, assignment, condition_true, condition_false, "
                    "loop_start, loop_iteration, function_call, return, output, completed, limit_exceeded",
    )
    line_number: Optional[int] = Field(
        default=None,
        description="1-indexed source code line number corresponding to this step",
    )
    description: str = Field(
        ...,
        description="Human-readable educational summary explaining this execution step",
    )
    variable_state: Dict[str, Any] = Field(
        default_factory=dict,
        description="Snapshot of all in-scope variables at this step",
    )
    list_state: Dict[str, List[Any]] = Field(
        default_factory=dict,
        description="Snapshot of all lists/arrays in scope for specialized rendering",
    )
    current_function: Optional[str] = Field(
        default=None,
        description="Name of currently executing function, or None for top-level code",
    )
    condition_result: Optional[bool] = Field(
        default=None,
        description="Result of conditional evaluation (True/False) if applicable",
    )
    loop_iteration: Optional[int] = Field(
        default=None,
        description="Current loop iteration count if inside a loop",
    )
    output: Optional[str] = Field(
        default=None,
        description="Cumulative printed console output up to this step",
    )


class VisualizeRequest(BaseModel):
    """Payload for requesting deterministic algorithm visualization."""
    code: str = Field(
        ...,
        description="Source code to execute and trace",
        min_length=1,
    )
    language: str = Field(
        default="Python",
        description="Programming language of the code (Python supported in Step 7A)",
    )

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Code must not be empty.")
        if len(v.encode("utf-8")) > MAX_CODE_SIZE_BYTES:
            raise ValueError(f"Code exceeds maximum permitted size of {MAX_CODE_SIZE_BYTES // 1024} KB.")
        return v


class VisualizeResponse(BaseModel):
    """Structured response containing deterministic execution trace or rejection details."""
    status: str = Field(
        ...,
        description="Execution status: 'success', 'unsupported', or 'error'",
    )
    supported: bool = Field(
        ...,
        description="True if the code language and constructs are within supported scope",
    )
    trace: List[TraceEvent] = Field(
        default_factory=list,
        description="Sequential list of execution trace events",
    )
    total_steps: int = Field(
        default=0,
        description="Total number of execution steps captured",
    )
    final_state: Dict[str, Any] = Field(
        default_factory=dict,
        description="Final variable state after execution completes or terminates",
    )
    termination_reason: str = Field(
        ...,
        description="Reason execution finished: completed, step_limit_exceeded, loop_limit_exceeded, "
                    "recursion_limit_exceeded, time_limit_exceeded, unsupported_construct, "
                    "unsupported_language, syntax_error, runtime_error",
    )
    error: Optional[str] = Field(
        default=None,
        description="User-friendly explanation if code was unsupported or failed",
    )
