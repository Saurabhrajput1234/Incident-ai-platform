"""
Pending Service Orchestrator.

Flow — initial trigger (no active cycle, force_reminder=False):
  1. Check for an existing active PendingCycle via PendingCycleService.
  2. If one already exists → preserve it (idempotency gate).
  3. Otherwise create a new cycle via create_cycle_if_not_exists().
  4. Schedule Reminder 1 by setting next_reminder_at = now + REMINDER_INTERVAL.
     Do NOT send the reminder immediately.
  5. Return "SCHEDULED" result.  Pending Agent execution ends here.

Flow — scheduled reminder execution (called by scheduler, force_reminder=True):
  1. Validate active cycle still exists.
  2. Fetch work-note context + run LLM analysis.
  3. Increment reminder_count on the cycle (schedules next_reminder_at for the
     NEXT reminder, or clears it on the final reminder).
  4. Render email + add PENDING_AGENT work note via WorkNoteService.
     WorkNoteService may automatically transition ON_HOLD → ACTIVE/IN_PROGRESS.
     This behavior is intentional and must NOT be suppressed.
  5. After the work note is committed, explicitly return the incident to ON_HOLD
     via IncidentService.update_incident_internal().

All cycle persistence goes through the canonical PendingCycleService.
All work notes go through WorkNoteService.

Configuration
-------------
REMINDER_INTERVAL_SECONDS controls the delay between reminders.
Set to 10 for quick local testing; replace with a real interval (e.g. 3600)
in production.
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agents.base.response import AgentResponse
from app.modules.agents.pending.agent import PendingAgent
from app.modules.agents.pending.reminder_renderer import PendingReminderRenderer
from app.modules.agents.pending.schemas import PendingResult
from app.modules.agents.pending.work_note_analyzer import PendingWorkNoteAnalyzer
from app.modules.incidents.service import IncidentService
from app.modules.incidents.schemas import IncidentUpdate
from app.modules.pending_cycles.service import PendingCycleService
from app.modules.pending_cycles.enums import PendingCycleStatus
from app.modules.work_notes.service import WorkNoteService
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — delay between reminders.
# 10 seconds for dev/test; set to a real interval (e.g. 3600) in production.
# ---------------------------------------------------------------------------
REMINDER_INTERVAL_SECONDS: int = 20


class PendingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.incident_service = IncidentService(db)
        self.work_note_svc = WorkNoteService(db)
        self.cycle_svc = PendingCycleService(db)
        self.analyzer = PendingWorkNoteAnalyzer()
        self.renderer = PendingReminderRenderer()
        self.agent = PendingAgent()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    async def get_cycle_status(self, incident_id: str) -> dict | None:
        """Returns the current active cycle for an incident."""
        cycle = await self.cycle_svc.get_active_cycle(incident_id)
        if not cycle:
            return None
        return {
            "id": cycle.id,
            "incident_id": cycle.incident_id,
            "status": cycle.status,
            "reminder_count": cycle.reminder_count,
            "max_reminders": cycle.max_reminders,
            "next_reminder_at": cycle.next_reminder_at.isoformat() if cycle.next_reminder_at else None,
            "created_at": cycle.created_at.isoformat() if cycle.created_at else None,
            "updated_at": cycle.updated_at.isoformat() if cycle.updated_at else None,
        }

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process_pending_transition(
        self,
        incident_id: str,
        force_reminder: bool = False,
    ) -> AgentResponse:
        """
        Called in two situations:

        1. force_reminder=False (default) — incident just entered pending state.
           • If an active cycle already exists: preserve it (idempotency).
           • Otherwise: create cycle + schedule Reminder 1 (do NOT send yet).

        2. force_reminder=True — the scheduler picked up a due reminder.
           • Execute the reminder: render email, add work note, return to ON_HOLD.
        """
        incident = await self.incident_service.get_incident(incident_id)
        existing_cycle = await self.cycle_svc.get_active_cycle(incident_id)

        # ------------------------------------------------------------------
        # Path A: Idempotency gate — preserve existing cycle
        # ------------------------------------------------------------------
        if existing_cycle and not force_reminder:
            logger.info(
                "[PendingService] Active cycle %s exists for %s. Preserving.",
                existing_cycle.id, incident.incident_number,
            )
            if incident.state not in ("on_hold", "pending"):
                await self.incident_service.update_incident_internal(
                    incident.id, IncidentUpdate(state="on_hold")
                )
            return self._preserved_response(incident, existing_cycle)

        # ------------------------------------------------------------------
        # Path B: Schedule Reminder 1 (no active cycle, force_reminder=False)
        # ------------------------------------------------------------------
        if not existing_cycle and not force_reminder:
            return await self._schedule_first_reminder(incident)

        # ------------------------------------------------------------------
        # Path C: Execute a scheduled reminder (force_reminder=True)
        # ------------------------------------------------------------------
        return await self._execute_reminder(incident, existing_cycle)

    # ------------------------------------------------------------------
    # Private: Path B — schedule Reminder 1
    # ------------------------------------------------------------------

    async def _schedule_first_reminder(self, incident) -> AgentResponse:
        """
        Create the PendingCycle and schedule Reminder 1.
        The reminder is NOT sent here — the scheduler picks it up when due.
        """
        # create_cycle_if_not_exists is idempotent; returns existing if one appeared
        # concurrently.
        cycle = await self.cycle_svc.create_cycle_if_not_exists(
            incident_id=incident.id,
            max_reminders=3,
        )

        # Schedule Reminder 1 by setting next_reminder_at = now + interval.
        # increment_reminder advances reminder_count 0 → 1 and stores
        # next_reminder_at so the scheduler knows when to fire.
        next_due = datetime.now(timezone.utc) + timedelta(seconds=REMINDER_INTERVAL_SECONDS)
        cycle = await self.cycle_svc.increment_reminder(
            cycle.id,
            next_reminder_at=next_due,
        )

        logger.info(
            "[PendingService] Scheduled Reminder 1 for %s at %s (cycle %s).",
            incident.incident_number, next_due.isoformat(), cycle.id,
        )

        # Ensure incident stays in on_hold while waiting.
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
            cycle_status=PendingCycleStatus.ACTIVE,
            reminder_count=cycle.reminder_count,
            max_reminders=cycle.max_reminders,
            is_caller_action_required=True,
            action_taken="REMINDER_SCHEDULED",
            email_sent=False,
            next_reminder_at=cycle.next_reminder_at,
        )
        return AgentResponse(
            success=True,
            agent_name="PendingAgent",
            reasoning=(
                f"Reminder 1 of {cycle.max_reminders} scheduled for "
                f"{incident.incident_number} at {next_due.isoformat()}."
            ),
            result=res.model_dump(),
        )

    # ------------------------------------------------------------------
    # Private: Path C — execute a due reminder
    # ------------------------------------------------------------------

    async def _execute_reminder(self, incident, existing_cycle) -> AgentResponse:
        """
        Execute the reminder that the scheduler determined is due.
        If existing_cycle is None at this point the cycle was cancelled/completed
        between the scheduler's query and this call — return safely.

        Guard: if reminder_count >= max_reminders when we arrive here, the cycle
        has already reached its limit (e.g. a stale scheduler job, a race, or a
        duplicate call).  Complete the cycle without sending anything.
        """
        if not existing_cycle:
            logger.warning(
                "[PendingService] force_reminder=True but no active cycle for %s. "
                "Cycle may have been cancelled. Skipping.",
                incident.incident_number,
            )
            res = PendingResult(
                incident_id=incident.id,
                incident_number=incident.incident_number,
                caller=incident.caller,
                assigned_to=incident.assigned_to,
                assignment_group=incident.assignment_group,
                is_caller_action_required=False,
                action_taken="DISCARDED",
                email_sent=False,
            )
            return AgentResponse(
                success=True,
                agent_name="PendingAgent",
                reasoning="No active cycle found. Reminder skipped.",
                result=res.model_dump(),
            )

        # ------------------------------------------------------------------
        # Guard: reminder_count already EXCEEDS max_reminders — this means more
        # reminders were somehow logged than allowed (should never happen in normal
        # flow, but defends against stale scheduler jobs or duplicate calls).
        # When count == max_reminders, that means the final reminder is DUE to be
        # sent now — allow it through so it can execute and complete the cycle.
        # ------------------------------------------------------------------
        if existing_cycle.reminder_count > existing_cycle.max_reminders:
            logger.info(
                "[PendingService] Cycle %s for %s has already sent %d/%d reminders. "
                "Completing cycle without sending another reminder.",
                existing_cycle.id, incident.incident_number,
                existing_cycle.reminder_count, existing_cycle.max_reminders,
            )
            try:
                await self.cycle_svc.complete_cycle(existing_cycle.id)
            except Exception as exc:
                logger.warning(
                    "[PendingService] Could not complete already-exhausted cycle %s: %s",
                    existing_cycle.id, exc,
                )
            res = PendingResult(
                incident_id=incident.id,
                incident_number=incident.incident_number,
                caller=incident.caller,
                assigned_to=incident.assigned_to,
                assignment_group=incident.assignment_group,
                cycle_id=existing_cycle.id,
                cycle_status=PendingCycleStatus.COMPLETED,
                reminder_count=existing_cycle.reminder_count,
                max_reminders=existing_cycle.max_reminders,
                is_caller_action_required=False,
                action_taken="DISCARDED",
                email_sent=False,
            )
            return AgentResponse(
                success=True,
                agent_name="PendingAgent",
                reasoning=(
                    f"Max reminders ({existing_cycle.max_reminders}) already sent "
                    f"for {incident.incident_number}. Cycle completed."
                ),
                result=res.model_dump(),
            )

        # The reminder_count stored on the cycle IS the reminder number to send now.
        # Reminder 1 was scheduled with count=1, Reminder 2 with count=2, etc.
        reminder_tier = existing_cycle.reminder_count

        # ------------------------------------------------------------------
        # 1. Fetch work-note context + LLM analysis
        # ------------------------------------------------------------------
        latest_notes = await self.work_note_svc.get_notes(incident_id=incident.id, limit=15)
        top_two = latest_notes[:2]

        prior_substantive = None
        for n in latest_notes:
            if n.action_type not in (WorkNoteActionType.STATE_CHANGE, WorkNoteActionType.INCIDENT_UPDATE):
                prior_substantive = n
                break

        formatted_notes = []
        source_names = []
        for idx, n in enumerate(top_two):
            label = "Latest Note" if idx == 0 else "Previous Note"
            formatted_notes.append(
                f"[{label} - {n.source_name} ({n.source_type})]:\n{n.message}"
            )
            if n.source_name not in source_names:
                source_names.append(n.source_name)

        if prior_substantive and prior_substantive not in top_two:
            formatted_notes.append(
                f"[Context Note - {prior_substantive.source_name} ({prior_substantive.source_type})]:\n"
                f"{prior_substantive.message}"
            )
            if prior_substantive.source_name not in source_names:
                source_names.append(prior_substantive.source_name)

        combined_notes_str = (
            "\n\n".join(formatted_notes) if formatted_notes
            else (incident.description or "")
        )
        primary_source = (
            ", ".join(source_names) if source_names
            else (incident.assigned_to or "Engineer")
        )

        incident_context_str = (
            f"Ticket: {incident.incident_number} | "
            f"Title: {incident.short_description} | "
            f"Description: {incident.description or incident.short_description} | "
            f"Assigned: {incident.assigned_to} ({incident.assignment_group})"
        )
        analysis = await self.analyzer.analyze(
            latest_work_note=combined_notes_str,
            source_name=primary_source,
            incident_context=incident_context_str,
        )

        awaiting_detail = analysis.reasoning
        if not awaiting_detail or awaiting_detail.strip() == "" or not analysis.is_caller_action_required:
            awaiting_detail = (
                f"Awaiting caller response and confirmation regarding "
                f"'{incident.short_description}'."
                if incident.short_description
                else "Awaiting requested details and confirmation from caller to proceed."
            )

        # ------------------------------------------------------------------
        # 2. Advance cycle state.
        #
        # Non-final reminder (reminder_tier < max_reminders):
        #   → increment_reminder: count stays as-is but next_reminder_at is set
        #     so the scheduler knows when to fire the next reminder.
        #   Wait — actually reminder_count was already incremented during scheduling.
        #   We do NOT increment again here for "sending"; instead we schedule the
        #   NEXT reminder by setting next_reminder_at on the current count.
        #   But to schedule Reminder N+1 we need to increment count to N+1.
        #   So the pattern is: execute Reminder N (count=N), then increment to N+1.
        #
        # Final reminder (reminder_tier >= max_reminders):
        #   → complete_cycle: mark COMPLETED, clear next_reminder_at.
        #   Do NOT call increment_reminder — that would push count past max.
        # ------------------------------------------------------------------
        is_final = reminder_tier >= existing_cycle.max_reminders

        if not is_final:
            # Schedule the next reminder anchored to the PREVIOUS scheduled time,
            # not to wall-clock time after execution.  This prevents interval drift
            # caused by LLM/notification/work-note execution time.
            # e.g. if Reminder 1 was scheduled at T+10s, Reminder 2 fires at T+20s
            # regardless of how long Reminder 1's execution took.
            previous_scheduled = existing_cycle.next_reminder_at
            if previous_scheduled is not None:
                next_due = previous_scheduled + timedelta(seconds=REMINDER_INTERVAL_SECONDS)
            else:
                # Fallback only if next_reminder_at is unexpectedly None
                next_due = datetime.now(timezone.utc) + timedelta(seconds=REMINDER_INTERVAL_SECONDS)
            cycle = await self.cycle_svc.increment_reminder(
                existing_cycle.id,
                next_reminder_at=next_due,
            )
            cycle_completed = False
        else:
            # Final reminder: complete the cycle so no more reminders can fire.
            # Use complete_cycle() — this sets status=COMPLETED and clears
            # next_reminder_at, making the cycle invisible to the scheduler and
            # to get_active_cycle() for all future calls.
            cycle = await self.cycle_svc.complete_cycle(existing_cycle.id)
            cycle_completed = True
            logger.info(
                "[PendingService] Final reminder (%d/%d) for %s. Cycle %s COMPLETED.",
                reminder_tier, existing_cycle.max_reminders,
                incident.incident_number, existing_cycle.id,
            )

        # ------------------------------------------------------------------
        # 3. Render email
        # ------------------------------------------------------------------
        render_ctx = {
            "ticket_number": incident.incident_number,
            "caller_name": incident.caller or "Valued Employee",
            "short_description": incident.short_description or "",
            "assignment_group": incident.assignment_group or "Support Team",
            "assigned_engineer_name": incident.assigned_to or "Assigned Support Engineer",
            "reminder_count": reminder_tier,
            "max_reminders": cycle.max_reminders,
            "is_final": is_final,
            "awaiting_detail": awaiting_detail,
        }
        email_text = self.renderer.render_plain_text_email(render_ctx)

        # ------------------------------------------------------------------
        # 4. Add work note via WorkNoteService.
        #    auto_activate=True is intentional: WorkNoteService's existing
        #    ON_HOLD → ACTIVE behavior must NOT be suppressed.
        # ------------------------------------------------------------------
        note_msg = (
            f"Pending Agent: Reminder {reminder_tier} of {cycle.max_reminders} sent to user.\n"
            f"• Cycle ID: {cycle.id}\n"
            f"• Awaiting from User: {awaiting_detail}\n"
            f"• Follow-up Status: "
            f"{'Cycle Max Reminders Sent' if cycle_completed else 'Awaiting User Response'}\n"
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

        # ------------------------------------------------------------------
        # 5. Return incident to ON_HOLD.
        #    WorkNoteService may have auto-activated the incident
        #    (ON_HOLD → ACTIVE/IN_PROGRESS).  Explicitly restore ON_HOLD now.
        # ------------------------------------------------------------------
        await self.incident_service.update_incident_internal(
            incident.id, IncidentUpdate(state="on_hold")
        )
        logger.info(
            "[PendingService] Reminder %d/%d sent for %s. Incident returned to on_hold.",
            reminder_tier, cycle.max_reminders, incident.incident_number,
        )

        res = PendingResult(
            incident_id=incident.id,
            incident_number=incident.incident_number,
            caller=incident.caller,
            assigned_to=incident.assigned_to,
            assignment_group=incident.assignment_group,
            cycle_id=cycle.id,
            cycle_status=PendingCycleStatus.COMPLETED if cycle_completed else PendingCycleStatus.ACTIVE,
            reminder_count=reminder_tier,  # the reminder that was just sent
            max_reminders=existing_cycle.max_reminders,
            is_caller_action_required=True,
            action_taken="CYCLE_COMPLETED" if cycle_completed else "REMINDER_SENT",
            email_sent=True,
            delivery_status="simulated_success",
            work_notes_added=note_msg,
            next_reminder_at=cycle.next_reminder_at if not cycle_completed else None,
        )
        return AgentResponse(
            success=True,
            agent_name="PendingAgent",
            reasoning=(
                f"Reminder {reminder_tier} of {cycle.max_reminders} sent. "
                f"Ticket returned to ON_HOLD."
            ),
            confidence=analysis.confidence,
            result=res.model_dump(),
        )

    # ------------------------------------------------------------------
    # Private: response builders
    # ------------------------------------------------------------------

    @staticmethod
    def _preserved_response(incident, cycle) -> AgentResponse:
        res = PendingResult(
            incident_id=incident.id,
            incident_number=incident.incident_number,
            caller=incident.caller,
            assigned_to=incident.assigned_to,
            assignment_group=incident.assignment_group,
            cycle_id=cycle.id,
            cycle_status=PendingCycleStatus.ACTIVE,
            reminder_count=cycle.reminder_count,
            max_reminders=cycle.max_reminders,
            is_caller_action_required=True,
            action_taken="CYCLE_PRESERVED",
            email_sent=False,
            next_reminder_at=cycle.next_reminder_at,
        )
        return AgentResponse(
            success=True,
            agent_name="PendingAgent",
            reasoning=(
                f"Active cycle {cycle.id} is already in progress "
                f"(Reminder {cycle.reminder_count}/{cycle.max_reminders}). "
                f"Cycle preserved."
            ),
            result=res.model_dump(),
        )
