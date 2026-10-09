"""Pydantic models for Chat Service"""
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator
from promption.api.models import (
    ConversationEvidence,
    _validate_context_dict,
    _validate_messages_list,
    _validate_roles_list,
    _validate_text,
    _validate_user_id,
)


class UserRole(str, Enum):
    """User roles"""
    ADMIN = "admin"
    VENTAS = "ventas"
    CUSTOMER = "customer"
    GUEST = "guest"


class User(BaseModel):
    """User information"""
    id: str = Field(...)
    name: str = Field(...)
    email: str = Field(...)
    roles: List[UserRole] = Field(...)
    avatar: Optional[str] = None
    puesto: Optional[str] = None
    authenticated: bool = True

    @field_validator("id", "name", "email")
    @classmethod
    def validate_user_strings(cls, v: str) -> str:
        return _validate_user_id(v)

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: list) -> list:
        return _validate_roles_list(v)


class ChatRequest(BaseModel):
    """Chat request from frontend"""
    text: str = Field(..., min_length=1)
    user: User
    context: Optional[Dict[str, Any]] = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        return _validate_text(v)

    @field_validator("context")
    @classmethod
    def validate_context(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is not None:
            return _validate_context_dict(v)
        return v


class ConversationHistoryRequest(BaseModel):
    conversation_id: str = Field(...)
    user: User

    @field_validator("conversation_id")
    @classmethod
    def validate_conv_id(cls, v: str) -> str:
        return _validate_user_id(v)


class AIGuardRequest(BaseModel):
    text: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    roles: List[UserRole] = Field(...)
    direction: Literal["input", "output"]
    messages: List[ConversationEvidence] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        return _validate_text(v)

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        return _validate_user_id(v)

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: list) -> list:
        return _validate_roles_list(v)

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: list) -> list:
        return _validate_messages_list(v)


class ScopeCheckRequest(BaseModel):
    text: str = Field(..., min_length=1)
    user: User
    messages: List[ConversationEvidence] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        return _validate_text(v)

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: list) -> list:
        return _validate_messages_list(v)


class SecurityStateUpdate(BaseModel):
    action: Literal["filter", "output_guard", "reset"]
    enabled: Optional[bool] = None
    updated_by: str = Field(default="admin", max_length=128)


class FilterResponse(BaseModel):
    """Response from Filter API"""
    decision: str
    blocked: bool
    confidence: float
    reason: Optional[str] = None
    layers: Optional[Dict[str, Any]] = None
    sanitized: Optional[str] = None
    text: Optional[str] = None  # Campo adicional del Filter API
    tenant_id: Optional[str] = None  # Campo adicional del Filter API
    latency_ms: Optional[float] = None  # Campo adicional del Filter API
    classification: Literal["MALICIOUS", "BENIGN", "UNCERTAIN"] = "UNCERTAIN"
    requires_review: bool = True


class LLMResponse(BaseModel):
    """Response from LLM"""
    text: str
    model: str
    latency_ms: float
    ok: bool = True
    requested_model: Optional[str] = None
    fallback_count: int = 0
    fallback_reason: Optional[str] = None
    truncated: bool = False
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    provider_calls: Optional[int] = None
    generation_calls: Optional[int] = None
    scope_calls: Optional[int] = None
    failed_calls: int = 0
    known_usage: Optional[Dict[str, Optional[int]]] = None
    usage_coverage: Optional[Dict[str, Any]] = None
    usage_events: Optional[List[Dict[str, Any]]] = None


class MCPToolCall(BaseModel):
    """MCP tool execution result"""
    tool: str
    allowed: bool
    result: Optional[Any] = None
    reason: Optional[str] = None
    tier: Optional[str] = None


class OutputGuardResponse(BaseModel):
    """Response from Output Guard"""
    action: str  # PASS, REDACT, BLOCK
    categories: List[str] = Field(default_factory=list)
    redacted_response: Optional[str] = None


class PolicyInfo(BaseModel):
    """Authorization decision for the requested business resource."""
    allowed: bool
    matched: bool
    policy_id: str
    resource: str
    tier: str
    tool_names: List[str] = Field(default_factory=list)
    required_roles: List[str] = Field(default_factory=list)
    confidence: float
    reason: str

    @property
    def tool_name(self) -> Optional[str]:
        """Legacy single-tool accessor for backwards compatibility."""
        return self.tool_names[0] if self.tool_names else None


class ChatResponse(BaseModel):
    """Complete chat response"""
    blocked: bool = False
    reply: str = ""
    leaked: bool = False
    audit: List[MCPToolCall] = Field(default_factory=list)
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    guard: str = "SKIPPED"
    filter_enabled: bool = True
    output_guard_enabled: bool = True
    filter_skipped: bool = False
    output_guard_skipped: bool = False
    role: str = "customer"
    model: str = ""
    filter_layers: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None  # Campo para el frontend cuando está bloqueado
    confidence: Optional[float] = None  # Campo para el frontend cuando está bloqueado
    block_type: Optional[str] = None
    policy: Optional[PolicyInfo] = None
    security_classification: Literal["MALICIOUS", "BENIGN", "UNCERTAIN"] = "UNCERTAIN"
    scope: Optional[Dict[str, Any]] = None
    requested_model: Optional[str] = None
    fallback_count: int = 0
    fallback_reason: Optional[str] = None
    eval_counts: Optional[Dict[str, int]] = None
    request_id: Optional[str] = None
    execution_metrics: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    """Health check response"""
    service: str
    status: str
    version: str
    filter_api_connected: bool
    llm_connected: bool
    uptime_seconds: float


class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    code: Optional[str] = None
    friendly: bool = False


class ChatCancelRequest(BaseModel):
    """Request to cancel an active chat execution"""
    conversation_id: str = Field(...)
    user: User

    @field_validator("conversation_id")
    @classmethod
    def validate_conv_id(cls, v: str) -> str:
        return _validate_user_id(v)


class ChatCancelResponse(BaseModel):
    """Response from cancel request"""
    ok: bool
    status: Literal["cancelled", "completed", "not_found"]
    conversation_id: str

