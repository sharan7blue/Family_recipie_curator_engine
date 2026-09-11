"""
PrepLink Settings
===================
Local-preview defaults: everything is overridable via env vars / .env,
but nothing is required to boot the app for a local stub preview.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"
    ALLOWED_ORIGINS: list[str] = ["*"]
    RATE_LIMIT_PER_MINUTE: int = 60

    REDIS_CACHE_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    CELERY_TASK_SOFT_TIME_LIMIT: int = 3600
    CELERY_TASK_TIME_LIMIT: int = 7200

    BULK_JOB_TTL_SECONDS: int = 86400 * 7

    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""


settings = Settings()
