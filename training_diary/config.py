"""Configuration helpers for the training diary bot and mini app."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from typing import List

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """Runtime configuration loaded from environment variables."""

    telegram_bot_token: str
    database_url: str
    webapp_base_url: str | None = None
    allowed_origins: List[str] | None = None

    @property
    def time_zone(self) -> str:
        return os.getenv("TIME_ZONE", "UTC")


@lru_cache()
def get_settings() -> Settings:
    """Return singleton settings instance."""

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is required")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")

    webapp_base_url = os.getenv("WEBAPP_BASE_URL")
    allowed_origins = os.getenv("ALLOWED_ORIGINS")
    origins = [origin.strip() for origin in allowed_origins.split(",") if origin.strip()] if allowed_origins else None

    return Settings(
        telegram_bot_token=token,
        database_url=database_url,
        webapp_base_url=webapp_base_url,
        allowed_origins=origins,
    )
