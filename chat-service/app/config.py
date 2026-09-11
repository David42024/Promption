"""Configuration management for Chat Service"""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # Filter API Configuration
    filter_api_url: str = os.getenv("FILTER_API_URL", "https://promption.onrender.com")
    filter_api_key: str = os.getenv("FILTER_API_KEY", "pif_demo_shop_123456")
    tenant_id: str = os.getenv("TENANT_ID", "demo-shop")
    
    # LLM Configuration
    groq_api_key: Optional[str] = os.getenv("GROQ_API_KEY")
    openrouter_api_key: Optional[str] = os.getenv("OPENROUTER_API_KEY")
    default_model: str = os.getenv("DEFAULT_MODEL", "llama-3.1-70b-versatile")
    
    # Service Configuration
    service_name: str = "promption-chat-service"
    version: str = "1.0.0"
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # CORS Configuration
    cors_origins: list[str] = [
        "http://localhost:3000",
        "https://promptionsi.vercel.app",
        "https://promption.shop",
    ]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
