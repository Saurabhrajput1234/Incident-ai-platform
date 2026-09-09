"""
Pending Service Orchestrator.

Flow:
  1. Idempotency check: inspect pending_cycles for active cycle.
  2. If active cycle exists: preserve it unless advancing reminder tier.
  3. Fetch latest work note from incident_work_notes.
  4. Run LLM analyzer to verify if user action is needed.
  5. Create/update cycle, render reminder email, add work note with full email text.
  6. Enforce incident state to PENDING.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.agents.base.response import AgentResponse
from app.modules.agents.pending.agent import PendingAgent
from app.modules.agents.pending.models.pending_cycle import PendingCycleStatus
from app.modules.agents.pending.repository import PendingCycleRepository
from app.modules.agents.pending.reminder_renderer import PendingReminderRenderer
from app.modules.agents.pending.schemas import PendingResult
from app.modules.agents.pending.work_note_analyzer import PendingWorkNoteAnalyzer
from app.modules.incidents.service import IncidentService
from app.modules.incidents.schemas import IncidentUpdate
from app.modules.work_notes.service import WorkNoteService
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType

logger = logging.getLogger(__name__)


class PendingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.incident_service = IncidentService(db)
        self.work_note_svc = WorkNoteService(db)
        self.cycle_repo = PendingCycleRepository(db)
        self.analyzer = PendingWorkNoteAnalyzer()
        self.renderer = PendingReminderRenderer()
        self.agent = PendingAgent()

    async def get_cycle_status(self, incident_id: str) -> dict | None:
        """Returns the current active or latest cycle for an incident."""
        cycle = await self.cycle_repo.get_active_cycle(incident_id)
        if not cycle:
            cycle = await self.cycle_repo.get_latest_cycle(incident_id)
        if not cycle:
            return None
        return {
            "id": cycle.id,
            "incident_id": cycle.incident_id,
            "incident_number": cycle.incident_number,
            "status": cycle.status.value if hasattr(cycle.status, "value") else str(cycle.status),
            "reminder_count": cycle.reminder_count,
            "max_reminders": cycle.max_reminders,
            "source_type": cycle.source_type,
            "next_reminder_at": cycle.next_reminder_at.isoformat() if cycle.next_reminder_at else None,
            "created_at": cycle.created_at.isoformat() if cycle.created_at else None,
            "updated_at": cycle.updated_at.isoformat() if cycle.updated_at else None,
        }

    async def process_pending_transition(
        self,
        incident_id: str,
        force_reminder: bool = False,
    ) -> AgentResponse:
        """
        Executes the pending cycle flow whenever an incident enters pending/on_hold.
        """
        incident = await self.incident_service.get_incident(incident_id)
        existing_cycle = await self.cycle_repo.get_active_cycle(incident_id)

        # 1. Idempotency Gate: If cycle is already active and this is just an auto-bounce, preserve it
        if existing_cycle and not force_reminder:
            logger.info(f"[PendingService] Active cycle '{existing_cycle.id}' exists for {incident.incident_number}. Preserving cycle.")
            # Ensure ticket state remains on_hold (pending)
            if incident.state not in ("on_hold", "pending"):
                await self.incident_service.update_incident_internal(
                    incident.id, IncidentUpdate(state="on_hold")
                )

            res = PendingResult(
                incident_id=incident.id,
                incident_number=incident.incident_number,
                caller=incident.caller,
                assigned_to=incident.assigned_to,
                assignment_group=incident.assignment_group,
                cycle_id=existing_cycle.id,
                cycle_status=existing_cycle.status,
                reminder_count=existing_cycle.reminder_count,
                max_reminders=existing_cycle.max_reminders,
                is_caller_action_required=True,
                action_taken="CYCLE_PRESERVED",
                email_sent=False,
                next_reminder_at=existing_cycle.next_reminder_at,
            )
            return AgentResponse(
                success=True,
                agent_name="PendingAgent",
                reasoning=f"Active cycle {existing_cycle.id} is already in progress (Reminder {existing_cycle.reminder_count}/{existing_cycle.max_reminders}). Cycle preserved.",
                result=res.model_dump(),
            )

        # 2. Fetch the recent work notes (top two notes, plus prior substantive context if needed)
        latest_notes = await self.work_note_svc.get_notes(incident_id=incident.id, limit=15)
        top_two = latest_notes[:2]

        # Also find the most recent substantive note (not just a state transition) to provide true context
        prior_substantive = None
        for n in latest_notes:
            if n.action_type not in (WorkNoteActionType.STATE_CHANGE, WorkNoteActionType.INCIDENT_UPDATE):
                prior_substantive = n
                break

        formatted_notes = []
        source_names = []
        for idx, n in enumerate(top_two):
            label = "Latest Note" if idx == 0 else "Previous Note (Below Latest)"
            formatted_notes.append(f"[{label} - {n.source_name} ({n.source_type})]:\n{n.message}")
            if n.source_name not in source_names:
                source_names.append(n.source_name)

        # If both top notes are purely state changes and we have a substantive note, append it
        if prior_substantive and prior_substantive not in top_two:
            formatted_notes.append(f"[Recent Context Note - {prior_substantive.source_name} ({prior_substantive.source_type})]:\n{prior_substantive.message}")
            if prior_substantive.source_name not in source_names:
                source_names.append(prior_substantive.source_name)

        combined_notes_str = "\n\n".join(formatted_notes) if formatted_notes else (incident.description or "")
        primary_source = ", ".join(source_names) if source_names else (incident.assigned_to or "Engineer")

        # 3. Analyze work notes via LLM
        incident_context_str = f"Ticket: {incident.incident_number} | Title: {incident.short_description} | Description: {incident.description or incident.short_description} | Assigned: {incident.assigned_to} ({incident.assignment_group})"
        analysis = await self.analyzer.analyze(
            latest_work_note=combined_notes_str,
            source_name=primary_source,
            incident_context=incident_context_str,
        )

        # Ensure sensible awaiting detail for the user reminder
        awaiting_detail = analysis.reasoning
        if not awaiting_detail or awaiting_detail.strip() == "" or not analysis.is_caller_action_required:
            if incident.short_description:
                awaiting_detail = f"Awaiting caller response and confirmation regarding '{incident.short_description}'."
            else:
                awaiting_detail = "Awaiting requested details and confirmation from caller to proceed."

        # 4. Cycle Management: advance or create
        if existing_cycle and force_reminder:
            cycle = await self.cycle_repo.increment_reminder(existing_cycle)
            reminder_tier = cycle.reminder_count
        else:
            source_type_val = "ACKNOWLEDGEMENT_AGENT" if "Acknowledgement" in primary_source else "ENGINEER"
            cycle = await self.cycle_repo.create_cycle(
                incident_id=incident.id,
                incident_number=incident.incident_number,
                source_type=source_type_val,
                reminder_count=1,
                max_reminders=3,
            )
            reminder_tier = 1

        # 5. Render reminder email
        render_ctx = {
            "ticket_number": incident.incident_number,
            "caller_name": incident.caller or "Valued Employee",
            "short_description": incident.short_description or "",
            "assignment_group": incident.assignment_group or "Support Team",
            "assigned_engineer_name": incident.assigned_to or "Assigned Support Engineer",
            "reminder_count": reminder_tier,
            "max_reminders": cycle.max_reminders,
            "is_final": (reminder_tier >= cycle.max_reminders),
            "awaiting_detail": awaiting_detail,
        }
        email_text = self.renderer.render_plain_text_email(render_ctx)

        # 6. Add work note with full email text
        note_msg = (
            f"Pending Agent: Reminder {reminder_tier} of {cycle.max_reminders} sent to user.\n"
            f"• Cycle ID: {cycle.id}\n"
            f"• Awaiting from User: {awaiting_detail}\n"
            f"• Follow-up Status: {'Cycle Completed (Max Reminders Sent)' if cycle.status == PendingCycleStatus.COMPLETED else 'Awaiting User Response'}\n"
            f"• State: Maintained in Pending\n\n"
            f"==================== EMAIL SENT TO USER ====================\n"
            f"{email_text}\n"
            f"============================================================"
        )

        await self.work_note_svc.add_note(
            incident_id=incident.id,
            message=note_msg,
            source_type=WorkNoteSourceType.PENDING_AGENT,
            source_name="PENDING AGENT",
            action_type=WorkNoteActionType.SEND_REMINDER,
        )

        # 7. Force ticket state to on_hold (pending)
        if incident.state not in ("on_hold", "pending"):
            await self.incident_service.update_incident_internal(
                incident.id, IncidentUpdate(state="on_hold")
            )

        res = PendingResult(
            incident_id=incident.id,
            incident_number=incident.incident_number,
            caller=incident.caller,
            assigned_to=incident.assigned_to,
            assignment_group=incident.assignment_group,
            cycle_id=cycle.id,
            cycle_status=cycle.status,
            reminder_count=cycle.reminder_count,
            max_reminders=cycle.max_reminders,
            is_caller_action_required=True,
            action_taken="CYCLE_COMPLETED" if cycle.status == PendingCycleStatus.COMPLETED else "CYCLE_STARTED",
            email_sent=True,
            delivery_status="simulated_success",
            work_notes_added=note_msg,
            next_reminder_at=cycle.next_reminder_at,
        )

        return AgentResponse(
            success=True,
            agent_name="PendingAgent",
            reasoning=f"Reminder {reminder_tier} of {cycle.max_reminders} generated and logged. Ticket maintained in Pending.",
            confidence=analysis.confidence,
            result=res.model_dump(),
        )
