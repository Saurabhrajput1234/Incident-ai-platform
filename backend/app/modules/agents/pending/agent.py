"""
Pending Agent implementation.

Responsibility:
  1. Inspect incident context.
  2. Determine if ticket is pending/on_hold.
  3. Analyze previous work note using PendingWorkNoteAnalyzer.
  4. Return AgentResponse with decision on whether to send reminder.
"""
import logging
from app.modules.agents.base.base_agent import BaseAgent
from app.modules.agents.base.response import AgentResponse
from app.modules.context.schemas import AIContext
from app.modules.agents.pending.work_note_analyzer import PendingWorkNoteAnalyzer

logger = logging.getLogger(__name__)


class PendingAgent(BaseAgent):
    def __init__(self):
        self.analyzer = PendingWorkNoteAnalyzer()

    @property
    def agent_name(self) -> str:
        return "PendingAgent"

    async def reason(self, context: AIContext) -> AgentResponse:
        incident = context.incident
        short_desc = incident.short_description or ""
        group = incident.assignment_group or ""

        # Find latest work notes (top 2) from context if available
        notes_text = ""
        source_name = "Engineer"
        if incident.work_notes:
            notes = [n.strip() for n in incident.work_notes.strip().split("────────────────────────────────────────") if n.strip()]
            if notes:
                notes_text = "\n\n---\n\n".join(notes[:2])

        incident_context_str = f"Incident: {incident.incident_number}, Short Description: {short_desc}, Group: {group}"
        analysis = await self.analyzer.analyze(
            latest_work_note=notes_text,
            source_name=source_name,
            incident_context=incident_context_str,
        )

        result_data = {
            "incident_id": incident.incident_id,
            "incident_number": incident.incident_number,
            "is_caller_action_required": analysis.is_caller_action_required,
            "reasoning": analysis.reasoning,
            "confidence": analysis.confidence,
        }

        return AgentResponse(
            success=True,
            agent_name=self.agent_name,
            reasoning=analysis.reasoning,
            confidence=analysis.confidence,
            result=result_data,
        )
