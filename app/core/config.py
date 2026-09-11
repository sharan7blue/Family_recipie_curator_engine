"""
PrepLink Settings
===================
Local-preview defaults: everything is overridable via env vars / .env,
but nothing is required to boot the app for a local stub preview.

Per ADR-004, there is no Celery broker/result-backend anymore — Redis is
used only as a cache (nutrition lookups, recipe-by-id storage).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"
    ALLOWED_ORIGINS: list[str] = ["*"]
    RATE_LIMIT_PER_MINUTE: int = 60

    REDIS_CACHE_URL: str = "redis://localhost:6379/0"
    RECIPE_TTL_SECONDS: int = 86400 * 7  # 7 days

    USDA_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""


settings = Settings()
