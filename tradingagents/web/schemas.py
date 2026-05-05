from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

_ALLOWED_ANALYSTS = {"market", "social", "news", "fundamentals"}
_ALLOWED_DECISIONS = {"BUY", "HOLD", "SELL"}


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value:
            raise ValueError("email must contain @")
        return value


class LoginRequest(UserCreate):
    pass


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: dict[str, Any]


class AnalysisCreate(BaseModel):
    workspace_id: int | None = None
    ticker: str = Field(min_length=1, max_length=32)
    analysis_date: date
    analysts: list[str] = Field(min_length=1)
    research_depth: int = Field(default=1, ge=1, le=10)
    llm_provider: str = Field(default="openai", min_length=1, max_length=64)
    backend_url: str | None = Field(default=None, max_length=512)
    quick_model: str = Field(default="gpt-5.4-mini", min_length=1, max_length=128)
    deep_model: str = Field(default="gpt-5.5", min_length=1, max_length=128)
    output_language: str = Field(default="English", min_length=1, max_length=64)
    google_thinking_level: str | None = None
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    memory_ids: list[int] = Field(default_factory=list)
    memory_context: str | None = Field(default=None, exclude=True)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        value = value.strip().upper()
        if not value or "/" in value or "\\" in value or ".." in value:
            raise ValueError("ticker must be a safe symbol, not a path")
        return value

    @field_validator("analysts")
    @classmethod
    def validate_analysts(cls, value: list[str]) -> list[str]:
        normalized = []
        for analyst in value:
            item = analyst.strip().lower()
            if item not in _ALLOWED_ANALYSTS:
                raise ValueError(f"invalid analyst: {analyst}")
            if item not in normalized:
                normalized.append(item)
        if not normalized:
            raise ValueError("at least one analyst is required")
        return normalized

    def parameter_payload(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "ticker": self.ticker,
            "analysis_date": self.analysis_date.isoformat(),
            "analysts": self.analysts,
            "research_depth": self.research_depth,
            "llm_provider": self.llm_provider,
            "backend_url": self.backend_url,
            "quick_model": self.quick_model,
            "deep_model": self.deep_model,
            "output_language": self.output_language,
            "google_thinking_level": self.google_thinking_level,
            "openai_reasoning_effort": self.openai_reasoning_effort,
            "anthropic_effort": self.anthropic_effort,
            "memory_ids": self.memory_ids,
        }


class AnalysisRerun(BaseModel):
    workspace_id: int | None = None
    ticker: str | None = None
    analysis_date: date | None = None
    analysts: list[str] | None = None
    research_depth: int | None = Field(default=None, ge=1, le=10)
    llm_provider: str | None = None
    backend_url: str | None = None
    quick_model: str | None = None
    deep_model: str | None = None
    output_language: str | None = None
    memory_ids: list[int] | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_optional_ticker(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return AnalysisCreate.normalize_ticker(value)

    @field_validator("analysts")
    @classmethod
    def validate_optional_analysts(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        return AnalysisCreate.validate_analysts(value)


class ScheduledAnalysisCreate(BaseModel):
    workspace_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    ticker: str = Field(min_length=1, max_length=32)
    start_at: datetime
    interval: Literal["daily", "weekly", "monthly"]
    analysts: list[str] = Field(min_length=1)
    research_depth: int = Field(default=1, ge=1, le=10)
    llm_provider: str = Field(default="openai", min_length=1, max_length=64)
    backend_url: str | None = Field(default=None, max_length=512)
    quick_model: str = Field(default="gpt-5.4-mini", min_length=1, max_length=128)
    deep_model: str = Field(default="gpt-5.5", min_length=1, max_length=128)
    output_language: str = Field(default="English", min_length=1, max_length=64)
    analysis_date: date | None = None
    analysis_date_policy: Literal["run_date", "fixed"] = "run_date"
    google_thinking_level: str | None = None
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    memory_ids: list[int] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return AnalysisCreate.normalize_ticker(value)

    @field_validator("analysts")
    @classmethod
    def validate_analysts(cls, value: list[str]) -> list[str]:
        return AnalysisCreate.validate_analysts(value)


class ScheduledAnalysisUpdate(BaseModel):
    workspace_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    ticker: str | None = Field(default=None, min_length=1, max_length=32)
    start_at: datetime | None = None
    interval: Literal["daily", "weekly", "monthly"] | None = None
    analysts: list[str] | None = None
    research_depth: int | None = Field(default=None, ge=1, le=10)
    llm_provider: str | None = Field(default=None, min_length=1, max_length=64)
    backend_url: str | None = Field(default=None, max_length=512)
    quick_model: str | None = Field(default=None, min_length=1, max_length=128)
    deep_model: str | None = Field(default=None, min_length=1, max_length=128)
    output_language: str | None = Field(default=None, min_length=1, max_length=64)
    analysis_date: date | None = None
    analysis_date_policy: Literal["run_date", "fixed"] | None = None
    memory_ids: list[int] | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_optional_ticker(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return AnalysisCreate.normalize_ticker(value)

    @field_validator("analysts")
    @classmethod
    def validate_optional_analysts(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        return AnalysisCreate.validate_analysts(value)


class RunDueRequest(BaseModel):
    now: datetime | None = None


class InterventionCreate(BaseModel):
    source_analysis_task_id: int
    target_agent_name: str = Field(min_length=1, max_length=120)
    workspace_id: int | None = None


class InterventionMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class MemoryUpdate(BaseModel):
    tags: dict[str, Any] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)


WorkspaceRole = Literal["owner", "admin", "member", "viewer"]


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceMemberCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: WorkspaceRole

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return UserCreate.normalize_email(value)


class WorkspaceMemberUpdate(BaseModel):
    role: WorkspaceRole


class EventPayload(BaseModel):
    agent: str
    event_type: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class RunnerResult(BaseModel):
    report_sections: dict[str, str]
    final_decision: dict[str, Any]
