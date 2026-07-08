import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("kalories.config")

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    MONGODB_URL: str = "mongodb://localhost:27017/kalories"
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    USDA_API_KEY: str = ""
    HF_API_KEY: str = ""
    FOOD_ANALYSIS_PROMPT: str = ""
    GEMMA_MODEL_NAME: str = "google/gemma-4-12B-it"
    OLLAMA_URL: str = "http://localhost:11434"

    # JWT Authentication settings
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Caching
    REDIS_URL: str = "redis://localhost:6379/0"

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

# Enforce secret injection in production
if settings.ENVIRONMENT == "production" and not settings.JWT_SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY must be configured via environment variables in production!")

# Log API key presence on startup
logger.info(f"Settings loaded. Gemini API key present: {bool(settings.GEMINI_API_KEY)}")
logger.info(f"OpenAI API key present: {bool(settings.OPENAI_API_KEY)}")
logger.info(f"Anthropic API key present: {bool(settings.ANTHROPIC_API_KEY)}")
logger.info(f"Hugging Face API key present: {bool(settings.HF_API_KEY)}")
logger.info(f"Gemma model name: {settings.GEMMA_MODEL_NAME}")
logger.info(f"Ollama URL: {settings.OLLAMA_URL}")

