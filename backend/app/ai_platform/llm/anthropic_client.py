"""
Anthropic LLM Client — shared, reusable by any agent.

Wraps the Anthropic SDK. All agents call this client through LLMService.
Never call this directly from agents — use LLMService instead.
"""
import logging
from anthropic import AsyncAnthropic
from app.core.config import settings

logger = logging.getLogger(__name__)


def get_anthropic_client() -> AsyncAnthropic:
    """Return an AsyncAnthropic client initialized with current settings."""
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in .env")
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
