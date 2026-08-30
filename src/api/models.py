"""Pydantic request/response schemas for the API."""
from pydantic import BaseModel, Field


class FilterRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Prompt to analyze")
    use_ml: bool = True
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)


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


class BenchmarkRequest(BaseModel):
    sample_size: int | None = Field(default=None, ge=1)
    use_llm: bool = True
    dataset: str | None = None


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