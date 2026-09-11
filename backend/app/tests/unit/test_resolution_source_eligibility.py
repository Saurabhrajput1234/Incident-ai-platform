"""
Tests verifying Resolution Agent source-based eligibility.

Scenario coverage (from spec requirements)
-------------------------------------------
1.  PENDING_AGENT work note → ON_HOLD → ACTIVE → Resolution IGNORED, LLM NOT called
2.  SYSTEM work note → ON_HOLD → ACTIVE → Resolution IGNORED, LLM NOT called
3.  ACKNOWLEDGEMENT_AGENT work note → Resolution IGNORED
4.  ENGINEER work note → Resolution IGNORED
5.  USER work note → ON_HOLD → ACTIVE → Resolution analysis runs
6.  USER response, no ACK/Pending provenance → does NOT auto-resolve
7.  ACK Agent requested action + USER confirms → LLM classifies REQUIRED_ACTION_COMPLETED → resolves
8.  ACK Agent requested action + USER merely acknowledges → LLM classifies ACKNOWLEDGED_ONLY → NOT resolved
9.  Pending Agent sent reminder + Pending Agent note causes ON_HOLD → ACTIVE → IGNORED
10. Pending reminder + later USER response causes ON_HOLD → ACTIVE → Resolution runs
11. LLM returns ACTION_PENDING/UNCLEAR → NOT resolved
12. LLM returns REQUIRED_ACTION_COMPLETED/REQUEST_COMPLETED/ISSUE_RESOLVED → resolves (with provenance)
13. Duplicate trigger remains idempotent

All tests use a fully mocked ResolutionService (no DB, no LLM calls).
The `_make_svc` factory is extended to control triggering_work_note_source.
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
# Factories
# ---------------------------------------------------------------------------

def _trigger(
    source: str | None = None,
    previous: str = "on_hold",
    current: str = "active",
) -> ResolutionTrigger:
    """Build a trigger, optionally with a triggering_work_note_source."""
    return ResolutionTrigger(
        incident_id="inc-001",
        previous_state=previous,
        current_state=current,
        triggering_work_note_id="wn-001" if source else None,
        triggering_work_note_source=source,
    )


def _mock_note(source: str = "USER", msg: str = "It works now.") -> MagicMock:
    m = MagicMock()
    m.source_type = source
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


def _make_svc(
    note_source: str = "USER",
    note_msg: str = "It works now.",
    agent_response: AgentResponse | None = None,
    provenance_notes: list | None = None,
    update_internal_raises: Exception | None = None,
) -> ResolutionService:
    """
    Return a ResolutionService with all sub-services mocked.
    note_source / note_msg: source and message of the note returned by both
        get_latest() AND get_note_by_id() (covers both paths).
    """
    from datetime import date
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
    if update_internal_raises:
        svc.incident_service.update_incident_internal.side_effect = update_internal_raises
    else:
        svc.incident_service.update_incident_internal.return_value = inc

    # Work notes
    note = _mock_note(note_source, note_msg)
    svc.work_note_svc = AsyncMock()
    svc.work_note_svc.get_latest.return_value = note
    svc.work_note_svc.get_note_by_id.return_value = note
    svc.work_note_svc.add_note.return_value = MagicMock(id="audit-1")

    # Provenance — default: ACK note exists
    if provenance_notes is None:
        ack = _mock_note("ACKNOWLEDGEMENT_AGENT", "Please submit RITM.")
        svc.work_note_svc.get_by_source_type.return_value = [ack]
    else:
        svc.work_note_svc.get_by_source_type.return_value = provenance_notes

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

    # Agent
    if agent_response is not None:
        svc.agent = AsyncMock()
        svc.agent.run.return_value = agent_response
        svc.agent.agent_name = "ResolutionAgent"

    return svc


# ===========================================================================
# 1. PENDING_AGENT source → IGNORED at step 1b (fast path, no LLM)
# ===========================================================================

@pytest.mark.asyncio
async def test_1_pending_agent_work_note_ignored_no_llm():
    """
    PENDING_AGENT work note causes ON_HOLD → ACTIVE.
    Resolution Agent must IGNORE immediately and NOT call the LLM.
    """
    svc = _make_svc(note_source="PENDING_AGENT")
    svc.agent = AsyncMock()  # will fail test if called

    result = await svc.process(_trigger(source="PENDING_AGENT"))

    assert result.result["action"] == ResolutionAction.IGNORED.value
    # LLM agent must NOT have been invoked
    svc.agent.run.assert_not_called()


# ===========================================================================
# 2. SYSTEM source → IGNORED at step 1b, no LLM
# ===========================================================================

@pytest.mark.asyncio
async def test_2_system_work_note_ignored_no_llm():
    """
    SYSTEM audit note causes ON_HOLD → ACTIVE.
    Resolution Agent must IGNORE and NOT call the LLM.
    """
    svc = _make_svc(note_source="SYSTEM")
    svc.agent = AsyncMock()

    result = await svc.process(_trigger(source="SYSTEM"))

    assert result.result["action"] == ResolutionAction.IGNORED.value
    svc.agent.run.assert_not_called()


# ===========================================================================
# 3. ACKNOWLEDGEMENT_AGENT source → IGNORED
# ===========================================================================

@pytest.mark.asyncio
async def test_3_acknowledgement_agent_note_ignored():
    """
    ACKNOWLEDGEMENT_AGENT work note causes ON_HOLD → ACTIVE → IGNORED.
    """
    svc = _make_svc(note_source="ACKNOWLEDGEMENT_AGENT")
    svc.agent = AsyncMock()

    result = await svc.process(_trigger(source="ACKNOWLEDGEMENT_AGENT"))

    assert result.result["action"] == ResolutionAction.IGNORED.value
    svc.agent.run.assert_not_called()


# ===========================================================================
# 4. ENGINEER source → IGNORED
# ===========================================================================

@pytest.mark.asyncio
async def test_4_engineer_note_ignored():
    """
    ENGINEER work note causes ON_HOLD → ACTIVE → IGNORED.
    """
    svc = _make_svc(note_source="ENGINEER")
    svc.agent = AsyncMock()

    result = await svc.process(_trigger(source="ENGINEER"))

    assert result.result["action"] == ResolutionAction.IGNORED.value
    svc.agent.run.assert_not_called()


# ===========================================================================
# 5. USER source → analysis runs
# ===========================================================================

@pytest.mark.asyncio
async def test_5_user_note_triggers_analysis():
    """
    USER work note causes ON_HOLD → ACTIVE → Resolution analysis runs (LLM called).
    """
    svc = _make_svc(
        note_source="USER",
        note_msg="I have submitted the RITM.",
        agent_response=_llm_resp(ResolutionIntent.REQUEST_COMPLETED),
    )

    result = await svc.process(_trigger(source="USER"))

    assert result.result["work_note_eligible"] is True
    assert result.result["action"] != ResolutionAction.IGNORED.value
    svc.agent.run.assert_called_once()


# ===========================================================================
# 6. USER response, NO provenance → does not auto-resolve
# ===========================================================================

@pytest.mark.asyncio
async def test_6_user_response_no_provenance_does_not_resolve():
    """
    USER note triggers analysis, but there are no ACK/Pending provenance notes.
    Result: notified but NOT auto-resolved.
    """
    svc = _make_svc(
        note_source="USER",
        note_msg="It is working now.",
        agent_response=_llm_resp(ResolutionIntent.ISSUE_RESOLVED),
        provenance_notes=[],  # empty — no ACK/Pending workflow history
    )

    result = await svc.process(_trigger(source="USER"))

    data = result.result
    assert data["work_note_eligible"] is True
    assert data["provenance_eligible"] is False
    assert data["action"] != ResolutionAction.AUTO_RESOLVED.value
    # Incident state NOT changed
    svc.incident_service.update_incident_internal.assert_not_called()


# ===========================================================================
# 7. ACK requested + USER confirms action → REQUIRED_ACTION_COMPLETED → resolves
# ===========================================================================

@pytest.mark.asyncio
async def test_7_ack_requested_user_confirms_completion_resolves():
    """
    ACK Agent said "Please submit RITM" and user says "I have submitted it."
    LLM classifies REQUIRED_ACTION_COMPLETED → incident auto-resolved.
    """
    svc = _make_svc(
        note_source="USER",
        note_msg="I have submitted the RITM as requested.",
        agent_response=_llm_resp(ResolutionIntent.REQUIRED_ACTION_COMPLETED),
    )

    result = await svc.process(_trigger(source="USER"))

    data = result.result
    assert data["work_note_eligible"] is True
    assert data["provenance_eligible"] is True
    assert data["action"] == ResolutionAction.AUTO_RESOLVED.value
    # State change was called
    svc.incident_service.update_incident_internal.assert_called_once()


# ===========================================================================
# 8. ACK requested + USER merely acknowledges → ACKNOWLEDGED_ONLY → NOT resolved
# ===========================================================================

@pytest.mark.asyncio
async def test_8_ack_requested_user_acknowledges_only_not_resolved():
    """
    ACK Agent requested RITM submission. User responds "Thanks, I'll check."
    LLM classifies ACKNOWLEDGED_ONLY → NOT resolved.
    """
    svc = _make_svc(
        note_source="USER",
        note_msg="Thanks, I'll check on that.",
        agent_response=_llm_resp(ResolutionIntent.ACKNOWLEDGED_ONLY),
    )

    result = await svc.process(_trigger(source="USER"))

    data = result.result
    assert data["work_note_eligible"] is True
    assert data["action"] != ResolutionAction.AUTO_RESOLVED.value
    svc.incident_service.update_incident_internal.assert_not_called()


# ===========================================================================
# 9. Pending Agent reminder note causes ON_HOLD → ACTIVE → IGNORED
# ===========================================================================

@pytest.mark.asyncio
async def test_9_pending_agent_reminder_causes_state_change_ignored():
    """
    Pending Agent sends reminder → WorkNoteService auto-changes ON_HOLD → ACTIVE.
    Resolution Agent sees triggering_work_note_source=PENDING_AGENT → IGNORED.
    LLM NOT called.
    """
    svc = _make_svc(note_source="PENDING_AGENT")
    svc.agent = AsyncMock()

    result = await svc.process(ResolutionTrigger(
        incident_id="inc-001",
        previous_state="on_hold",
        current_state="active",
        triggering_work_note_id="wn-pending-reminder",
        triggering_work_note_source="PENDING_AGENT",  # ← the key field
    ))

    assert result.result["action"] == ResolutionAction.IGNORED.value
    svc.agent.run.assert_not_called()


# ===========================================================================
# 10. Pending reminder THEN USER responds → USER causes ON_HOLD → ACTIVE → runs
# ===========================================================================

@pytest.mark.asyncio
async def test_10_pending_reminder_then_user_response_triggers_analysis():
    """
    After reminders were sent, the USER eventually responds with a work note.
    That USER work note causes ON_HOLD → ACTIVE.
    triggering_work_note_source=USER → Resolution analysis runs.
    """
    svc = _make_svc(
        note_source="USER",
        note_msg="I have now completed the requested steps.",
        agent_response=_llm_resp(ResolutionIntent.REQUIRED_ACTION_COMPLETED),
    )

    result = await svc.process(ResolutionTrigger(
        incident_id="inc-001",
        previous_state="on_hold",
        current_state="active",
        triggering_work_note_id="wn-user-response",
        triggering_work_note_source="USER",  # ← user responded, not the agent
    ))

    data = result.result
    assert data["work_note_eligible"] is True
    assert data["action"] != ResolutionAction.IGNORED.value
    svc.agent.run.assert_called_once()


# ===========================================================================
# 11. LLM returns ACTION_PENDING or UNCLEAR → NOT resolved
# ===========================================================================

@pytest.mark.asyncio
async def test_11a_action_pending_intent_not_resolved():
    """LLM returns ACTION_PENDING → no auto-resolution."""
    svc = _make_svc(
        note_source="USER",
        note_msg="I'll do it tomorrow.",
        agent_response=_llm_resp(ResolutionIntent.ACTION_PENDING),
    )

    result = await svc.process(_trigger(source="USER"))

    data = result.result
    assert data["action"] != ResolutionAction.AUTO_RESOLVED.value
    svc.incident_service.update_incident_internal.assert_not_called()


@pytest.mark.asyncio
async def test_11b_unclear_intent_not_resolved():
    """LLM returns UNCLEAR → no auto-resolution."""
    svc = _make_svc(
        note_source="USER",
        note_msg="Yes.",
        agent_response=_llm_resp(ResolutionIntent.UNCLEAR),
    )

    result = await svc.process(_trigger(source="USER"))

    data = result.result
    assert data["action"] != ResolutionAction.AUTO_RESOLVED.value
    svc.incident_service.update_incident_internal.assert_not_called()


@pytest.mark.asyncio
async def test_11c_more_information_provided_not_resolved():
    """LLM returns MORE_INFORMATION_PROVIDED → no auto-resolution."""
    svc = _make_svc(
        note_source="USER",
        note_msg="Here are the logs you requested.",
        agent_response=_llm_resp(ResolutionIntent.MORE_INFORMATION_PROVIDED),
    )

    result = await svc.process(_trigger(source="USER"))

    data = result.result
    assert data["action"] != ResolutionAction.AUTO_RESOLVED.value
    svc.incident_service.update_incident_internal.assert_not_called()


# ===========================================================================
# 12. LLM returns REQUIRED_ACTION_COMPLETED / REQUEST_COMPLETED / ISSUE_RESOLVED
#     → resolves (with provenance)
# ===========================================================================

@pytest.mark.asyncio
async def test_12a_required_action_completed_resolves():
    """REQUIRED_ACTION_COMPLETED + provenance → AUTO_RESOLVED."""
    svc = _make_svc(
        note_source="USER",
        note_msg="I have completed all the required steps.",
        agent_response=_llm_resp(ResolutionIntent.REQUIRED_ACTION_COMPLETED),
    )
    result = await svc.process(_trigger(source="USER"))
    assert result.result["action"] == ResolutionAction.AUTO_RESOLVED.value


@pytest.mark.asyncio
async def test_12b_request_completed_resolves():
    """REQUEST_COMPLETED + provenance → AUTO_RESOLVED."""
    svc = _make_svc(
        note_source="USER",
        note_msg="I have raised the RITM via the portal.",
        agent_response=_llm_resp(ResolutionIntent.REQUEST_COMPLETED),
    )
    result = await svc.process(_trigger(source="USER"))
    assert result.result["action"] == ResolutionAction.AUTO_RESOLVED.value


@pytest.mark.asyncio
async def test_12c_issue_resolved_resolves():
    """ISSUE_RESOLVED + provenance → AUTO_RESOLVED."""
    svc = _make_svc(
        note_source="USER",
        note_msg="Everything is working fine now.",
        agent_response=_llm_resp(ResolutionIntent.ISSUE_RESOLVED),
    )
    result = await svc.process(_trigger(source="USER"))
    assert result.result["action"] == ResolutionAction.AUTO_RESOLVED.value


# ===========================================================================
# 13. Duplicate trigger → idempotent (second process call returns IGNORED or
#     reflects already-resolved state — no duplicate resolution action)
# ===========================================================================

@pytest.mark.asyncio
async def test_13_duplicate_trigger_idempotency():
    """
    If the same trigger is processed twice (e.g. a retry), the second call
    must not perform a second auto-resolution.

    Simulated by making update_incident_internal raise on the second call
    (mimicking an incident that's already resolved / no longer in active state).
    The first call succeeds; the second call either gets IGNORED via the
    source gate (no triggering_work_note_source → step 4 checks latest note)
    or raises gracefully.

    The simpler idempotency check: once resolved, the latest note in the DB
    would be a SYSTEM note, so step 4 rejects the second trigger as IGNORED.
    """
    svc = _make_svc(
        note_source="SYSTEM",  # simulate second call — latest note is already the SYSTEM audit note
        note_msg="Resolution Agent: auto-resolved.",
    )
    svc.agent = AsyncMock()

    # Second trigger — no triggering_work_note_id (simulating a retry without the original ID)
    result = await svc.process(ResolutionTrigger(
        incident_id="inc-001",
        previous_state="on_hold",
        current_state="active",
    ))

    assert result.result["action"] == ResolutionAction.IGNORED.value
    # LLM was NOT called on the duplicate
    svc.agent.run.assert_not_called()
    # No state-change was attempted
    svc.incident_service.update_incident_internal.assert_not_called()


# ===========================================================================
# Additional: source fast-path covers all non-USER sources
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("source", [
    "PENDING_AGENT",
    "ACKNOWLEDGEMENT_AGENT",
    "ENGINEER",
    "SYSTEM",
    "TRIAGE_AGENT",
])
async def test_non_user_sources_all_ignored_fast_path(source: str):
    """
    Every non-USER source with triggering_work_note_source set must be
    rejected at step 1b (before any DB call to get the incident).
    """
    svc = _make_svc(note_source=source)
    svc.agent = AsyncMock()

    result = await svc.process(_trigger(source=source))

    assert result.result["action"] == ResolutionAction.IGNORED.value
    svc.agent.run.assert_not_called()
    # Incident service was NOT called (short-circuited before step 2)
    svc.incident_service.get_incident.assert_not_called()
