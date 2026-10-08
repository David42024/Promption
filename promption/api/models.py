"""Pydantic request/response schemas for the API."""
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


import json
from promption.utils.config import load_config


def get_limits() -> dict:
    return load_config().get("limits", {})


def _validate_text(text: str) -> str:
    max_len = int(get_limits().get("max_text_chars", 100000))
    if len(text) > max_len:
        raise ValueError(f"Text length exceeds limit of {max_len} characters")
    return text


def _validate_roles_list(roles: list[str]) -> list[str]:
    limits = get_limits()
    max_roles = int(limits.get("max_roles", 32))
    max_role_len = int(limits.get("max_role_name_chars", 64))
    if len(roles) > max_roles:
        raise ValueError(f"Exceeded maximum number of roles ({max_roles})")
    for r in roles:
        if not isinstance(r, str) or len(r) > max_role_len:
            raise ValueError(f"Role exceeds maximum length of {max_role_len} characters")
    return roles


def _validate_context_dict(ctx: dict) -> dict:
    limits = get_limits()
    max_keys = int(limits.get("max_context_keys", 64))
    max_bytes = int(limits.get("max_context_bytes", 65536))
    if len(ctx) > max_keys:
        raise ValueError(f"Context exceeds maximum number of keys ({max_keys})")
    try:
        serialized = json.dumps(ctx)
        if len(serialized.encode("utf-8")) > max_bytes:
            raise ValueError(f"Context serialized size exceeds {max_bytes} bytes")
    except (TypeError, ValueError) as err:
        if "exceeds" in str(err):
            raise
        raise ValueError(f"Context must be JSON serializable: {err}")
    return ctx


def _validate_user_id(user_id: str | None) -> str | None:
    if user_id is not None:
        max_user_id = int(get_limits().get("max_user_id_chars", 128))
        if len(user_id) > max_user_id:
            raise ValueError(f"user_id exceeds maximum length of {max_user_id} characters")
    return user_id


def _validate_messages_list(messages: list) -> list:
    max_msgs = int(get_limits().get("max_history_messages", 128))
    if len(messages) > max_msgs:
        raise ValueError(f"Exceeded maximum number of messages ({max_msgs})")
    return messages


class ConversationEvidence(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str = Field(...)
    tool_name: str | None = Field(default=None, max_length=128)

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        return _validate_text(v)


class FilterRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Prompt to analyze")
    use_ml: bool = True
    messages: list[ConversationEvidence] = Field(default_factory=list)
    user_id: str | None = Field(default=None, description="End-user id (audit + per-user policy)")
    roles: list[str] = Field(default_factory=list, description="End-user roles/scopes")
    context: dict = Field(default_factory=dict, description="Tenant-defined context (doc ACL, channel…)")

    @model_validator(mode="before")
    @classmethod
    def reject_threshold(cls, data: Any) -> Any:
        if isinstance(data, dict) and "threshold" in data:
            raise ValueError("The 'threshold' field is removed. Maintain effective thresholds per tenant.")
        return data

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        return _validate_text(v)

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: list) -> list:
        return _validate_messages_list(v)

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str | None) -> str | None:
        return _validate_user_id(v)

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: list[str]) -> list[str]:
        return _validate_roles_list(v)

    @field_validator("context")
    @classmethod
    def validate_context(cls, v: dict) -> dict:
        return _validate_context_dict(v)


class RuleMatch(BaseModel):
    name: str
    severity: str
    description: str = ""


class HeuristicInfo(BaseModel):
    blocked: bool
    score: float
    matched_rules: list[RuleMatch] = []


class MLInfo(BaseModel):
    available: bool
    blocked: bool | None = None
    probability: float | None = None
    threshold: float | None = None
    status: str | None = None
    error_code: str | None = None
    state: str | None = None


class FilterResponse(BaseModel):
    text: str
    decision: str
    blocked: bool
    confidence: float
    latency_ms: float
    reason: str = ""
    layers: dict
    sanitized: str
    tenant_id: str = "default"
    classification: Literal["MALICIOUS", "BENIGN", "UNCERTAIN"] = "UNCERTAIN"
    requires_review: bool = True
    requires_output_guard: bool = False


class BenchmarkRequest(BaseModel):
    sample_size: int | None = Field(default=None)
    use_llm: bool = True
    dataset: str | None = None

    @field_validator("sample_size")
    @classmethod
    def validate_sample_size(cls, v: int | None) -> int | None:
        if v is not None:
            max_size = int(get_limits().get("max_benchmark_sample_size", 5000))
            if v < 1 or v > max_size:
                raise ValueError(f"sample_size must be between 1 and {max_size}")
        return v


class OutputGuardRequest(BaseModel):
    text: str = Field(..., min_length=1, description="LLM response to inspect")
    user_id: str | None = Field(default=None)
    roles: list[str] = Field(default_factory=list, description="End-user roles/scopes")
    context: dict = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        return _validate_text(v)

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str | None) -> str | None:
        return _validate_user_id(v)

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: list[str]) -> list[str]:
        return _validate_roles_list(v)

    @field_validator("context")
    @classmethod
    def validate_context(cls, v: dict) -> dict:
        return _validate_context_dict(v)


class OutputGuardResponse(BaseModel):
    action: str
    risk: float
    categories: list[str] = []
    matches: int = 0
    redacted_response: str | None = None
    tenant_id: str = "default"


class AuditEventRequest(BaseModel):
    category: str = Field(..., min_length=1, max_length=64)
    event_type: str = Field(..., min_length=1, max_length=96)
    level: Literal["INFO", "WARNING", "ERROR"] = "INFO"
    message: str = Field(default="", max_length=240)
    user_id: str | None = Field(default=None)
    roles: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str | None) -> str | None:
        return _validate_user_id(v)

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: list[str]) -> list[str]:
        return _validate_roles_list(v)

    @field_validator("details")
    @classmethod
    def validate_details(cls, v: dict) -> dict:
        return _validate_context_dict(v)


class SystemInfo(BaseModel):
    service: str = "prompt-injection-filter"
    status: str
    version: str = "1.0.0"
    uptime_seconds: float
    memory_used_percent: float
    cpu_percent: float
    ollama: dict
    filter_layers: dict
    timestamp: str
