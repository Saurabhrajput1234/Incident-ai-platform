"""
Focused tests for the Pending + Resolution workflow fixes.

Items under test (from spec)
-----------------------------
2.  Reminders execute at regular configured intervals (no drift).
    next_reminder_at = previous_next_reminder_at + REMINDER_INTERVAL_SECONDS
    NOT datetime.now() + REMINDER_INTERVAL_SECONDS.

4.  USER response cancels the active PendingCycle — no further reminders.
    When Resolution processes a valid USER work note, cancel_active_cycle()
    is called regardless of whether auto-resolution occurs.

7.  PENDING_AGENT-caused state transition:
    - Resolution IGNORED
    - PendingCycle NOT cancelled by Resolution

8.  Valid ACK non-standard + USER + no engineer intervention:
    - Resolution can proceed, cycle cancelled after validation

9.  ACK/Pending + USER + engineer intervention anywhere after ACK:
    - Resolution MUST NOT auto-resolve
    - provenance_eligible = False

10. Engineer-manually-pended (no ACK note) + USER:
    - Resolution MUST NOT auto-resolve
    - provenance_eligible = False
    (Cycle may still be cancelled because USER responded.)

The engineer-intervention check is timestamp-based:
    ENGINEER notes created AFTER the qualifying ACK note → block resolution
    ENGINEER notes created BEFORE the qualifying ACK note → allow (e.g. initial assignment)
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.modules.agents.pending.service import PendingService, REMINDER_INTERVAL_SECONDS
from app.modules.pending_cycles.enums import PendingCycleStatus
from app.modules.agents.resolution.service import ResolutionService
from app.modules.agents.resolution.schemas import (
    ResolutionAction,
    ResolutionTrigger,
    LLMAnalysis,
    ResolutionIntent,
    RESOLUTION_POSITIVE_INTENTS,
)
from app.modules.agents.base.response import AgentResponse
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType
from app.integrations.notifications.schemas import NotificationResult, NotificationChannel


# ---------------------------------------------------------------------------
# Pending Agent helpers
# ---------------------------------------------------------------------------

def _mock_incident_p(
    inc_id: str = "inc-p-001",
    number: str = "INC0000099",
    state: str = "on_hold",
):
    m = MagicMock()
    m.id = inc_id
    m.incident_number = number
    m.caller = "Alice"
    m.assigned_to = "Bob"
    m.assignment_group = "Support"
    m.state = state
    m.description = "VPN issue"
    m.short_description = "VPN issue"
    return m


def _mock_cycle_p(
    cycle_id: str = "PC-001",
    reminder_count: int = 1,
    max_reminders: int = 3,
    next_reminder_at: datetime | None = None,
    status: str = PendingCycleStatus.ACTIVE.value,
):
    m = MagicMock()
    m.id = cycle_id
    m.incident_id = "inc-p-001"
    m.status = status
    m.reminder_count = reminder_count
    m.max_reminders = max_reminders
    m.next_reminder_at = next_reminder_at
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = datetime.now(timezone.utc)
    return m


def _make_pending_svc() -> PendingService:
    db = AsyncMock()
    svc = PendingService(db)
    svc.incident_service = AsyncMock()
    svc.work_note_svc = AsyncMock()
    svc.cycle_svc = AsyncMock()
    svc.analyzer = AsyncMock()
    svc.work_note_svc.get_notes.return_value = []
    svc.work_note_svc.add_note.return_value = MagicMock()
    svc.incident_service.update_incident_internal = AsyncMock()
    from app.modules.agents.pending.schemas import PendingWorkNoteAnalysis
    svc.analyzer.analyze.return_value = PendingWorkNoteAnalysis(
        is_caller_action_required=True,
        reasoning="Awaiting.",
        confidence=1.0,
    )
    return svc


# ---------------------------------------------------------------------------
# Resolution Agent helpers
# ---------------------------------------------------------------------------

_NONSTANDARD_MARKER = "• Selected Template: wrong_ticket_access.html"
_STANDARD_MARKER = "• Selected Template: standard_ack.html"


def _ack_note(marker: str, created_at: datetime | None = None) -> MagicMock:
    m = MagicMock()
    m.source_type = WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT.value
    m.message = (
        f"Acknowledgement Agent executed.\n"
        f"{marker}\n"
        f"• Status: Incident updated to Pending."
    )
    m.created_at = created_at or datetime.now(timezone.utc)
    return m


def _engineer_note(created_at: datetime | None = None) -> MagicMock:
    m = MagicMock()
    m.source_type = WorkNoteSourceType.ENGINEER.value
    m.message = "Engineer added diagnostic information."
    m.action_type = WorkNoteActionType.MANUAL_NOTE.value
    m.created_at = created_at or datetime.now(timezone.utc)
    return m


def _user_note_r(msg: str = "I submitted the RITM.", created_at: datetime | None = None) -> MagicMock:
    m = MagicMock()
    m.source_type = WorkNoteSourceType.USER.value
    m.message = msg
    m.created_at = created_at or datetime.now(timezone.utc)
    return m


def _llm_resp_r(intent: ResolutionIntent) -> AgentResponse:
    positive = intent in RESOLUTION_POSITIVE_INTENTS
    return AgentResponse(
        success=True,
        agent_name="ResolutionAgent",
        result={"llm_analysis": LLMAnalysis(
            intent=intent, positive_resolution=positive,
            confidence=0.95, summary=intent.value, next_best_action="Review.",
        ).model_dump()},
    )


def _make_resolution_svc(
    user_note_msg: str = "I submitted the RITM.",
    agent_response: AgentResponse | None = None,
    ack_notes: list | None = None,
    all_notes: list | None = None,
) -> ResolutionService:
    """
    Build a mocked ResolutionService.
    all_notes: returned by work_note_svc.get_notes() — used for the
    engineer-intervention scan in _check_provenance().
    """
    from app.modules.context.schemas import AIContext, IncidentContext, EngineerContext

    db = AsyncMock()
    svc = ResolutionService(db)

    inc = MagicMock()
    inc.id = "inc-r-001"
    inc.incident_number = "INC0000001"
    inc.state = "active"
    inc.assigned_to = "Alice"
    inc.assignment_group = "Network Ops"
    inc.short_description = "VPN down"
    inc.description = None
    inc.priority = "3"
    inc.category = "network"
    inc.subcategory = None
    inc.caller = "alice"
    inc.created_at = datetime.now(timezone.utc)

    svc.incident_service = AsyncMock()
    svc.incident_service.get_incident.return_value = inc
    svc.incident_service.update_incident_internal.return_value = inc

    user_wn = _user_note_r(user_note_msg)
    svc.work_note_svc = AsyncMock()
    svc.work_note_svc.get_latest.return_value = user_wn
    svc.work_note_svc.get_note_by_id.return_value = user_wn
    svc.work_note_svc.add_note.return_value = MagicMock(id="audit-1")
    svc.work_note_svc.get_notes.return_value = all_notes or []

    _ack_list = ack_notes if ack_notes is not None else [_ack_note(_NONSTANDARD_MARKER)]

    async def _get_by_source_type(incident_id, source_type):
        val = source_type.value if hasattr(source_type, "value") else str(source_type)
        if val == WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT.value:
            return _ack_list
        if val == WorkNoteSourceType.PENDING_AGENT.value:
            return []
        return []

    svc.work_note_svc.get_by_source_type.side_effect = _get_by_source_type

    svc.pending_cycle_svc = AsyncMock()
    cycle = MagicMock()
    cycle.id = "cycle-r-1"
    svc.pending_cycle_svc.cancel_active_cycle.return_value = cycle

    inc_ctx = IncidentContext(
        incident_id="inc-r-001", incident_number="INC0000001",
        short_description="VPN", description=None, priority="3",
        state="active", category=None, subcategory=None,
        assignment_group="Network Ops", assigned_to="Alice",
        caller="alice", created_at=datetime.now(timezone.utc),
    )
    ctx = AIContext(
        incident=inc_ctx,
        engineers=[EngineerContext(
            engineer_id="e1", name="Alice", email="alice@corp.com",
            assignment_group="Network Ops", level="L2",
            default_shift="S1", current_shift="S1",
            is_available=True, is_shift_active=True,
            roster_date=datetime.now(timezone.utc).date(),
        )],
        context_date=datetime.now(timezone.utc).date(),
        created_at=datetime.now(timezone.utc),
    )
    svc.context_service = AsyncMock()
    svc.context_service.build_for_incident.return_value = ctx

    teams_res = NotificationResult(
        success=True, channel="teams", delivery_status="ok",
        message_id="T-1", recipient="alice@corp.com", message="body", work_note_id="wn-t",
    )
    email_res = NotificationResult(
        success=True, channel="email", delivery_status="ok",
        message_id="E-1", recipient="alice@corp.com", message="body", work_note_id="wn-e",
    )

    async def _send(req):
        return teams_res if req.channel == NotificationChannel.TEAMS else email_res

    svc.notification_svc = AsyncMock()
    svc.notification_svc.send.side_effect = _send

    if agent_response is not None:
        svc.agent = AsyncMock()
        svc.agent.run.return_value = agent_response
        svc.agent.agent_name = "ResolutionAgent"

    return svc


def _trigger_r(source: str | None = "USER") -> ResolutionTrigger:
    return ResolutionTrigger(
        incident_id="inc-r-001",
        previous_state="on_hold",
        current_state="active",
        triggering_work_note_id="wn-001" if source else None,
        triggering_work_note_source=source,
    )


# ===========================================================================
# Item 2 — Reminders execute at regular intervals (no drift)
# ===========================================================================

@pytest.mark.asyncio
async def test_item2_reminder_interval_anchored_to_previous_scheduled_time():
    """
    When Reminder 1 is due, the NEXT reminder must be scheduled at:
        existing_cycle.next_reminder_at + REMINDER_INTERVAL_SECONDS
    NOT at:
        datetime.now() + REMINDER_INTERVAL_SECONDS

    This prevents interval drift caused by LLM/work-note execution time.
    """
    svc = _make_pending_svc()
    svc.incident_service.get_incident.return_value = _mock_incident_p(state="on_hold")

    # Reminder 1 was scheduled at exactly T+10s from cycle creation
    scheduled_time = datetime(2026, 9, 11, 12, 0, 10, tzinfo=timezone.utc)
    cycle_r1 = _mock_cycle_p(cycle_id="PC-DRIFT-001", reminder_count=1, next_reminder_at=scheduled_time)
    svc.cycle_svc.get_active_cycle.return_value = cycle_r1

    # increment_reminder returns a cycle with the next scheduled time
    cycle_r2 = _mock_cycle_p(cycle_id="PC-DRIFT-001", reminder_count=2, max_reminders=3, next_reminder_at=None)
    svc.cycle_svc.increment_reminder.return_value = cycle_r2

    await svc.process_pending_transition(incident_id="inc-p-001", force_reminder=True)

    # Verify increment_reminder was called with next_reminder_at anchored to
    # the PREVIOUS scheduled time (T+10s), not to the current wall-clock time.
    svc.cycle_svc.increment_reminder.assert_called_once()
    call = svc.cycle_svc.increment_reminder.call_args
    actual_next = call.kwargs.get("next_reminder_at") or (call.args[1] if len(call.args) > 1 else None)

    expected_next = scheduled_time + timedelta(seconds=REMINDER_INTERVAL_SECONDS)
    assert actual_next == expected_next, (
        f"Expected next_reminder_at={expected_next.isoformat()}, "
        f"got {actual_next.isoformat() if actual_next else None}. "
        f"Interval drift detected — must anchor to previous scheduled time."
    )


@pytest.mark.asyncio
async def test_item2_reminder_interval_fallback_when_no_previous_time():
    """
    Edge case: if next_reminder_at is unexpectedly None on the cycle,
    the service falls back to now() + interval (no crash).
    """
    svc = _make_pending_svc()
    svc.incident_service.get_incident.return_value = _mock_incident_p(state="on_hold")

    # next_reminder_at is None (edge case — should not normally happen)
    cycle_no_time = _mock_cycle_p(cycle_id="PC-NOTIM-001", reminder_count=1, next_reminder_at=None)
    svc.cycle_svc.get_active_cycle.return_value = cycle_no_time

    cycle_next = _mock_cycle_p(cycle_id="PC-NOTIM-001", reminder_count=2, max_reminders=3)
    svc.cycle_svc.increment_reminder.return_value = cycle_next

    # Should complete without error
    resp = await svc.process_pending_transition(incident_id="inc-p-001", force_reminder=True)

    assert resp.success is True
    svc.cycle_svc.increment_reminder.assert_called_once()
    # next_reminder_at should still be set (not None)
    call = svc.cycle_svc.increment_reminder.call_args
    actual_next = call.kwargs.get("next_reminder_at") or (call.args[1] if len(call.args) > 1 else None)
    assert actual_next is not None


# ===========================================================================
# Item 4 — USER response cancels PendingCycle (stops future reminders)
# ===========================================================================

@pytest.mark.asyncio
async def test_item4_user_response_cancels_pending_cycle():
    """
    When a USER work note triggers Resolution and is confirmed as USER source,
    cancel_active_cycle() is called regardless of whether auto-resolution fires.
    This stops future reminders from executing.
    """
    svc = _make_resolution_svc(
        user_note_msg="I have submitted the RITM.",
        agent_response=_llm_resp_r(ResolutionIntent.REQUEST_COMPLETED),
    )
    result = await svc.process(_trigger_r(source="USER"))

    # Cycle must be cancelled — user has responded, waiting-for-user is over
    svc.pending_cycle_svc.cancel_active_cycle.assert_called_once_with("inc-r-001")
    assert result.result["pending_cycle_cancelled"] is True


@pytest.mark.asyncio
async def test_item4_user_non_positive_response_still_cancels_cycle():
    """
    Even a non-positive USER response (e.g. ACKNOWLEDGED_ONLY) must cancel
    the PendingCycle — the user HAS responded, so the "waiting" is over.
    The cycle should not keep firing reminders after the user replied.
    """
    svc = _make_resolution_svc(
        user_note_msg="Thanks, I'll check on it.",
        agent_response=_llm_resp_r(ResolutionIntent.ACKNOWLEDGED_ONLY),
    )
    result = await svc.process(_trigger_r(source="USER"))

    # Cycle cancelled — user responded
    svc.pending_cycle_svc.cancel_active_cycle.assert_called_once_with("inc-r-001")
    # But no auto-resolution
    svc.incident_service.update_incident_internal.assert_not_called()
    assert result.result["action"] != ResolutionAction.AUTO_RESOLVED.value


# ===========================================================================
# Item 7 — PENDING_AGENT transition: Resolution ignored, cycle NOT cancelled
# ===========================================================================

@pytest.mark.asyncio
async def test_item7_pending_agent_transition_ignored_cycle_not_cancelled():
    """
    When PENDING_AGENT work note causes ON_HOLD → ACTIVE:
    - Resolution is IGNORED immediately (step 1b fast-path)
    - NO LLM call
    - PendingCycle is NOT cancelled (still waiting for user)
    - Incident fetch is NOT performed (short-circuits before step 2)
    """
    svc = _make_resolution_svc()
    svc.agent = AsyncMock()

    result = await svc.process(ResolutionTrigger(
        incident_id="inc-r-001",
        previous_state="on_hold",
        current_state="active",
        triggering_work_note_id="wn-pending-001",
        triggering_work_note_source="PENDING_AGENT",
    ))

    assert result.result["action"] == ResolutionAction.IGNORED.value
    svc.agent.run.assert_not_called()
    svc.incident_service.get_incident.assert_not_called()
    svc.pending_cycle_svc.cancel_active_cycle.assert_not_called()


# ===========================================================================
# Item 8 — Valid ACK + USER + no engineer intervention → resolves
# ===========================================================================

@pytest.mark.asyncio
async def test_item8_valid_ack_user_no_engineer_intervention_resolves():
    """
    Full valid auto-resolution path:
    - Non-standard ACK note exists
    - No engineer notes after the ACK
    - USER responds with REQUIRED_ACTION_COMPLETED
    Result: auto-resolved, cycle cancelled.
    """
    ack_time = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone.utc)
    ack = _ack_note(_NONSTANDARD_MARKER, created_at=ack_time)

    # All notes: just the ACK (engineer notes come BEFORE ack_time, if any)
    all_notes = [ack]  # no engineer notes after ACK

    svc = _make_resolution_svc(
        user_note_msg="I have completed the steps.",
        agent_response=_llm_resp_r(ResolutionIntent.REQUIRED_ACTION_COMPLETED),
        ack_notes=[ack],
        all_notes=all_notes,
    )

    result = await svc.process(_trigger_r(source="USER"))

    assert result.result["provenance_eligible"] is True
    assert result.result["action"] == ResolutionAction.AUTO_RESOLVED.value
    svc.pending_cycle_svc.cancel_active_cycle.assert_called_once()
    svc.incident_service.update_incident_internal.assert_called_once()


# ===========================================================================
# Item 9 — ACK/Pending + USER + engineer intervention → blocked
# ===========================================================================

@pytest.mark.asyncio
async def test_item9_engineer_intervention_after_ack_blocks_resolution():
    """
    An ENGINEER note exists AFTER the qualifying ACK note.
    Even with a positive USER response, auto-resolution is blocked.
    The engineer intervened → automatic resolution is not permitted.
    """
    ack_time = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone.utc)
    eng_time = datetime(2026, 9, 11, 10, 30, 0, tzinfo=timezone.utc)   # 30 min after ACK
    user_time = datetime(2026, 9, 11, 11, 0, 0, tzinfo=timezone.utc)   # 1 hr after ACK

    ack = _ack_note(_NONSTANDARD_MARKER, created_at=ack_time)
    eng_note = _engineer_note(created_at=eng_time)
    user_wn = _user_note_r("I have submitted the RITM.", created_at=user_time)

    # All notes in descending order (newest first): user, engineer, ack
    all_notes = [user_wn, eng_note, ack]

    svc = _make_resolution_svc(
        user_note_msg="I have submitted the RITM.",
        agent_response=_llm_resp_r(ResolutionIntent.REQUIRED_ACTION_COMPLETED),
        ack_notes=[ack],
        all_notes=all_notes,
    )

    result = await svc.process(_trigger_r(source="USER"))

    # Provenance blocked by engineer intervention
    assert result.result["provenance_eligible"] is False
    assert "engineer" in result.result["provenance_reason"].lower()
    assert result.result["action"] != ResolutionAction.AUTO_RESOLVED.value
    # Incident must NOT be resolved
    svc.incident_service.update_incident_internal.assert_not_called()
    # Cycle IS cancelled — user responded (regardless of resolution block)
    svc.pending_cycle_svc.cancel_active_cycle.assert_called_once()


@pytest.mark.asyncio
async def test_item9_engineer_note_before_ack_does_not_block_resolution():
    """
    An ENGINEER note that predates the qualifying ACK note is ignored.
    Only engineer activity AFTER the ACK workflow began blocks resolution.
    """
    ack_time = datetime(2026, 9, 11, 10, 0, 0, tzinfo=timezone.utc)
    eng_time = datetime(2026, 9, 11, 9, 0, 0, tzinfo=timezone.utc)    # 1 hr BEFORE ACK

    ack = _ack_note(_NONSTANDARD_MARKER, created_at=ack_time)
    eng_note = _engineer_note(created_at=eng_time)   # pre-ACK (e.g. initial assignment)

    all_notes = [ack, eng_note]  # desc order: ack is newer

    svc = _make_resolution_svc(
        user_note_msg="I have completed the requested steps.",
        agent_response=_llm_resp_r(ResolutionIntent.REQUIRED_ACTION_COMPLETED),
        ack_notes=[ack],
        all_notes=all_notes,
    )

    result = await svc.process(_trigger_r(source="USER"))

    # Pre-ACK engineer note must NOT block resolution
    assert result.result["provenance_eligible"] is True
    assert result.result["action"] == ResolutionAction.AUTO_RESOLVED.value


# ===========================================================================
# Item 10 — Engineer-manually-pended (no ACK) + USER → blocked
# ===========================================================================

@pytest.mark.asyncio
async def test_item10_engineer_manually_pended_user_response_blocked():
    """
    Engineer manually put the ticket ON_HOLD (no ACK Agent involvement).
    User responds positively.
    No ACKNOWLEDGEMENT_AGENT note → provenance fails → no auto-resolve.
    Cycle IS cancelled because the user responded.
    """
    svc = _make_resolution_svc(
        user_note_msg="Done, you can close this.",
        agent_response=_llm_resp_r(ResolutionIntent.ISSUE_RESOLVED),
        ack_notes=[],    # no ACK note — engineer manually pended
        all_notes=[],
    )

    result = await svc.process(_trigger_r(source="USER"))

    assert result.result["provenance_eligible"] is False
    assert result.result["action"] != ResolutionAction.AUTO_RESOLVED.value
    svc.incident_service.update_incident_internal.assert_not_called()
    # Cycle IS cancelled — user responded
    svc.pending_cycle_svc.cancel_active_cycle.assert_called_once()


# ===========================================================================
# Existing flow regression: PENDING_AGENT source transition still does not
# cancel cycle even with force_reminder path (i.e., scheduler re-entry)
# ===========================================================================

@pytest.mark.asyncio
async def test_stale_scheduled_job_after_cycle_cancelled_does_nothing():
    """
    If the scheduler fires force_reminder=True but the cycle was already
    cancelled (e.g. user responded and Resolution cancelled it), the
    execution must be silently discarded with no work note or notification.
    """
    svc = _make_pending_svc()
    svc.incident_service.get_incident.return_value = _mock_incident_p(state="on_hold")

    # No active cycle (was cancelled by Resolution after user responded)
    svc.cycle_svc.get_active_cycle.return_value = None

    resp = await svc.process_pending_transition(incident_id="inc-p-001", force_reminder=True)

    assert resp.success is True
    assert resp.result["action_taken"] == "DISCARDED"
    assert resp.result["email_sent"] is False
    svc.work_note_svc.add_note.assert_not_called()
    svc.cycle_svc.increment_reminder.assert_not_called()
    svc.cycle_svc.complete_cycle.assert_not_called()
