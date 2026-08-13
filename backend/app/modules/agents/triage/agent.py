"""
Triage Agent.

Responsibility: Determine the assignment group only.

The agent does NOT select engineers, score, or rank anyone.
Engineer selection is done by AssignmentService after the agent runs.

Flow:
  1. Validate context (assignment_group must be set — LLM already resolved it)
  2. Confirm the group exists in context
  3. Return the assignment group for AssignmentService to use

Rules:
  - Never queries DB
  - Never calls repositories or services
  - Never updates incidents
  - Only works on the AIContext it receives
"""
import logging
from datetime import datetime, timezone

from app.modules.agents.base.base_agent import BaseAgent
from app.modules.agents.base.response import AgentResponse
from app.modules.agents.base.exceptions import ContextValidationError
from app.modules.agents.triage.schemas import TriageResult
from app.modules.context.schemas import AIContext

logger = logging.getLogger(__name__)


class TriageAgent(BaseAgent):
    """
    Validates context and confirms the assignment group.
    Engineer selection is delegated to AssignmentService.
    """

    @property
    def agent_name(self) -> str:
        return "TriageAgent"

    def validate_context(self, context: AIContext) -> None:
        super().validate_context(context)
        if not context.incident.assignment_group:
            raise ContextValidationError(
                "No assignment group in context — LLM resolution required before running agent"
            )

    async def reason(self, context: AIContext) -> AgentResponse:
        incident = context.incident
        available_count = sum(1 for e in context.engineers if e.is_available)
        total_count = len(context.engineers)

        result = TriageResult(
            incident_id=incident.incident_id,
            incident_number=incident.incident_number,
            assignment_group=incident.assignment_group,
            recommended_engineer=None,   # set by AssignmentService after this
            all_candidates=[],
            recommendation_reason=(
                f"Assignment group confirmed: '{incident.assignment_group}'. "
                f"{available_count}/{total_count} engineers available on {context.context_date}. "
                f"Delegating engineer selection to AssignmentService."
            ),
            timestamp=datetime.now(timezone.utc),
        )

        logger.info(
            f"[TriageAgent] {incident.incident_number} → group='{incident.assignment_group}' "
            f"available={available_count}/{total_count}"
        )

        return AgentResponse(
            success=True,
            agent_name=self.agent_name,
            reasoning=result.recommendation_reason,
            confidence=1.0,
            result=result.model_dump(),
        )
