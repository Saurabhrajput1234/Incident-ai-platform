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

logger = logging.getLogger(__name__)


class AcknowledgementService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.incident_service = IncidentService(db)
        self.context_service = ContextService(db)
        self.work_note_svc = WorkNoteService(db)
        self.agent = AcknowledgementAgent()

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

        # Map intent → state + message
        if intent_info.intent == IntentType.SALESFORCE_INCORRECT_REQUEST:
            new_state = "on_hold"
            note_msg = (
                "Acknowledgement Agent executed successfully.\n"
                "• Incident classified as Salesforce Access / Update Request.\n"
                "• Request submitted under incorrect form for Salesforce.com GTS (EANZ) & GEM.\n"
                "• User notified to submit 'Application Access Request' RITM via IT Central.\n"
                "• Incident status updated to Pending."
            )
        elif intent_info.intent == IntentType.WRONG_REQUEST:
            new_state = "on_hold"
            note_msg = (
                "Acknowledgement Agent executed successfully.\n"
                "• Incident classified as Wrong Request.\n"
                "• Request raised under an incorrect Assignment Group.\n"
                "• User notified to raise the request using the correct request form.\n"
                "• Incident status updated to Pending."
            )
        elif intent_info.intent == IntentType.ACCESS_REQUEST:
            new_state = "on_hold"
            note_msg = (
                "Acknowledgement Agent executed successfully.\n"
                "• Incident classified as Access Request.\n"
                "• Request requires access authorization / approval via Access Portal.\n"
                "• User notified to submit request via Access Governance Portal.\n"
                "• Incident status updated to Pending."
            )
        elif intent_info.intent == IntentType.SERVICE_REQUEST:
            new_state = "on_hold"
            note_msg = (
                "Acknowledgement Agent executed successfully.\n"
                "• Incident classified as Service Request.\n"
                "• Hardware / software item requested via incident ticket.\n"
                "• User notified to order item via Service Catalog.\n"
                "• Incident status updated to Pending."
            )
        else:  # STANDARD_INCIDENT
            new_state = incident.state
            note_msg = (
                "Acknowledgement Agent executed successfully.\n"
                "• Incident classified as Standard Incident.\n"
                f"• Ticket assigned to {incident.assigned_to or 'Engineer'} ({incident.assignment_group or 'Group'}).\n"
                "• User notified with assignment details."
            )

        # Update incident state (if changed)
        if new_state != incident.state:
            await self.incident_service.update_incident_internal(
                incident.id,
                IncidentUpdate(state=new_state),
            )

        # Write structured work note
        await self.work_note_svc.add_note(
            incident_id=incident.id,
            message=note_msg,
            source_type=WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT,
            source_name="AcknowledgementAgent",
            action_type=WorkNoteActionType.SEND_ACKNOWLEDGEMENT,
        )

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
