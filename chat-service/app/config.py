"""Configuration management for Chat Service"""
import os
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""
    
    # Filter API Configuration
    filter_api_url: str = "https://promption.onrender.com"
    filter_api_key: str = "pif_demo_shop_123456"
    tenant_id: str = "demo-shop"
    
    # LLM Configuration
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    default_model: str = "llama-3.1-70b-versatile"
    gemini_model: str = "gemini-3.1-flash"
    llm_provider_order: str = "gemini,groq,openrouter"
    llm_provider_timeout_seconds: float = 8.0
    llm_total_timeout_seconds: float = 24.0
    llm_max_attempts: int = 1
    llm_retry_backoff_seconds: float = 0.35
    
    # Service Configuration
    service_name: str = "promption-chat-service"
    version: str = "1.0.0"
    debug: bool = False
    chat_service_token: Optional[str] = None
    
    # CORS Configuration (como string separado por comas)
    cors_origins_str: str = "http://localhost:3000,https://promptionsi.vercel.app,https://promption.shop"
    
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
