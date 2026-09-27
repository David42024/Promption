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
    
    # Service Configuration
    service_name: str = "promption-chat-service"
    version: str = "1.0.0"
    debug: bool = False
    chat_service_token: Optional[str] = None
    security_state_path: str = "data/security-state.json"
    
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
