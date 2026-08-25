"""
LLM Service — shared service layer for all AI agents.

Any agent that needs LLM reasoning calls this service.
It handles the Groq API call, error handling, and returns a clean string response.

Usage:
    from app.ai_platform.services.llm_service import LLMService
    llm = LLMService()
    response = await llm.complete(messages=[...])
"""
import logging
from app.ai_platform.llm.groq_client import get_groq_client
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """
    Shared LLM service — wraps Groq API.
    Reusable by Triage Agent, Acknowledgement Agent, Resolution Agent, etc.
    """

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Send a chat completion request to Groq.

        Args:
            messages: List of {role, content} dicts — system + user messages
            model: Override the default model from settings
            max_tokens: Override default max tokens
            temperature: Override default temperature

        Returns:
            The LLM response as a plain string.
        """
        client = get_groq_client()

        response = await client.chat.completions.create(
            model=model or settings.GROQ_MODEL,
            messages=messages,
            max_tokens=max_tokens or settings.GROQ_MAX_TOKENS,
            temperature=temperature if temperature is not None else settings.GROQ_TEMPERATURE,
        )

        result = response.choices[0].message.content.strip()
        if "</think>" in result:
            result = result.split("</think>")[-1].strip()
        logger.debug(f"LLM response ({len(result)} chars): {result[:100]}...")
        return result
