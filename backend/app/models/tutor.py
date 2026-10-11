from typing import Optional, List, Literal, Any, Union, Dict
from pydantic import BaseModel, Field, field_validator
from app.models.analysis import (
    SUPPORTED_LANGUAGES,
    SUPPORTED_LEVELS,
    MAX_CODE_SIZE_BYTES,
    CodeAnalysis,
    StaticAnalysisData,
)

MAX_QUESTION_LENGTH = 2000
MAX_HISTORY_MESSAGES = 10


class TutorMessage(BaseModel):
    """Single message in the tutor conversation history."""
    role: Literal["user", "assistant", "tutor"] = Field(
        ...,
        description="Message role: 'user' for user questions, 'tutor' or 'assistant' for tutor answers",
    )
    content: str = Field(
        ...,
        description="Text content of the message",
        min_length=1,
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Message content must not be empty.")
        return stripped


class TutorRequest(BaseModel):
    """Payload for interactive AI tutor code questions."""
    code: str = Field(
        ...,
        description="Current source code being analyzed",
        min_length=1,
    )
    language: str = Field(
        ...,
        description="Programming language of the code",
    )
    learning_level: str = Field(
        default="Beginner",
        description="Educational depth (Beginner, Intermediate, Advanced)",
    )
    question: str = Field(
        ...,
        description="User question about the code",
        min_length=1,
    )
    static_analysis: Optional[Union[StaticAnalysisData, Dict[str, Any]]] = Field(
        default=None,
        description="Lightweight static analysis facts from the current session",
    )
    analysis: Optional[Union[CodeAnalysis, Dict[str, Any]]] = Field(
        default=None,
        description="Structured explanation from the current session",
    )
    history: List[TutorMessage] = Field(
        default_factory=list,
        description="Recent in-session conversation history (bounded to last 10 messages)",
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

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Question must not be empty.")
        if len(stripped) > MAX_QUESTION_LENGTH:
            raise ValueError(f"Question exceeds maximum permitted length of {MAX_QUESTION_LENGTH} characters.")
        return stripped

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
    def validate_language(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Language must not be empty.")
        for valid_lang in SUPPORTED_LANGUAGES:
            if stripped.lower() == valid_lang.lower():
                return valid_lang
        raise ValueError(
            f"Unsupported language '{v}'. Must be one of: {', '.join(SUPPORTED_LANGUAGES)}"
        )

    @field_validator("history")
    @classmethod
    def bound_history(cls, v: Optional[List[TutorMessage]]) -> List[TutorMessage]:
        if not v:
            return []
        # Strictly enforce bounded history to prevent context explosion
        return v[-MAX_HISTORY_MESSAGES:]


class TutorLLMResponse(BaseModel):
    """Schema for Gemini LLM structured output for AI Tutor."""
    answer: str = Field(description="Educational explanation answering the user's question, grounded strictly in the code")
    key_points: List[str] = Field(default_factory=list, description="1 to 3 concise key educational takeaway points or concepts")
    related_code: Optional[str] = Field(default=None, description="Short snippet of relevant code from the provided code if applicable, or null")
    grounded: bool = Field(default=True, description="True if the question is answerable from the code/context; False if the question asks about something not present or ungrounded")


class TutorResponse(BaseModel):
    """Structured response from the Interactive AI Tutor."""
    success: bool = Field(default=True, description="Whether the request succeeded")
    answer: str = Field(description="Educational explanation answering the user's question")
    key_points: List[str] = Field(default_factory=list, description="Key learning takeaways or core points")
    related_code: Optional[str] = Field(default=None, description="Short snippet of relevant code from the provided code")
    grounded: bool = Field(default=True, description="Whether the answer is grounded in the provided code")
    error: Optional[str] = Field(default=None, description="User-safe error description if failed")

