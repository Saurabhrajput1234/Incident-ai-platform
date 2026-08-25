"""
Groq LLM Client — shared, reusable by any agent.

Wraps the Groq SDK. All agents call this client through LLMService.
Never call this directly from agents — use LLMService instead.
"""
import logging
from groq import AsyncGroq
from app.core.config import settings

logger = logging.getLogger(__name__)

# Single shared async client instance
_client: AsyncGroq | None = None


def get_groq_client() -> AsyncGroq:
    """Return an AsyncGroq client initialized with current settings."""
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set in .env")
    return AsyncGroq(api_key=settings.GROQ_API_KEY)
