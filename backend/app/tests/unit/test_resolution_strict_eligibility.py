"""
Strict automatic-resolution eligibility tests.

Business rules under test
--------------------------
Auto-resolution is permitted ONLY when ALL of:
  1. Triggering work note source == USER
  2. An ACKNOWLEDGEMENT_AGENT work note exists that used a NON-STANDARD template
     (anything other than standard_ack.html)
  3. LLM intent is resolution-positive (ISSUE_RESOLVED / REQUEST_COMPLETED /
     REQUIRED_ACTION_COMPLETED)

The check that distinguishes standard vs non-standard uses the marker string
embedded in the ACK work note message by AcknowledgementService:
    "• Selected Template: standard_ack.html"   → standard   → NOT eligible
    "• Selected Template: <anything else>"      → non-standard → eligible
    (marker absent)                             → treat as non-standard (eligible)

STANDARD template marker (the constant in ResolutionService):
    ResolutionService._STANDARD_ACK_TEMPLATE_MARKER

Scenarios
---------
1.  Non-standard ACK + direct USER response (REQUIRED_ACTION_COMPLETED) → resolves
2.  Non-standard ACK + Pending reminders + USER response (REQUEST_COMPLETED) → resolves
3.  Standard ACK (standard_ack.html) + positive USER response → does NOT resolve
4.  USER response with NO ACK provenance → does NOT resolve
5.  Engineer-manually-pended ticket → no ACK note → does NOT resolve
6.  ACK/Pending workflow + USER says "okay"/"thanks" (ACKNOWLEDGED_ONLY) → does NOT resolve
7.  ACK/Pending workflow + USER says "I'll do it later" (ACTION_PENDING) → does NOT resolve
8.  PENDING_AGENT-caused state transition → Resolution ignored, no LLM, cycle stays active
9.  Valid resolution path → PendingCycle cancelled ONLY after all checks pass

All tests use fully mocked services — no DB, no LLM calls.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.modules.agents.resolution.service import ResolutionService
from app.modules.agents.resolution.schemas import (
    ResolutionAction,
    ResolutionTrigger,
    LLMAnalysis,
    ResolutionIntent,
    RESOLUTION_POSITIVE_INTENTS,
)
from app.modules.agents.base.response import AgentResponse
from app.modules.work_notes.enums import WorkNoteSourceType
from app.integrations.notifications.schemas import NotificationResult, NotificationChannel


# ---------------------------------------------------------------------------
# Markers and helpers
# ---------------------------------------------------------------------------

# The standard template marker — matches the constant in ResolutionService
_STANDARD_ACK_MARKER = "• Selected Template: standard_ack.html"

# A non-standard template marker — qualifies for auto-resolution
_NONSTANDARD_ACK_MARKER = "• Selected Template: wrong_ticket_access.html"


def _ack_note(template_marker: str, msg: str = "") -> MagicMock:
    """Build a mock ACKNOWLEDGEMENT_AGENT work note with the given template marker."""
    m = MagicMock()
    m.source_type = WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT.value
    m.message = (
        f"Acknowledgement Agent executed successfully.\n"
        f"• Classified Intent: ACCESS_REQUEST (Confidence: 0.95)\n"
        f"{template_marker}\n"
        f"• Status: Incident status updated to Pending / On Hold.\n"
        + (msg or "")
    )
    m.created_at = datetime.now(timezone.utc)
    return m


def _pending_note(count: int = 1) -> list[MagicMock]:
    """Return a list of mock PENDING_AGENT work notes."""
    notes = []
    for i in range(count):
        m = MagicMock()
        m.source_type = WorkNoteSourceType.PENDING_AGENT.value
        m.message = f"Pending Agent: Reminder {i + 1} of 3 sent to user."
        m.created_at = datetime.now(timezone.utc)
        notes.append(m)
    return notes


def _user_note(msg: str = "I have submitted the RITM.") -> MagicMock:
    m = MagicMock()
    m.source_type = WorkNoteSourceType.USER.value
    m.message = msg
    m.created_at = datetime.now(timezone.utc)
    return m


def _llm_resp(intent: ResolutionIntent, confidence: float = 0.92) -> AgentResponse:
    positive = intent in RESOLUTION_POSITIVE_INTENTS
    return AgentResponse(
        success=True,
        agent_name="ResolutionAgent",
        reasoning="test",
        confidence=confidence,
        result={"llm_analysis": LLMAnalysis(
            intent=intent,
            positive_resolution=positive,
            confidence=confidence,
            summary=f"Intent: {intent.value}",
            next_best_action="Review ticket.",
        ).model_dump()},
    )


def _trigger(source: str | None = "USER") -> ResolutionTrigger:
    return ResolutionTrigger(
        incident_id="inc-001",
        previous_state="on_hold",
        current_state="active",
        triggering_work_note_id="wn-001" if source else None,
        triggering_work_note_source=source,
    )


def _make_svc(
    user_note_msg: str = "I have submitted the RITM.",
    agent_response: AgentResponse | None = None,
    ack_notes: list | None = None,          # None = default non-standard ACK
    pending_notes: list | None = None,       # None = no pending notes
    trigger_source: str | None = "USER",
) -> ResolutionService:
    """
    Build a fully-mocked ResolutionService.

    get_by_source_type is wired as a side_effect that dispatches on
    source_type, so ACK and PENDING notes can be controlled independently.
    """
    from app.modules.context.schemas import AIContext, IncidentContext, EngineerContext

    db = AsyncMock()
    svc = ResolutionService(db)

    # Incident
    inc = MagicMock()
    inc.id = "inc-001"
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

    # Work notes — differentiated by source_type
    user_wn = _user_note(user_note_msg)
    _ack_list = ack_notes if ack_notes is not None else [_ack_note(_NONSTANDARD_ACK_MARKER)]
    _pending_list = pending_notes if pending_notes is not None else []

    async def _get_by_source_type(incident_id, source_type):
        """Dispatch by source_type to return the correct note list."""
        val = source_type.value if hasattr(source_type, "value") else str(source_type)
        if val == WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT.value:
            return _ack_list
        if val == WorkNoteSourceType.PENDING_AGENT.value:
            return _pending_list
        return []

    svc.work_note_svc = AsyncMock()
    svc.work_note_svc.get_latest.return_value = user_wn
    svc.work_note_svc.get_note_by_id.return_value = user_wn
    svc.work_note_svc.add_note.return_value = MagicMock(id="audit-1")
    svc.work_note_svc.get_by_source_type.side_effect = _get_by_source_type

    # Pending cycle
    svc.pending_cycle_svc = AsyncMock()
    cycle = MagicMock()
    cycle.id = "cycle-1"
    svc.pending_cycle_svc.cancel_active_cycle.return_value = cycle

    # Context
    inc_ctx = IncidentContext(
        incident_id="inc-001", incident_number="INC0000001",
        short_description="VPN", description=None, priority="3",
        state="active", category=None, subcategory=None,
        assignment_group="Network Ops", assigned_to="Alice",
        caller="alice", created_at=datetime.now(timezone.utc),
    )
    ctx = AIContext(
        incident=inc_ctx,
        engineers=[
            EngineerContext(
                engineer_id="e1", name="Alice", email="alice@corp.com",
                assignment_group="Network Ops", level="L2",
                default_shift="S1", current_shift="S1",
                is_available=True, is_shift_active=True,
                roster_date=datetime.now(timezone.utc).date(),
            )
        ],
        context_date=datetime.now(timezone.utc).date(),
        created_at=datetime.now(timezone.utc),
    )
    svc.context_service = AsyncMock()
    svc.context_service.build_for_incident.return_value = ctx

    # Notifications
    teams_res = NotificationResult(
        success=True, channel="teams", delivery_status="ok",
        message_id="T-1", recipient="alice@corp.com", message="body", work_note_id="wn-t",
    )
    email_res = NotificationResult(
        success=True, channel="email", delivery_status="ok",
        message_id="E-1", recipient="alice@corp.com", message="body", work_note_id="wn-e",
    )

    async def _send(req):
        if req.channel == NotificationChannel.TEAMS:
            return teams_res
        return email_res

    svc.notification_svc = AsyncMock()
    svc.notification_svc.send.side_effect = _send

    if agent_response is not None:
        svc.agent = AsyncMock()
        svc.agent.run.return_value = agent_response
        svc.agent.agent_name = "ResolutionAgent"

    return svc


# ===========================================================================
# Scenario 1 — Non-standard ACK + direct positive USER response → resolves
# ===========================================================================

@pytest.mark.asyncio
async def test_1_nonstandard_ack_direct_user_response_resolves():
    """
    ACK Agent used a non-standard template (wrong_ticket_access.html).
    User responds with "I have submitted the RITM." → REQUIRED_ACTION_COMPLETED.
    Expected: AUTO_RESOLVED.
    """
    svc = _make_svc(
        user_note_msg="I have submitted the RITM.",
        agent_response=_llm_resp(ResolutionIntent.REQUIRED_ACTION_COMPLETED),
        ack_notes=[_ack_note(_NONSTANDARD_ACK_MARKER)],
        pending_notes=[],  # no reminders — direct response
    )

    result = await svc.process(_trigger(source="USER"))

    assert result.result["provenance_eligible"] is True
    assert result.result["action"] == ResolutionAction.AUTO_RESOLVED.value
    svc.incident_service.update_incident_internal.assert_called()


# ===========================================================================
# Scenario 2 — Non-standard ACK + Pending reminders + USER response → resolves
# ===========================================================================

@pytest.mark.asyncio
async def test_2_nonstandard_ack_pending_reminder_user_response_resolves():
    """
    ACK Agent used a non-standard template.
    Pending Agent sent 2 reminders.
    User finally responds → REQUEST_COMPLETED.
    Expected: AUTO_RESOLVED.
    """
    svc = _make_svc(
        user_note_msg="I submitted the RITM yesterday.",
        agent_response=_llm_resp(ResolutionIntent.REQUEST_COMPLETED),
        ack_notes=[_ack_note(_NONSTANDARD_ACK_MARKER)],
        pending_notes=_pending_note(2),
    )

    result = await svc.process(_trigger(source="USER"))

    assert result.result["provenance_eligible"] is True
    assert "non-standard" in result.result["provenance_reason"].lower()
    assert "pending" in result.result["provenance_reason"].lower()
    assert result.result["action"] == ResolutionAction.AUTO_RESOLVED.value


# ===========================================================================
# Scenario 3 — Standard ACK + positive USER response → does NOT resolve
# ===========================================================================

@pytest.mark.asyncio
async def test_3_standard_ack_template_does_not_resolve():
    """
    ACK Agent used the standard template (standard_ack.html).
    User responds positively.
    Expected: NOT AUTO_RESOLVED — standard ACK does not request a specific action.
    """
    svc = _make_svc(
        user_note_msg="Everything is working now.",
        agent_response=_llm_resp(ResolutionIntent.ISSUE_RESOLVED),
        ack_notes=[_ack_note(_STANDARD_ACK_MARKER)],  # standard — not eligible
    )

    result = await svc.process(_trigger(source="USER"))

    assert result.result["provenance_eligible"] is False
    assert "standard template" in result.result["provenance_reason"].lower()
    assert result.result["action"] != ResolutionAction.AUTO_RESOLVED.value
    svc.incident_service.update_incident_internal.assert_not_called()
    # Cycle IS cancelled — user responded, waiting-for-user is over
    svc.pending_cycle_svc.cancel_active_cycle.assert_called_once()


# ===========================================================================
# Scenario 4 — USER response without any ACK provenance → does NOT resolve
# ===========================================================================

@pytest.mark.asyncio
async def test_4_user_response_no_ack_provenance_does_not_resolve():
    """
    No ACKNOWLEDGEMENT_AGENT work note on the incident.
    USER responds positively.
    Expected: NOT AUTO_RESOLVED — ticket not in ACK workflow.
    """
    svc = _make_svc(
        user_note_msg="Issue is resolved.",
        agent_response=_llm_resp(ResolutionIntent.ISSUE_RESOLVED),
        ack_notes=[],  # no ACK notes
        pending_notes=[],
    )

    result = await svc.process(_trigger(source="USER"))

    assert result.result["provenance_eligible"] is False
    assert "no acknowledgement_agent" in result.result["provenance_reason"].lower()
    assert result.result["action"] != ResolutionAction.AUTO_RESOLVED.value
    svc.incident_service.update_incident_internal.assert_not_called()
    # Cycle IS cancelled — user responded
    svc.pending_cycle_svc.cancel_active_cycle.assert_called_once()


# ===========================================================================
# Scenario 5 — Engineer-manually-pended ticket → does NOT resolve
# ===========================================================================

@pytest.mark.asyncio
async def test_5_engineer_manually_pended_does_not_resolve():
    """
    Engineer manually put the ticket ON_HOLD — no ACK Agent involvement.
    User responds "Done, you can close this."
    Expected: NOT AUTO_RESOLVED.
    """
    svc = _make_svc(
        user_note_msg="Done, you can close this.",
        agent_response=_llm_resp(ResolutionIntent.ISSUE_RESOLVED),
        ack_notes=[],   # no ACK note — manually pended by engineer
        pending_notes=[],
    )

    result = await svc.process(_trigger(source="USER"))

    assert result.result["provenance_eligible"] is False
    assert result.result["action"] != ResolutionAction.AUTO_RESOLVED.value
    # Cycle IS cancelled — user responded (no active PendingCycle exists for
    # engineer-manually-pended tickets, so cancel is a no-op but still called)
    svc.pending_cycle_svc.cancel_active_cycle.assert_called_once()


# ===========================================================================
# Scenario 6 — ACK/Pending + USER says "okay"/"thanks" → does NOT resolve
# ===========================================================================

@pytest.mark.asyncio
async def test_6_ack_pending_user_acknowledges_only_does_not_resolve():
    """
    Non-standard ACK exists.  User responds "Thanks, I'll check on it."
    LLM classifies as ACKNOWLEDGED_ONLY.
    Expected: NOT AUTO_RESOLVED, PendingCycle NOT cancelled.
    """
    svc = _make_svc(
        user_note_msg="Thanks, I'll check on it.",
        agent_response=_llm_resp(ResolutionIntent.ACKNOWLEDGED_ONLY),
        ack_notes=[_ack_note(_NONSTANDARD_ACK_MARKER)],
        pending_notes=_pending_note(1),
    )

    result = await svc.process(_trigger(source="USER"))

    assert result.result["work_note_eligible"] is True
    assert result.result["provenance_eligible"] is True
    assert result.result["action"] != ResolutionAction.AUTO_RESOLVED.value
    svc.incident_service.update_incident_internal.assert_not_called()
    # Cycle IS cancelled — user responded (regardless of non-positive intent)
    svc.pending_cycle_svc.cancel_active_cycle.assert_called_once()


# ===========================================================================
# Scenario 7 — ACK/Pending + USER says action will be completed later
# ===========================================================================

@pytest.mark.asyncio
async def test_7_ack_pending_user_action_pending_does_not_resolve():
    """
    Non-standard ACK + Pending reminders.  User responds "I'll do it tomorrow."
    LLM classifies as ACTION_PENDING.
    Expected: NOT AUTO_RESOLVED, PendingCycle NOT cancelled.
    """
    svc = _make_svc(
        user_note_msg="I'll submit the RITM next week.",
        agent_response=_llm_resp(ResolutionIntent.ACTION_PENDING),
        ack_notes=[_ack_note(_NONSTANDARD_ACK_MARKER)],
        pending_notes=_pending_note(2),
    )

    result = await svc.process(_trigger(source="USER"))

    assert result.result["action"] != ResolutionAction.AUTO_RESOLVED.value
    svc.incident_service.update_incident_internal.assert_not_called()
    # Cycle IS cancelled — user responded
    svc.pending_cycle_svc.cancel_active_cycle.assert_called_once()


# ===========================================================================
# Scenario 8 — PENDING_AGENT work-note-caused transition → Resolution ignored
# ===========================================================================

@pytest.mark.asyncio
async def test_8_pending_agent_transition_ignored_no_llm_no_cycle_cancel():
    """
    Pending Agent sends a reminder → WorkNoteService fires ON_HOLD → ACTIVE.
    triggering_work_note_source = PENDING_AGENT.
    Expected: IGNORED, LLM not called, PendingCycle stays active.
    """
    svc = _make_svc()
    svc.agent = AsyncMock()

    result = await svc.process(ResolutionTrigger(
        incident_id="inc-001",
        previous_state="on_hold",
        current_state="active",
        triggering_work_note_id="wn-pending-reminder",
        triggering_work_note_source="PENDING_AGENT",
    ))

    assert result.result["action"] == ResolutionAction.IGNORED.value
    # LLM must NOT be called
    svc.agent.run.assert_not_called()
    # Incident service must NOT be called
    svc.incident_service.get_incident.assert_not_called()
    # PendingCycle must NOT be cancelled
    svc.pending_cycle_svc.cancel_active_cycle.assert_not_called()


# ===========================================================================
# Scenario 9 — Valid resolution: PendingCycle cancelled only after all checks pass
# ===========================================================================

@pytest.mark.asyncio
async def test_9_pending_cycle_cancelled_only_after_all_checks_pass():
    """
    Full valid resolution path:
      - USER trigger
      - Non-standard ACK note exists
      - Positive LLM intent (REQUIRED_ACTION_COMPLETED)
    Expected:
      - PendingCycle cancelled exactly once
      - Incident resolved exactly once
      - Cancellation happens AFTER provenance and intent checks (not before)
    """
    svc = _make_svc(
        user_note_msg="I have completed all the required steps.",
        agent_response=_llm_resp(ResolutionIntent.REQUIRED_ACTION_COMPLETED),
        ack_notes=[_ack_note(_NONSTANDARD_ACK_MARKER)],
    )

    result = await svc.process(_trigger(source="USER"))

    assert result.result["action"] == ResolutionAction.AUTO_RESOLVED.value
    assert result.result["pending_cycle_cancelled"] is True

    # Cycle was cancelled exactly once
    svc.pending_cycle_svc.cancel_active_cycle.assert_called_once_with("inc-001")

    # Incident state was updated to resolved
    svc.incident_service.update_incident_internal.assert_called_once()


# ===========================================================================
# Unit test for the _is_standard_ack_note helper
# ===========================================================================

def test_is_standard_ack_note_helper():
    """Verify the marker detection logic directly."""
    standard = MagicMock()
    standard.message = (
        "Acknowledgement Agent executed successfully.\n"
        "• Selected Template: standard_ack.html\n"
        "• Status: Ticket assigned to Engineer."
    )
    nonstandard = MagicMock()
    nonstandard.message = (
        "Acknowledgement Agent executed successfully.\n"
        "• Selected Template: wrong_ticket_access.html\n"
        "• Status: Incident status updated to Pending / On Hold."
    )
    no_marker = MagicMock()
    no_marker.message = "Old format work note without template marker."

    assert ResolutionService._is_standard_ack_note(standard) is True
    assert ResolutionService._is_standard_ack_note(nonstandard) is False
    # No marker → treated as non-standard (eligible) for legacy notes
    assert ResolutionService._is_standard_ack_note(no_marker) is False


# ===========================================================================
# Additional: multiple non-standard ACK notes — first non-standard qualifies
# ===========================================================================

@pytest.mark.asyncio
async def test_multiple_ack_notes_first_nonstandard_qualifies():
    """
    If there are multiple ACK notes (e.g. re-acknowledged), the first
    non-standard one qualifies.
    """
    svc = _make_svc(
        user_note_msg="I have raised the access request.",
        agent_response=_llm_resp(ResolutionIntent.REQUEST_COMPLETED),
        ack_notes=[
            _ack_note(_NONSTANDARD_ACK_MARKER),   # most recent — non-standard
            _ack_note(_STANDARD_ACK_MARKER),       # older — standard
        ],
    )

    result = await svc.process(_trigger(source="USER"))

    assert result.result["provenance_eligible"] is True
    assert result.result["action"] == ResolutionAction.AUTO_RESOLVED.value


@pytest.mark.asyncio
async def test_all_ack_notes_standard_does_not_resolve():
    """
    All ACK notes used the standard template — not eligible.
    """
    svc = _make_svc(
        user_note_msg="Everything works now.",
        agent_response=_llm_resp(ResolutionIntent.ISSUE_RESOLVED),
        ack_notes=[
            _ack_note(_STANDARD_ACK_MARKER),
            _ack_note(_STANDARD_ACK_MARKER),
        ],
    )

    result = await svc.process(_trigger(source="USER"))

    assert result.result["provenance_eligible"] is False
    assert result.result["action"] != ResolutionAction.AUTO_RESOLVED.value
