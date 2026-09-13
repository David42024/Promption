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
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    default_model: str = "llama-3.1-70b-versatile"
    openai_model: str = "gpt-4o-mini"
    gemini_model: str = "gemini-3.1-pro-preview"
    llm_provider_order: str = "openai,gemini,groq,openrouter"
    
    # Service Configuration
    service_name: str = "promption-chat-service"
    version: str = "1.0.0"
    debug: bool = False
    
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
