"""
Unified Settings class.

Merges all config sections into a single Settings instance
using multiple inheritance. Pydantic-settings reads values
from the .env file and environment variables automatically.

Import pattern everywhere in the app:
    from app.core.config import settings
"""
from app.core.config.app import AppSettings
from app.core.config.database import DatabaseSettings
from app.core.config.logging import LoggingSettings
from app.core.config.security import SecuritySettings
from app.core.config.ai import AISettings
from app.core.config.notifications import NotificationSettings


class Settings(AppSettings, DatabaseSettings, LoggingSettings, SecuritySettings, AISettings, NotificationSettings):
    """Combined settings from all config modules."""
    pass


# Singleton instance — import this directly instead of instantiating Settings yourself
settings = Settings()
