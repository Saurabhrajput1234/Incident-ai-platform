"""
AI Platform health check endpoints.
"""
from fastapi import APIRouter
from app.ai_platform.services.llm_service import LLMService
from app.core.config import settings
from app.modules.shift_roster.shift_time_checker import get_shift_status_summary

router = APIRouter()


@router.get("/ai-health", tags=["health"])
async def ai_health_check():
    """
    Test the Anthropic Claude LLM connection by sending a simple ping message.
    Returns model info and confirms the API key is working.
    """
    if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY == "your-anthropic-api-key-here":
        return {"status": "not_configured", "message": "ANTHROPIC_API_KEY is not set in .env"}

    try:
        llm = LLMService()
        response = await llm.complete(
            messages=[{"role": "user", "content": "Say 'OK' and nothing else."}],
            max_tokens=5,
        )
        return {"status": "healthy", "model": settings.ANTHROPIC_MODEL, "response": response}
    except Exception as e:
        return {"status": "unhealthy", "model": settings.ANTHROPIC_MODEL, "error": str(e)}


@router.get("/shift-status", tags=["health"])
async def shift_status():
    """
    Returns which shifts are currently active based on real-world time.
    Use this to verify the shift time checker is working correctly.
    """
    return {"status": "ok", "shifts": get_shift_status_summary()}
