"""
Конфигурация приложения
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения"""
    
    # Основные настройки
    app_name: str = "Credit Analysis System"
    debug: bool = False
    version: str = "1.0.0"
    
    # База данных
    database_url: str = "postgresql://postgres:postgres@localhost:5432/credit_analysis"
    
    # Redis
    redis_url: str = "redis://localhost:6379"
    
    # LLM настройки
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    default_llm_provider: str = "openai"
    default_model: str = "gpt-4"
    
    # Файловая система
    upload_dir: str = "./uploads"
    max_file_size: int = 50 * 1024 * 1024  # 50MB
    allowed_extensions: list = [".pdf", ".doc", ".docx"]
    
    # Безопасность
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # CORS
    cors_origins: list = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    
    # Логирование
    log_level: str = "INFO"
    log_format: str = "json"
    
    # Производительность
    max_concurrent_requests: int = 100
    request_timeout: int = 300  # 5 минут
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Глобальный экземпляр настроек
settings = Settings()
