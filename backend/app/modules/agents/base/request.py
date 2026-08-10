"""Base agent request schema."""
from pydantic import BaseModel
from app.modules.context.schemas import AIContext


class AgentRequest(BaseModel):
    """Standard input to every agent — always wraps an AIContext."""
    context: AIContext
    metadata: dict = {}  # optional caller metadata (e.g. triggered_by, trace_id)

    model_config = {"arbitrary_types_allowed": True}
