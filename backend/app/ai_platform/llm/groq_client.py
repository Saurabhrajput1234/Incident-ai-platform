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
    """Return the shared AsyncGroq client, creating it on first call."""
    global _client
    if _client is None:
        if not settings.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set in .env")
        _client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        logger.info(f"Groq client initialized (model: {settings.GROQ_MODEL})")
    return _client
