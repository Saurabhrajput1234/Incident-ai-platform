"""Base agent response schema."""
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AgentResponse(BaseModel):
    """Standard output from every agent."""
    success: bool
    agent_name: str
    reasoning: str | None = None      # explanation of decision
    confidence: float | None = None   # 0.0 - 1.0
    result: dict = {}                 # agent-specific output
    errors: list[str] = []
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
