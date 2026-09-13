"""Pydantic request/response schemas for the API."""
from pydantic import BaseModel, Field


class FilterRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Prompt to analyze")
    use_ml: bool = True
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    user_id: str | None = Field(default=None, description="End-user id (audit + per-user policy)")
    roles: list[str] = Field(default_factory=list, description="End-user roles/scopes")
    context: dict = Field(default_factory=dict, description="Tenant-defined context (doc ACL, channel…)"
                          )


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


class BenchmarkRequest(BaseModel):
    sample_size: int | None = Field(default=None, ge=1)
    use_llm: bool = True
    dataset: str | None = None


class OutputGuardRequest(BaseModel):
    text: str = Field(..., min_length=1, description="LLM response to inspect")
    user_id: str | None = None
    roles: list[str] = Field(default_factory=list, description="End-user roles/scopes")
    context: dict = Field(default_factory=dict)


class OutputGuardResponse(BaseModel):
    action: str
    risk: float
    categories: list[str] = []
    matches: int = 0
    redacted_response: str | None = None
    tenant_id: str = "default"


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
