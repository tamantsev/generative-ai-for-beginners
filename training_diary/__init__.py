"""Training diary Telegram bot and mini app package."""

from .config import get_settings
from .database import init_db

__all__ = ["get_settings", "init_db"]
