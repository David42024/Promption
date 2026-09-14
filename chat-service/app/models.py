"""Pydantic models for Chat Service"""
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    """User roles"""
    ADMIN = "admin"
    VENTAS = "ventas"
    CUSTOMER = "customer"
    GUEST = "guest"


class User(BaseModel):
    """User information"""
    id: str
    name: str
    email: str
    roles: List[UserRole]
    avatar: Optional[str] = None
    puesto: Optional[str] = None
    authenticated: bool = True


class ChatRequest(BaseModel):
    """Chat request from frontend"""
    text: str = Field(..., min_length=1, max_length=5000)
    user: User
    context: Optional[Dict[str, Any]] = None


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
    tool_name: Optional[str] = None
    required_roles: List[str] = Field(default_factory=list)
    confidence: float
    reason: str


class ChatResponse(BaseModel):
    """Complete chat response"""
    blocked: bool = False
    reply: str = ""
    leaked: bool = False
    audit: List[MCPToolCall] = Field(default_factory=list)
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
    friendly: bool = False
