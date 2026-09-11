"""
Acknowledgement Service Orchestrator.

Flow:
  1. Fetch Incident context via ContextService
  2. Run AcknowledgementAgent (evaluates intent)
  3. Update incident state if needed
  4. Write structured work note via WorkNoteService
  5. Return result
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.agents.base.request import AgentRequest
from app.modules.agents.base.response import AgentResponse
from app.modules.agents.acknowledgement.agent import AcknowledgementAgent
from app.modules.agents.acknowledgement.schemas import (
    IntentResult, AcknowledgementResult, IntentType
)
from app.modules.context.service import ContextService
from app.modules.incidents.service import IncidentService
from app.modules.incidents.schemas import IncidentUpdate
from app.modules.work_notes.service import WorkNoteService
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType

from app.modules.agents.acknowledgement.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class AcknowledgementService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.incident_service = IncidentService(db)
        self.context_service = ContextService(db)
        self.work_note_svc = WorkNoteService(db)
        self.agent = AcknowledgementAgent()
        self.renderer = TemplateRenderer()

    async def process_acknowledgement(self, incident_id: str) -> AgentResponse:
        incident = await self.incident_service.get_incident(incident_id)
        context = await self.context_service.build_for_incident(incident_id=incident.id)

        request = AgentRequest(context=context)
        agent_response = await self.agent.run(request)

        if not agent_response.success:
            return agent_response

        res_data = agent_response.result
        intent_info = IntentResult(**res_data["intent_info"])
        template_used = res_data.get("template_used", "standard_ack.html")

        # Build template rendering context
        tpl_context = {
            "ticket_number": incident.incident_number,
            "caller_name": incident.caller or "Valued Employee",
            "short_description": incident.short_description or "",
            "assignment_group": incident.assignment_group or "Support Team",
            "assigned_engineer_name": incident.assigned_to or "Assigned Engineer",
        }

        # Render complete email body
        email_text = self.renderer.render_plain_text_email(template_used, tpl_context)

        # Determine state change
        if intent_info.intent in (
            IntentType.SALESFORCE_INCORRECT_REQUEST,
            IntentType.WRONG_REQUEST,
            IntentType.ACCESS_REQUEST,
            IntentType.SERVICE_REQUEST,
        ):
            new_state = "on_hold"
            status_desc = "Incident status updated to Pending / On Hold."
        else:  # STANDARD_INCIDENT
            new_state = incident.state
            status_desc = f"Ticket assigned to {incident.assigned_to or 'Engineer'} ({incident.assignment_group or 'Group'})."

        # Construct work note containing status and the whole rendered email content
        note_msg = (
            f"Acknowledgement Agent executed successfully.\n"
            f"• Classified Intent: {intent_info.intent.value} (Confidence: {intent_info.confidence:.2f})\n"
            f"• Selected Template: {template_used}\n"
            f"• Status: {status_desc}\n\n"
            f"==================== EMAIL SENT TO USER ====================\n"
            f"{email_text}\n"
            f"============================================================"
        )

        # Update incident state (if changed)
        if new_state != incident.state:
            await self.incident_service.update_incident_internal(
                incident.id,
                IncidentUpdate(state=new_state),
            )

        # Write structured work note
        # auto_activate=False: the state was intentionally set to on_hold above;
        # this note must not undo that deliberate transition.
        await self.work_note_svc.add_note(
            incident_id=incident.id,
            message=note_msg,
            source_type=WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT,
            source_name="AcknowledgementAgent",
            action_type=WorkNoteActionType.SEND_ACKNOWLEDGEMENT,
            auto_activate=False,
        )

        # Auto-trigger Pending Agent when moved to on_hold/pending
        if new_state in ("on_hold", "pending"):
            try:
                from app.modules.agents.pending.service import PendingService
                pending_svc = PendingService(self.db)
                await pending_svc.process_pending_transition(incident_id=incident.id)
            except Exception as e:
                logger.error(f"[AcknowledgementService] Auto-trigger for PendingAgent failed: {e}")

        ack_result = AcknowledgementResult(
            incident_id=incident.id,
            incident_number=incident.incident_number,
            caller=incident.caller,
            assigned_to=incident.assigned_to,
            assignment_group=incident.assignment_group,
            intent_info=intent_info,
            template_used=template_used,
            email_sent=True,
            delivery_status="simulated_success",
            work_notes_added=note_msg,
        )

        agent_response.result = ack_result.model_dump()
        return agent_response
