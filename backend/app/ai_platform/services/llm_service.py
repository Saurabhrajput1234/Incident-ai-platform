"""
LLM Service — shared service layer for all AI agents.

Any agent that needs LLM reasoning calls this service.
It handles the Anthropic Claude API call, error handling, and returns a clean string response.

Usage:
    from app.ai_platform.services.llm_service import LLMService
    llm = LLMService()
    response = await llm.complete(messages=[...])
"""
import logging
from app.ai_platform.llm.anthropic_client import get_anthropic_client
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """
    Shared LLM service — wraps Anthropic Claude API.
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
        Send a chat completion request to Anthropic Claude.

        Args:
            messages: List of {role, content} dicts — user messages only (system handled separately)
            model: Override the default model from settings
            max_tokens: Override default max tokens
            temperature: Override default temperature

        Returns:
            The LLM response as a plain string.
        """
        client = get_anthropic_client()

        # Extract system message if present (Anthropic uses a separate system parameter)
        system_message = None
        user_messages = []
        
        for msg in messages:
            if msg.get("role") == "system":
                system_message = msg.get("content")
            else:
                user_messages.append(msg)

        # Build request kwargs
        kwargs = {
            "model": model or settings.ANTHROPIC_MODEL,
            "max_tokens": max_tokens or settings.ANTHROPIC_MAX_TOKENS,
            "messages": user_messages,
        }
        
        if system_message:
            kwargs["system"] = system_message

        response = await client.messages.create(**kwargs)

        result = response.content[0].text.strip()
        logger.debug(f"LLM response ({len(result)} chars): {result[:100]}...")
        return result
