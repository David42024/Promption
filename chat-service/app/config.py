"""Configuration management for Chat Service"""
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""
    
    # Filter API Configuration
    filter_api_url: str = ""
    promption_api_key: Optional[str] = None
    filter_api_key: Optional[str] = None
    tenant_id: Optional[str] = None
    
    # LLM Configuration
    openai_model: str = ""
    openai_tool_model: str = ""
    vercel_ai_url: str = ""
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    openrouter_site_url: str = ""
    gemini_model: str = "gemini-3.1-flash"
    llm_provider_order: str = "openai"
    llm_provider_timeout_seconds: float = 90.0
    llm_total_timeout_seconds: float = 120.0
    llm_max_attempts: int = 1
    llm_retry_backoff_seconds: float = 0.35
    
    # Tool and Token Budgets
    max_tool_turns: int = 5
    max_tool_calls_per_turn: int = 8
    token_budget_chat: int = 2500
    token_budget_scope: int = 600
    token_budget_tools: int = 4500
    max_context_chars: int = 80000
    
    # Service Configuration
    service_name: str = "promption-chat-service"
    version: str = "1.0.0"
    debug: bool = False
    chat_service_token: Optional[str] = None
    security_state_path: str = "data/security-state.json"
    storage_backend: str = "memory"
    sqlite_db_path: str = "data/conversations.db"
    redis_url: str = "redis://localhost:6379/0"
    workers: int = 1
    
    # CORS Configuration (como string separado por comas)
    cors_origins_str: str = ""
    
    @property
    def cors_origins(self) -> List[str]:
        """Parse CORS origins from comma-separated string"""
        return [origin.strip() for origin in self.cors_origins_str.split(",") if origin.strip()]
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"
    )


settings = Settings()


def validate_chat_service_configuration(s: Settings | None = None, *, is_test: bool | None = None) -> None:
    """Validate authorized configuration fail-closed before serving chat traffic."""
    import os
    cfg = s or settings
    if cfg.chat_service_token is not None and not cfg.chat_service_token.strip():
        raise ValueError("chat_service_token cannot be an empty string")
    if not cfg.debug and not cfg.chat_service_token:
        raise ValueError("chat_service_token is required in non-debug mode")

    if cfg.llm_provider_timeout_seconds <= 0:
        raise ValueError("llm_provider_timeout_seconds must be positive")
    if cfg.llm_total_timeout_seconds <= 0:
        raise ValueError("llm_total_timeout_seconds must be positive")
    if cfg.llm_total_timeout_seconds < cfg.llm_provider_timeout_seconds:
        raise ValueError("llm_total_timeout_seconds must be greater than or equal to llm_provider_timeout_seconds")
    if cfg.llm_max_attempts < 1:
        raise ValueError("llm_max_attempts must be at least 1")
    if not cfg.llm_provider_order or not cfg.llm_provider_order.strip():
        raise ValueError("llm_provider_order cannot be empty")
    if cfg.max_tool_turns < 1:
        raise ValueError("max_tool_turns must be at least 1")
    if cfg.max_tool_calls_per_turn < 1:
        raise ValueError("max_tool_calls_per_turn must be at least 1")
    if cfg.token_budget_chat < 100:
        raise ValueError("token_budget_chat must be at least 100")
    if cfg.token_budget_scope < 100:
        raise ValueError("token_budget_scope must be at least 100")
    if cfg.token_budget_tools < 100:
        raise ValueError("token_budget_tools must be at least 100")
    if cfg.max_context_chars < 1000:
        raise ValueError("max_context_chars must be at least 1000")

    if is_test is None:
        is_test_mode = (
            "PYTEST_CURRENT_TEST" in os.environ
            or os.environ.get("PROMPTION_TEST_MODE", "").lower() in ("1", "true", "yes")
            or os.environ.get("TESTING", "").lower() in ("1", "true", "yes")
        )
    else:
        is_test_mode = is_test

    if cfg.filter_api_url:
        url = cfg.filter_api_url.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(f"filter_api_url must be an HTTP/HTTPS URL, got: '{url}'")
        key = (cfg.promption_api_key or cfg.filter_api_key or "").strip()
        if not key:
            raise ValueError("filter_api_key or promption_api_key is required when filter_api_url is configured")

    if not is_test_mode:
        if not cfg.filter_api_url or not cfg.filter_api_url.strip():
            raise ValueError("filter_api_url is required outside test mode")
        filter_key = (cfg.promption_api_key or cfg.filter_api_key or "").strip()
        if not filter_key:
            raise ValueError("filter_api_key or promption_api_key is required outside test mode")

        providers = [p.strip().lower() for p in cfg.llm_provider_order.split(",") if p.strip()]
        if not providers:
            raise ValueError("llm_provider_order cannot be empty")
        primary_provider = providers[0]

        if primary_provider == "openai":
            if not cfg.vercel_ai_url or not (cfg.vercel_ai_url.startswith("http://") or cfg.vercel_ai_url.startswith("https://")):
                raise ValueError("vercel_ai_url must be a valid HTTP/HTTPS URL when 'openai' is the selected provider")
            if not cfg.openai_model or not cfg.openai_model.strip():
                raise ValueError("openai_model is required when 'openai' is the selected provider")
            if not cfg.openai_tool_model or not cfg.openai_tool_model.strip():
                raise ValueError("openai_tool_model is required when 'openai' is the selected provider")
        elif primary_provider == "gemini":
            if not cfg.gemini_api_key or not cfg.gemini_api_key.strip():
                raise ValueError("gemini_api_key is required when 'gemini' is the selected provider")
            if not cfg.gemini_model or not cfg.gemini_model.strip():
                raise ValueError("gemini_model is required when 'gemini' is the selected provider")
        elif primary_provider == "groq":
            if not cfg.groq_api_key or not cfg.groq_api_key.strip():
                raise ValueError("groq_api_key is required when 'groq' is the selected provider")
        elif primary_provider == "openrouter":
            if not cfg.openrouter_api_key or not cfg.openrouter_api_key.strip():
                raise ValueError("openrouter_api_key is required when 'openrouter' is the selected provider")
        else:
            raise ValueError(f"Unknown or unconfigured selected LLM provider: '{primary_provider}'")
