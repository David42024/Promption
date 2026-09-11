"""Pydantic models for Chat Service"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


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
    categories: List[str] = []
    redacted_response: Optional[str] = None


class ChatResponse(BaseModel):
    """Complete chat response"""
    blocked: bool = False
    reply: str = ""
    leaked: bool = False
    audit: List[MCPToolCall] = []
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
