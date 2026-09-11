"""
Resolution Service — orchestrates the full ON_HOLD → ACTIVE resolution workflow.

Flow
~~~~
1.  Validate trigger (previous_state == on_hold AND current_state == active).
1b. Fast-path source gate: if triggering_work_note_source is not USER, IGNORE.
2.  Fetch incident.
3.  Load triggering work note (by ID if provided; else get_latest).
4.  Guard: note source must be USER.
5.  Build AIContext (for engineer email resolution).
6.  Fetch ACK/Pending context notes for LLM.
7.  Run ResolutionAgent via LLM.
8.  If LLM fails → write audit work note, return safe failure result.
9.  Check provenance (ACKNOWLEDGEMENT_AGENT or PENDING_AGENT work notes).
    Engineer-manually-pended tickets have no such notes → provenance=False → no auto-resolve.
10. Build notification message.
11. Send Teams notification to assigned engineer.
12. If resolution-positive → send Email to assignment group.
13. If resolution-positive AND provenance eligible:
      a. Cancel active PendingCycle (only here — not earlier).
      b. Auto-resolve incident.
14. Write top-level audit work note.
15. Return ResolutionResult inside AgentResponse.

PendingCycle Cancellation Rule
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The active PendingCycle is cancelled ONLY when ALL of these are true:
  • Triggering work note source == USER (step 1b / step 4)
  • Provenance confirmed (ACK or Pending workflow history present)
  • LLM intent is resolution-positive (ISSUE_RESOLVED / REQUEST_COMPLETED / REQUIRED_ACTION_COMPLETED)

A state transition alone, a PENDING_AGENT note, or a non-positive USER response
must NEVER cancel the PendingCycle.

Rules
~~~~~
* No direct DB access — all data goes through Services.
* No direct notification calls — all channels go through NotificationService.
* NotificationService creates its own work notes; no duplicates here.
* WorkNoteService.add_note() is used only for agent audit notes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_platform.services.llm_service import LLMService
from app.integrations.notifications.schemas import (
    NotificationChannel,
    NotificationRequest,
    NotificationResult,
)
from app.integrations.notifications.service import NotificationService
from app.modules.agents.base.request import AgentRequest
from app.modules.agents.base.response import AgentResponse
from app.modules.agents.resolution.agent import ResolutionAgent
from app.modules.agents.resolution.schemas import (
    LLMAnalysis,
    NotificationOutcome,
    ResolutionAction,
    ResolutionResult,
    ResolutionTrigger,
    ResolutionIntent,
    RESOLUTION_POSITIVE_INTENTS,
)
from app.modules.context.service import ContextService
from app.modules.context.schemas import AIContext
from app.modules.incidents.schemas import IncidentUpdate
from app.modules.incidents.service import IncidentService
from app.modules.pending_cycles.service import PendingCycleService
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType
from app.modules.work_notes.service import WorkNoteService

logger = logging.getLogger(__name__)

_AGENT_NAME = "ResolutionAgent"
_AGENT_SOURCE_TYPE = WorkNoteSourceType.SYSTEM.value   # generic source for audit notes
_ON_HOLD_STATE = "on_hold"   # the eligible previous state for this agent
_ACTIVE_STATE = "active"     # trigger contract string (not an IncidentState enum value)
_RESOLVED_STATE = "resolved"

# WorkNote sources that indicate the acknowledgement/reminder pending workflow
_PROVENANCE_SOURCES = {
    WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT.value,
    WorkNoteSourceType.PENDING_AGENT.value,
}


class ResolutionService:
    """
    Orchestrates the Resolution Agent workflow for ON_HOLD → ACTIVE transitions.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.incident_service = IncidentService(db)
        self.context_service = ContextService(db)
        self.work_note_svc = WorkNoteService(db)
        self.pending_cycle_svc = PendingCycleService(db)
        self.notification_svc = NotificationService(db)
        self.agent = ResolutionAgent()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def process(self, trigger: ResolutionTrigger) -> AgentResponse:
        """
        Main entry point.  Accepts a ResolutionTrigger and returns AgentResponse.
        Never raises — all errors are returned as structured failure responses.
        """
        incident_id = trigger.incident_id

        # --- Step 1: Validate trigger ---
        if not self._is_eligible_transition(trigger):
            reason = (
                f"Transition {trigger.previous_state!r} → {trigger.current_state!r} "
                f"is not eligible (requires on_hold → active)."
            )
            logger.info("[ResolutionService] %s %s", incident_id, reason)
            return self._ignored_response(
                incident_id=incident_id,
                incident_number=incident_id,
                trigger=trigger,
                reason=reason,
            )

        # --- Step 1b: Source eligibility gate (fast path, no DB needed) ---
        # Only a USER work note is a valid trigger for Resolution analysis.
        # PENDING_AGENT, ACKNOWLEDGEMENT_AGENT, ENGINEER, SYSTEM, and any other
        # source must be ignored immediately — they are not customer responses.
        # This check uses the source passed on the trigger (set by IncidentService
        # from WorkNoteService.add_note's source_type).
        # For manual state changes (triggering_work_note_source is None), we allow
        # the flow to continue to step 3 where the latest note will be inspected.
        if trigger.triggering_work_note_source is not None:
            if trigger.triggering_work_note_source != WorkNoteSourceType.USER.value:
                reason = (
                    f"Transition was caused by a '{trigger.triggering_work_note_source}' "
                    f"work note — only USER work notes trigger Resolution analysis."
                )
                logger.info(
                    "[ResolutionService] %s %s",
                    incident_id, reason,
                )
                return self._ignored_response(
                    incident_id=incident_id,
                    incident_number=incident_id,
                    trigger=trigger,
                    reason=reason,
                    latest_wn_source=trigger.triggering_work_note_source,
                )

        # --- Step 2: Fetch incident ---
        try:
            incident = await self.incident_service.get_incident(incident_id)
        except Exception as exc:
            return self._error_response(
                incident_id=incident_id,
                error=f"Failed to fetch incident: {exc}",
                trigger=trigger,
            )

        # --- Step 3: Load the triggering work note ---
        # When the trigger carries a specific note ID (work-note-driven activation),
        # load that note directly.  This prevents the SYSTEM STATE_CHANGE audit note
        # written immediately after activation from being mistaken for the user's
        # response.
        # When no ID is provided (manual state change), fall back to get_latest().
        try:
            if trigger.triggering_work_note_id:
                triggering_note = await self.work_note_svc.get_note_by_id(
                    trigger.triggering_work_note_id
                )
                if triggering_note is None:
                    # Note ID provided but note not found — fall back to latest.
                    logger.warning(
                        "[ResolutionService] %s Triggering work note %s not found — "
                        "falling back to get_latest().",
                        incident.incident_number,
                        trigger.triggering_work_note_id,
                    )
                    triggering_note = await self.work_note_svc.get_latest(incident.id)
            else:
                triggering_note = await self.work_note_svc.get_latest(incident.id)
        except Exception as exc:
            return self._error_response(
                incident_id=incident.id,
                error=f"Failed to retrieve work notes: {exc}",
                trigger=trigger,
                incident_number=incident.incident_number,
            )

        latest_note = triggering_note  # alias — rest of the method uses latest_note

        if not latest_note:
            reason = "No work notes found — cannot determine user response."
            logger.info("[ResolutionService] %s %s", incident.incident_number, reason)
            await self._write_audit_note(
                incident_id=incident.id,
                message=f"Resolution Agent: {reason}",
            )
            return self._ignored_response(
                incident_id=incident.id,
                incident_number=incident.incident_number,
                trigger=trigger,
                reason=reason,
                latest_wn_source=None,
            )

        # --- Step 4: Guard — triggering note must be from USER ---
        # The source gate in Step 1b already handles work-note-driven triggers.
        # This step is a defence-in-depth check for the manual-state-change path
        # (where triggering_work_note_source is None and we fell back to get_latest).
        # In that fallback, the latest note might be a SYSTEM, PENDING_AGENT, or
        # other non-USER note — which we must also reject.
        if latest_note.source_type != WorkNoteSourceType.USER.value:
            reason = (
                f"Triggering work note source is '{latest_note.source_type}' — "
                f"only USER work notes trigger Resolution analysis."
            )
            logger.info("[ResolutionService] %s %s", incident.incident_number, reason)
            await self._write_audit_note(
                incident_id=incident.id,
                message=f"Resolution Agent ignored: {reason}",
            )
            return self._ignored_response(
                incident_id=incident.id,
                incident_number=incident.incident_number,
                trigger=trigger,
                reason=reason,
                latest_wn_source=latest_note.source_type,
            )

        # --- Step 4b: USER responded — cancel the active PendingCycle ---
        # The cycle's purpose was "waiting for user response".  Now that a USER
        # work note has been confirmed, the waiting is over regardless of whether
        # auto-resolution will be performed.  Cancelling here prevents stale
        # reminders from firing while Resolution analysis is running and after.
        # If no active cycle exists (e.g. already cancelled by a prior run), this
        # is a no-op.
        cancelled_cycle = None
        try:
            cancelled_cycle = await self.pending_cycle_svc.cancel_active_cycle(incident.id)
            if cancelled_cycle:
                logger.info(
                    "[ResolutionService] PendingCycle %s cancelled for %s — "
                    "user has responded.",
                    cancelled_cycle.id, incident.incident_number,
                )
        except Exception as cancel_exc:
            logger.warning(
                "[ResolutionService] PendingCycle cancellation failed for %s: %s",
                incident.incident_number, cancel_exc,
            )

        # --- Step 5: Build AIContext (for engineer emails) ---
        context: AIContext | None = None
        try:
            context = await self.context_service.build_for_incident(incident.id)
        except Exception as exc:
            logger.warning(
                "[ResolutionService] AIContext build failed for %s: %s — "
                "will proceed without engineer email resolution.",
                incident.incident_number, exc,
            )

        # --- Step 7: Run ResolutionAgent (LLM analysis) ---
        # Inject the user response text and workflow context via transient attributes
        # on context so the agent stays pure (no DB access).
        user_response_text = latest_note.message

        # Build acknowledgement context for the LLM — find the most recent
        # ACKNOWLEDGEMENT_AGENT work note to understand what was requested.
        acknowledgement_context: str | None = None
        pending_reminder_count: int | None = None
        try:
            ack_notes = await self.work_note_svc.get_by_source_type(
                incident.id, WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT
            )
            if ack_notes:
                # Most recent ACK note is first (desc order)
                acknowledgement_context = ack_notes[0].message[:500]  # cap length

            pending_notes = await self.work_note_svc.get_by_source_type(
                incident.id, WorkNoteSourceType.PENDING_AGENT
            )
            if pending_notes:
                pending_reminder_count = len(pending_notes)
        except Exception as exc:
            logger.warning(
                "[ResolutionService] Could not fetch workflow context notes for %s: %s",
                incident.incident_number, exc,
            )

        agent_response = await self._run_agent(
            context=context,
            incident=incident,
            user_response_text=user_response_text,
            acknowledgement_context=acknowledgement_context,
            pending_reminder_count=pending_reminder_count,
        )

        llm_failed = not agent_response.success
        llm_error: str | None = None
        analysis: LLMAnalysis | None = None

        if llm_failed:
            llm_error = "; ".join(agent_response.errors) if agent_response.errors else "LLM error"
            logger.error(
                "[ResolutionService] LLM failed for %s: %s",
                incident.incident_number, llm_error,
            )
            await self._write_audit_note(
                incident_id=incident.id,
                message=(
                    f"Resolution Agent LLM analysis failed for {incident.incident_number}.\n"
                    f"Error: {llm_error}\n"
                    f"Action: No auto-resolution performed. Manual engineer review required."
                ),
            )
            result = ResolutionResult(
                incident_id=incident.id,
                incident_number=incident.incident_number,
                previous_state=trigger.previous_state,
                current_state=trigger.current_state,
                trigger_eligible=True,
                trigger_reason="Trigger accepted",
                latest_work_note_source=latest_note.source_type,
                work_note_eligible=True,
                pending_cycle_cancelled=cancelled_cycle is not None,
                pending_cycle_id=cancelled_cycle.id if cancelled_cycle else None,
                llm_failed=True,
                llm_error=llm_error,
                action=ResolutionAction.FAILED,
                action_reason=f"LLM analysis failed: {llm_error}",
            )
            return AgentResponse(
                success=False,
                agent_name=_AGENT_NAME,
                errors=[llm_error],
                result=result.model_dump(),
            )
        else:
            analysis = LLMAnalysis(**agent_response.result["llm_analysis"])

        # --- Step 8: Check provenance ---
        provenance_eligible, provenance_reason = await self._check_provenance(incident.id)

        # --- Step 9: Build notification body ---
        is_resolution_positive = analysis.intent in RESOLUTION_POSITIVE_INTENTS
        notif_body = self._build_notification_body(
            incident_number=incident.incident_number,
            analysis=analysis,
            positive=is_resolution_positive,
        )
        notif_subject = (
            f"{'[RESOLVED] ' if is_resolution_positive else '[ACTION REQUIRED] '}"
            f"Customer response received — {incident.incident_number}"
        )

        notifications: list[NotificationOutcome] = []

        # --- Step 10: Teams → assigned engineer ---
        engineer_email = self._resolve_engineer_email(
            assigned_to=incident.assigned_to,
            context=context,
        )
        teams_outcome = await self._send_teams(
            incident_id=incident.id,
            incident_number=incident.incident_number,
            recipient=engineer_email,
            message=notif_body,
        )
        notifications.append(teams_outcome)

        # --- Step 11: Email → assignment group (resolution-positive only) ---
        if is_resolution_positive:
            group_emails = self._resolve_group_emails(context=context)
            email_outcome = await self._send_email(
                incident_id=incident.id,
                incident_number=incident.incident_number,
                recipients=group_emails,
                subject=notif_subject,
                message=notif_body,
            )
            notifications.append(email_outcome)

        # --- Step 12 + 13: Auto-resolve if eligible ---
        # Requires: resolution-positive intent AND provenance (ACK/Pending workflow)
        auto_resolved = False
        action = ResolutionAction.NOTIFIED
        action_reason = "Engineer/group notified."

        if is_resolution_positive and provenance_eligible:
            try:
                await self.incident_service.update_incident_internal(
                    incident.id,
                    IncidentUpdate(state=_RESOLVED_STATE),
                )
                await self._write_audit_note(
                    incident_id=incident.id,
                    message=(
                        f"Resolution Agent: Incident {incident.incident_number} automatically resolved.\n"
                        f"Reason: User confirmed {analysis.intent.value} via acknowledgement/reminder workflow.\n"
                        f"Confidence: {analysis.confidence:.2f}\n"
                        f"Summary: {analysis.summary}"
                    ),
                    action_type=WorkNoteActionType.STATE_CHANGE,
                )
                auto_resolved = True
                action = ResolutionAction.AUTO_RESOLVED
                action_reason = (
                    f"Auto-resolved: intent={analysis.intent.value}, "
                    "acknowledgement/reminder workflow provenance confirmed."
                )
                logger.info(
                    "[ResolutionService] Auto-resolved %s (intent=%s)",
                    incident.incident_number, analysis.intent.value,
                )
            except Exception as exc:
                logger.error(
                    "[ResolutionService] Auto-resolve state change failed for %s: %s",
                    incident.incident_number, exc,
                )
                action_reason = f"Notifications sent but auto-resolve failed: {exc}"

        elif is_resolution_positive and not provenance_eligible:
            action_reason = (
                f"Intent {analysis.intent.value} detected but provenance not confirmed — "
                "notified engineer/group, no auto-resolve."
            )
            await self._write_audit_note(
                incident_id=incident.id,
                message=(
                    f"Resolution Agent: {analysis.intent.value} detected for {incident.incident_number} "
                    f"but provenance not confirmed ({provenance_reason}). "
                    f"No automatic state change performed. Manual engineer review required."
                ),
            )
        else:
            action_reason = (
                f"User response intent is {analysis.intent.value} — "
                "engineer notified, no state change."
            )
            await self._write_audit_note(
                incident_id=incident.id,
                message=(
                    f"Resolution Agent: Response intent={analysis.intent.value} for {incident.incident_number}.\n"
                    f"Summary: {analysis.summary}\n"
                    f"Next best action: {analysis.next_best_action}\n"
                    f"Confidence: {analysis.confidence:.2f}"
                ),
            )

        # --- Step 14: Build final result ---
        result = ResolutionResult(
            incident_id=incident.id,
            incident_number=incident.incident_number,
            previous_state=trigger.previous_state,
            current_state=trigger.current_state,
            trigger_eligible=True,
            trigger_reason="Trigger accepted: on_hold → active",
            latest_work_note_source=latest_note.source_type,
            work_note_eligible=True,
            pending_cycle_cancelled=cancelled_cycle is not None,
            pending_cycle_id=cancelled_cycle.id if cancelled_cycle else None,
            llm_analysis=analysis,
            llm_failed=False,
            provenance_eligible=provenance_eligible,
            provenance_reason=provenance_reason,
            notifications=notifications,
            action=action,
            action_reason=action_reason,
        )

        return AgentResponse(
            success=True,
            agent_name=_AGENT_NAME,
            reasoning=analysis.summary,
            confidence=analysis.confidence,
            result=result.model_dump(),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_eligible_transition(trigger: ResolutionTrigger) -> bool:
        """Return True only for on_hold → active."""
        return (
            trigger.previous_state.lower() == _ON_HOLD_STATE
            and trigger.current_state.lower() == _ACTIVE_STATE
        )

    async def _run_agent(
        self,
        context: AIContext | None,
        incident,
        user_response_text: str,
        acknowledgement_context: str | None = None,
        pending_reminder_count: int | None = None,
    ) -> AgentResponse:
        """
        Run the ResolutionAgent.  If no context is available, build a
        minimal stub context so the agent can still call the LLM.
        """
        from app.modules.context.schemas import IncidentContext

        if context is None:
            from datetime import date

            inc_ctx = IncidentContext(
                incident_id=incident.id,
                incident_number=incident.incident_number,
                short_description=incident.short_description,
                description=incident.description,
                priority=incident.priority,
                state=incident.state,
                category=incident.category,
                subcategory=incident.subcategory,
                assignment_group=incident.assignment_group,
                assigned_to=incident.assigned_to,
                caller=incident.caller,
                created_at=incident.created_at,
            )
            context = AIContext(
                incident=inc_ctx,
                engineers=[],
                context_date=datetime.now(timezone.utc).date(),
                created_at=datetime.now(timezone.utc),
            )

        # Inject metadata as transient attributes — keeps the agent pure
        object.__setattr__(context, "_user_response_text", user_response_text)
        if acknowledgement_context is not None:
            object.__setattr__(context, "_acknowledgement_context", acknowledgement_context)
        if pending_reminder_count is not None:
            object.__setattr__(context, "_pending_reminder_count", pending_reminder_count)

        request = AgentRequest(context=context)
        return await self.agent.run(request)

    # The marker written by AcknowledgementService into the work note message
    # for the standard (non-qualifying) template.
    _STANDARD_ACK_TEMPLATE_MARKER = "• Selected Template: standard_ack.html"

    async def _check_provenance(self, incident_id: str) -> tuple[bool, str]:
        """
        Determine whether this incident qualifies for automatic resolution.

        Strict eligibility requires ALL of the following:

        1. An ACKNOWLEDGEMENT_AGENT work note exists for this incident that used
           a NON-STANDARD template (anything other than standard_ack.html).
           Standard acknowledgements do NOT qualify.
           Engineer-manually-pended tickets have no ACK note → fail here.

        2. No ENGINEER work note exists in the incident history AFTER the
           qualifying ACK note.  Engineer intervention (adding notes, guiding
           the user, manually changing state) after the ACK workflow began
           invalidates automatic resolution eligibility — a human took over.

        3. A PENDING_AGENT work note is NOT required — Scenario 1 (direct ACK
           response) qualifies even without reminders.  Scenario 2 (reminder
           response) is also covered because the original ACK note still exists.

        Returns (eligible: bool, reason: str).
        """
        # --- 1. Check for a qualifying (non-standard) ACK note ---
        ack_notes = []
        try:
            ack_notes = await self.work_note_svc.get_by_source_type(
                incident_id, WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT
            )
        except Exception as exc:
            logger.warning(
                "[ResolutionService] Provenance check: ACK note fetch failed: %s", exc,
            )

        if not ack_notes:
            return (
                False,
                "No ACKNOWLEDGEMENT_AGENT work notes found — "
                "incident was not processed through the ACK workflow.",
            )

        # Find the most recent non-standard ACK note
        # (list is ordered desc — newest first)
        qualifying_ack = None
        for note in ack_notes:
            if not self._is_standard_ack_note(note):
                qualifying_ack = note
                break

        if qualifying_ack is None:
            return (
                False,
                "ACKNOWLEDGEMENT_AGENT work note found but it used the standard template "
                "(standard_ack.html) — standard acknowledgements do not request a specific "
                "user action and are not eligible for automatic resolution.",
            )

        # --- 2. Check for engineer intervention AFTER the qualifying ACK note ---
        # Fetch all work notes ordered desc (newest first).  Any ENGINEER note
        # that is newer than the qualifying ACK note means an engineer intervened
        # after the ACK workflow started — automatic resolution is blocked.
        engineer_intervention = False
        engineer_intervention_reason = ""
        try:
            all_notes = await self.work_note_svc.get_notes(incident_id, limit=100)
            ack_created_at = getattr(qualifying_ack, "created_at", None)

            for note in all_notes:
                note_source = getattr(note, "source_type", "")
                note_source_val = note_source.value if hasattr(note_source, "value") else str(note_source)
                note_created_at = getattr(note, "created_at", None)

                if note_source_val != WorkNoteSourceType.ENGINEER.value:
                    continue

                # Skip engineer notes that predate or coincide with the ACK note
                # (e.g. the initial assignment).  Only flag those that came after.
                if ack_created_at is not None and note_created_at is not None:
                    if note_created_at <= ack_created_at:
                        continue

                engineer_intervention = True
                engineer_intervention_reason = (
                    f"Engineer work note found after qualifying ACK "
                    f"(engineer intervened in the workflow history)."
                )
                logger.info(
                    "[ResolutionService] Engineer intervention detected for %s after ACK.",
                    incident_id,
                )
                break

        except Exception as exc:
            logger.warning(
                "[ResolutionService] Provenance check: engineer-intervention scan failed: %s",
                exc,
            )

        if engineer_intervention:
            return False, engineer_intervention_reason

        # --- 3. Optionally note if Pending Agent reminders were also sent ---
        pending_info = ""
        try:
            pending_notes = await self.work_note_svc.get_by_source_type(
                incident_id, WorkNoteSourceType.PENDING_AGENT
            )
            if pending_notes:
                pending_info = f" + {len(pending_notes)} PENDING_AGENT reminder(s) confirmed."
        except Exception as exc:
            logger.warning(
                "[ResolutionService] Provenance check: PENDING_AGENT fetch failed: %s", exc,
            )

        return (
            True,
            f"Provenance confirmed: non-standard ACK template used (ACK workflow eligible){pending_info}",
        )

    @staticmethod
    def _is_standard_ack_note(note) -> bool:
        """
        Return True when the ACK work note used the standard (non-qualifying) template.

        The AcknowledgementService embeds the template filename in the message text as:
            "• Selected Template: standard_ack.html"

        Any other template (salesforce_incorrect_request.html, wrong_ticket_access.html,
        wrong_ticket_service_catalog.html, wrong_org_environment.html) is non-standard
        and qualifies for the Resolution workflow.

        If the marker is absent (e.g. very old notes before this format was introduced),
        we treat the note as non-standard (eligible) so as not to break legacy incidents.
        """
        msg = getattr(note, "message", "") or ""
        return ResolutionService._STANDARD_ACK_TEMPLATE_MARKER in msg

    @staticmethod
    def _resolve_engineer_email(
        assigned_to: str | None,
        context: AIContext | None,
    ) -> str | None:
        """
        Find the email of the assigned engineer from AIContext.engineers.
        Returns None if not found.
        """
        if not assigned_to or not context or not context.engineers:
            return None
        name_lower = assigned_to.lower().strip()
        for eng in context.engineers:
            if eng.name.lower().strip() == name_lower:
                return eng.email
        return None

    @staticmethod
    def _resolve_group_emails(context: AIContext | None) -> list[str]:
        """
        Collect all unique engineer emails from AIContext.engineers for the
        assignment group email blast.
        Returns empty list if context is unavailable.
        """
        if not context or not context.engineers:
            return []
        seen: set[str] = set()
        emails: list[str] = []
        for eng in context.engineers:
            if eng.email and eng.email not in seen:
                seen.add(eng.email)
                emails.append(eng.email)
        return emails

    @staticmethod
    def _build_notification_body(
        incident_number: str,
        analysis: LLMAnalysis,
        positive: bool,
    ) -> str:
        """Build the human-readable notification body."""
        header = (
            f"✅ The customer has indicated that the issue appears to be RESOLVED."
            if positive
            else f"⚠️ The customer has responded but the issue may not be resolved."
        )
        lines = [
            f"Incident: {incident_number}",
            "",
            header,
            "",
            "Customer Response Summary:",
            analysis.summary,
            "",
            "Next Best Action:",
            analysis.next_best_action,
            "",
            f"Confidence: {analysis.confidence:.0%}",
        ]
        return "\n".join(lines)

    async def _send_teams(
        self,
        incident_id: str,
        incident_number: str,
        recipient: str | None,
        message: str,
    ) -> NotificationOutcome:
        """Send Teams notification to the assigned engineer."""
        if not recipient:
            reason = f"No Teams recipient — assigned engineer email not found for {incident_number}."
            logger.warning("[ResolutionService] %s", reason)
            await self._write_audit_note(
                incident_id=incident_id,
                message=f"Resolution Agent: {reason}",
            )
            return NotificationOutcome(
                channel="teams",
                success=False,
                recipient="",
                error=reason,
            )

        req = NotificationRequest(
            incident_id=incident_id,
            channel=NotificationChannel.TEAMS,
            recipients=[recipient],
            message=message,
            source_name=_AGENT_NAME,
            source_type=WorkNoteSourceType.SYSTEM.value,
            action_type=WorkNoteActionType.SEND_ACKNOWLEDGEMENT.value,
        )
        result: NotificationResult = await self.notification_svc.send(req)
        return NotificationOutcome(
            channel="teams",
            success=result.success,
            recipient=recipient,
            message_id=result.message_id if result.success else None,
            work_note_id=result.work_note_id,
            error=result.error,
        )

    async def _send_email(
        self,
        incident_id: str,
        incident_number: str,
        recipients: list[str],
        subject: str,
        message: str,
    ) -> NotificationOutcome:
        """Send Email notification to the assignment group."""
        if not recipients:
            reason = f"No Email recipients — assignment group members not found for {incident_number}."
            logger.warning("[ResolutionService] %s", reason)
            await self._write_audit_note(
                incident_id=incident_id,
                message=f"Resolution Agent: {reason}",
            )
            return NotificationOutcome(
                channel="email",
                success=False,
                recipient="",
                error=reason,
            )

        req = NotificationRequest(
            incident_id=incident_id,
            channel=NotificationChannel.EMAIL,
            recipients=recipients,
            subject=subject,
            message=message,
            source_name=_AGENT_NAME,
            source_type=WorkNoteSourceType.SYSTEM.value,
            action_type=WorkNoteActionType.SEND_ACKNOWLEDGEMENT.value,
        )
        result: NotificationResult = await self.notification_svc.send(req)
        return NotificationOutcome(
            channel="email",
            success=result.success,
            recipient=recipients[0],
            message_id=result.message_id if result.success else None,
            work_note_id=result.work_note_id,
            error=result.error,
        )

    async def _write_audit_note(
        self,
        incident_id: str,
        message: str,
        action_type: WorkNoteActionType = WorkNoteActionType.SYSTEM_NOTE,
    ) -> None:
        """Write an audit-only work note.  Errors are logged, not raised."""
        try:
            await self.work_note_svc.add_note(
                incident_id=incident_id,
                message=message,
                source_type=WorkNoteSourceType.SYSTEM,
                source_name=_AGENT_NAME,
                action_type=action_type,
                auto_activate=False,  # audit notes must not trigger state change
            )
        except Exception as exc:
            logger.error(
                "[ResolutionService] Audit work note failed for %s: %s",
                incident_id, exc,
            )

    # ------------------------------------------------------------------
    # Static response builders
    # ------------------------------------------------------------------

    @staticmethod
    def _ignored_response(
        incident_id: str,
        incident_number: str,
        trigger: ResolutionTrigger,
        reason: str,
        latest_wn_source: str | None = None,
    ) -> AgentResponse:
        result = ResolutionResult(
            incident_id=incident_id,
            incident_number=incident_number,
            previous_state=trigger.previous_state,
            current_state=trigger.current_state,
            trigger_eligible=False,
            trigger_reason=reason,
            latest_work_note_source=latest_wn_source,
            work_note_eligible=False,
            action=ResolutionAction.IGNORED,
            action_reason=reason,
        )
        return AgentResponse(
            success=True,   # not an error — expected path
            agent_name=_AGENT_NAME,
            reasoning=reason,
            result=result.model_dump(),
        )

    @staticmethod
    def _error_response(
        incident_id: str,
        error: str,
        trigger: ResolutionTrigger,
        incident_number: str | None = None,
    ) -> AgentResponse:
        result = ResolutionResult(
            incident_id=incident_id,
            incident_number=incident_number or incident_id,
            previous_state=trigger.previous_state,
            current_state=trigger.current_state,
            trigger_eligible=True,
            trigger_reason="Trigger accepted but processing failed",
            action=ResolutionAction.FAILED,
            action_reason=error,
        )
        return AgentResponse(
            success=False,
            agent_name=_AGENT_NAME,
            errors=[error],
            result=result.model_dump(),
        )
