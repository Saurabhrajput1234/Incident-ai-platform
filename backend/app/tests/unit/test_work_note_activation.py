"""
Tests for the work-note auto-activation behaviour and the updated Resolution Agent trigger.

Coverage map (requirements A–E plus regression section D)
----------------------------------------------------------
A. Work note activation (tests 1–10)
    1.  ON_HOLD  + ENGINEER note  → IN_PROGRESS
    2.  ON_HOLD  + USER note      → IN_PROGRESS
    3.  ON_HOLD  + TRIAGE_AGENT note  → IN_PROGRESS
    4.  ON_HOLD  + ACKNOWLEDGEMENT_AGENT note → IN_PROGRESS
        (auto_activate=True; different from AcknowledgementService which uses False)
    5.  ON_HOLD  + PENDING_AGENT note → IN_PROGRESS
    6.  PENDING  + USER note      → IN_PROGRESS
    7.  NEW      + USER note      → IN_PROGRESS
    8.  IN_PROGRESS + USER note   → remains IN_PROGRESS (no-op)
    9.  ACTIVE (IN_PROGRESS) + USER note → remains IN_PROGRESS
    10. ACTIVE (IN_PROGRESS) + ENGINEER note → remains IN_PROGRESS

B. Engineer field updates (tests 11–14)
    11. ON_HOLD + engineer updates priority   → remains ON_HOLD
    12. ON_HOLD + engineer updates category   → remains ON_HOLD
    13. ON_HOLD + engineer updates CI         → remains ON_HOLD
    14. ON_HOLD + engineer updates assignment group → remains ON_HOLD

C. Explicit state update (test 15)
    15. Engineer explicitly sets ON_HOLD → RESOLVED → remains RESOLVED

D. Resolution Alert Agent trigger update (tests 16–21)
    16. ON_HOLD → ACTIVE + USER latest note   → eligible (processed)
    17. PENDING → ACTIVE                      → ignored
    18. IN_PROGRESS → ACTIVE                  → ignored
    19. NEW → ACTIVE                          → ignored
    20. ON_HOLD → ACTIVE + ENGINEER latest note  → ignored
    21. ON_HOLD → ACTIVE + AGENT latest note     → ignored

Notes
-----
* Tests 1–15 use real SQLite db_session (integration style) to verify actual DB state.
* Tests 16–21 use mocked services (unit style) to test ResolutionService routing.
"""
from __future__ import annotations

import uuid
import pytest
from datetime import datetime, timezone, date
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select

from app.modules.incidents.model import Incident
from app.modules.incidents.enums import IncidentPriority, IncidentState
from app.modules.incidents.service import IncidentService
from app.modules.incidents.schemas import IncidentUpdate
from app.modules.work_notes.service import WorkNoteService
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType
from app.modules.agents.resolution.service import ResolutionService
from app.modules.agents.resolution.schemas import ResolutionAction, ResolutionTrigger, LLMAnalysis
from app.modules.agents.base.response import AgentResponse
from app.integrations.notifications.schemas import NotificationChannel, NotificationResult


# ---------------------------------------------------------------------------
# Integration helpers (use real db_session)
# ---------------------------------------------------------------------------

async def _create_incident(db, state: str = "on_hold") -> Incident:
    inc = Incident(
        id=str(uuid.uuid4()),
        incident_number=f"INC{uuid.uuid4().hex[:7].upper()}",
        short_description="Auto-activate test",
        priority=IncidentPriority.MEDIUM.value,
        state=state,
    )
    db.add(inc)
    await db.commit()
    await db.refresh(inc)
    return inc


async def _reload_incident(db, incident_id: str) -> Incident:
    result = await db.execute(
        select(Incident).where(Incident.id == incident_id)
    )
    return result.scalar_one()


# ===========================================================================
# A. Work note activation — integration tests against real SQLite
# ===========================================================================

@pytest.mark.anyio
async def test_A1_on_hold_engineer_note_activates(db_session):
    """ON_HOLD + ENGINEER work note → state becomes in_progress."""
    inc = await _create_incident(db_session, state="on_hold")
    svc = WorkNoteService(db_session)
    await svc.add_note(
        incident_id=inc.id,
        message="Added extra diagnostics.",
        source_type=WorkNoteSourceType.ENGINEER,
        source_name="Alice Smith",
        auto_activate=True,
    )
    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"


@pytest.mark.anyio
async def test_A2_on_hold_user_note_activates(db_session):
    """ON_HOLD + USER work note → state becomes in_progress."""
    inc = await _create_incident(db_session, state="on_hold")
    svc = WorkNoteService(db_session)
    await svc.add_note(
        incident_id=inc.id,
        message="The issue is still happening.",
        source_type=WorkNoteSourceType.USER,
        source_name="Bob (Reporter)",
        auto_activate=True,
    )
    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"


@pytest.mark.anyio
async def test_A3_on_hold_triage_agent_note_activates(db_session):
    """ON_HOLD + TRIAGE_AGENT work note → state becomes in_progress."""
    inc = await _create_incident(db_session, state="on_hold")
    svc = WorkNoteService(db_session)
    await svc.add_note(
        incident_id=inc.id,
        message="Triage re-run.",
        source_type=WorkNoteSourceType.TRIAGE_AGENT,
        source_name="TriageAgent",
        auto_activate=True,
    )
    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"


@pytest.mark.anyio
async def test_A4_on_hold_acknowledgement_agent_note_activates(db_session):
    """
    ON_HOLD + ACKNOWLEDGEMENT_AGENT note with auto_activate=True → in_progress.
    (Note: AcknowledgementService always passes auto_activate=False.
     This test verifies the underlying mechanism works when True is explicitly passed.)
    """
    inc = await _create_incident(db_session, state="on_hold")
    svc = WorkNoteService(db_session)
    await svc.add_note(
        incident_id=inc.id,
        message="Acknowledgement re-sent.",
        source_type=WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT,
        source_name="AcknowledgementAgent",
        auto_activate=True,
    )
    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"


@pytest.mark.anyio
async def test_A5_on_hold_pending_agent_note_activates(db_session):
    """ON_HOLD + PENDING_AGENT work note → state becomes in_progress."""
    inc = await _create_incident(db_session, state="on_hold")
    svc = WorkNoteService(db_session)
    await svc.add_note(
        incident_id=inc.id,
        message="Reminder sent.",
        source_type=WorkNoteSourceType.PENDING_AGENT,
        source_name="PendingReminderAgent",
        auto_activate=True,
    )
    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"


@pytest.mark.anyio
async def test_A6_pending_user_note_activates(db_session):
    """PENDING + USER note → state becomes in_progress."""
    inc = await _create_incident(db_session, state="pending")
    svc = WorkNoteService(db_session)
    await svc.add_note(
        incident_id=inc.id,
        message="Checking in.",
        source_type=WorkNoteSourceType.USER,
        source_name="Carol",
        auto_activate=True,
    )
    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"


@pytest.mark.anyio
async def test_A7_new_user_note_activates(db_session):
    """NEW + USER note → state becomes in_progress."""
    inc = await _create_incident(db_session, state="new")
    svc = WorkNoteService(db_session)
    await svc.add_note(
        incident_id=inc.id,
        message="Here is more info.",
        source_type=WorkNoteSourceType.USER,
        source_name="Dave",
        auto_activate=True,
    )
    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"


@pytest.mark.anyio
async def test_A8_in_progress_user_note_stays_in_progress(db_session):
    """IN_PROGRESS + USER note → no state change, remains in_progress."""
    inc = await _create_incident(db_session, state="in_progress")
    svc = WorkNoteService(db_session)
    await svc.add_note(
        incident_id=inc.id,
        message="Still working.",
        source_type=WorkNoteSourceType.USER,
        source_name="Eve",
        auto_activate=True,
    )
    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"


@pytest.mark.anyio
async def test_A9_already_active_user_note_no_state_change(db_session):
    """IN_PROGRESS (active) + USER note → state does not change."""
    inc = await _create_incident(db_session, state="in_progress")
    svc = WorkNoteService(db_session)
    await svc.add_note(
        incident_id=inc.id,
        message="Update from user.",
        source_type=WorkNoteSourceType.USER,
        source_name="Frank",
        auto_activate=True,
    )
    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"


@pytest.mark.anyio
async def test_A10_already_active_engineer_note_no_state_change(db_session):
    """IN_PROGRESS + ENGINEER note → no redundant state update."""
    inc = await _create_incident(db_session, state="in_progress")
    svc = WorkNoteService(db_session)
    await svc.add_note(
        incident_id=inc.id,
        message="Engineer update.",
        source_type=WorkNoteSourceType.ENGINEER,
        source_name="Grace",
        auto_activate=True,
    )
    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"


# ===========================================================================
# B. Engineer field updates via IncidentService.update_incident()
# These use auto_activate=False internally so state must NOT change.
# ===========================================================================

@pytest.mark.anyio
async def test_B11_on_hold_priority_update_stays_on_hold(db_session):
    """ON_HOLD + engineer updates priority via update_incident → remains on_hold."""
    inc = await _create_incident(db_session, state="on_hold")
    svc = IncidentService(db_session)
    await svc.update_incident(inc.id, IncidentUpdate(priority=IncidentPriority.HIGH))
    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "on_hold"


@pytest.mark.anyio
async def test_B12_on_hold_category_update_stays_on_hold(db_session):
    """ON_HOLD + engineer updates category → remains on_hold."""
    from app.modules.incidents.enums import IncidentCategory
    inc = await _create_incident(db_session, state="on_hold")
    svc = IncidentService(db_session)
    await svc.update_incident(inc.id, IncidentUpdate(category=IncidentCategory.SOFTWARE))
    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "on_hold"


@pytest.mark.anyio
async def test_B13_on_hold_ci_update_stays_on_hold(db_session):
    """ON_HOLD + engineer updates configuration_item → remains on_hold."""
    inc = await _create_incident(db_session, state="on_hold")
    svc = IncidentService(db_session)
    await svc.update_incident(inc.id, IncidentUpdate(configuration_item="CI-1234"))
    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "on_hold"


@pytest.mark.anyio
async def test_B14_on_hold_assignment_group_update_stays_on_hold(db_session):
    """ON_HOLD + engineer updates assignment_group → remains on_hold."""
    inc = await _create_incident(db_session, state="on_hold")
    svc = IncidentService(db_session)
    await svc.update_incident(inc.id, IncidentUpdate(assignment_group="Network Ops"))
    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "on_hold"


# ===========================================================================
# C. Explicit state update — engineer explicitly changes state
# ===========================================================================

@pytest.mark.anyio
async def test_C15_engineer_explicit_state_change_preserved(db_session):
    """
    Engineer explicitly sets ON_HOLD → RESOLVED via update_incident.
    The state must remain RESOLVED — the work note must not re-activate to in_progress.
    """
    inc = await _create_incident(db_session, state="on_hold")
    svc = IncidentService(db_session)
    await svc.update_incident(inc.id, IncidentUpdate(state=IncidentState.RESOLVED))
    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "resolved"


# ===========================================================================
# D. Resolution Alert Agent trigger tests (unit, mocked)
# ===========================================================================

def _mock_incident_for_resolution(state: str = "in_progress"):
    m = MagicMock()
    m.id = "inc-001"
    m.incident_number = "INC0000001"
    m.state = state
    m.assigned_to = "Alice"
    m.assignment_group = "Network Ops"
    m.short_description = "VPN issue"
    m.description = "Cannot connect"
    m.priority = "3"
    m.category = "network"
    m.subcategory = None
    m.caller = "alice"
    m.created_at = datetime.now(timezone.utc)
    return m


def _mock_work_note_res(source_type: str = "USER", message: str = "It works now."):
    m = MagicMock()
    m.source_type = source_type
    m.message = message
    return m


def _positive_agent_resp() -> AgentResponse:
    return AgentResponse(
        success=True,
        agent_name="ResolutionAgent",
        reasoning="User confirmed fix.",
        confidence=0.95,
        result={"llm_analysis": LLMAnalysis(
            positive_resolution=True, confidence=0.95,
            summary="Issue resolved.", next_best_action="Close ticket.",
        ).model_dump()},
    )


def _make_resolution_service(
    latest_note_source: str = "USER",
    latest_note_msg: str = "It works now.",
    agent_response: AgentResponse | None = None,
    provenance_notes: list | None = None,
) -> ResolutionService:
    db = AsyncMock()
    svc = ResolutionService(db)

    svc.incident_service = AsyncMock()
    svc.incident_service.get_incident.return_value = _mock_incident_for_resolution()
    svc.incident_service.update_incident_internal.return_value = _mock_incident_for_resolution()

    svc.work_note_svc = AsyncMock()
    svc.work_note_svc.get_latest.return_value = _mock_work_note_res(
        source_type=latest_note_source, message=latest_note_msg
    )
    svc.work_note_svc.add_note.return_value = MagicMock(id="wn-audit-1")

    if provenance_notes is None:
        ack_note = MagicMock()
        ack_note.source_type = WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT.value
        svc.work_note_svc.get_by_source_type.return_value = [ack_note]
    else:
        svc.work_note_svc.get_by_source_type.return_value = provenance_notes

    svc.pending_cycle_svc = AsyncMock()
    svc.pending_cycle_svc.cancel_active_cycle.return_value = MagicMock(id="cycle-1")

    from app.modules.context.schemas import AIContext, IncidentContext, EngineerContext
    from app.modules.context.schemas import AIContext as _AIC
    inc_ctx = IncidentContext(
        incident_id="inc-001", incident_number="INC0000001",
        short_description="VPN", description=None, priority="3",
        state="in_progress", category=None, subcategory=None,
        assignment_group="Network Ops", assigned_to="Alice",
        caller="alice", created_at=datetime.now(timezone.utc),
    )
    ctx = _AIC(
        incident=inc_ctx,
        engineers=[
            EngineerContext(
                engineer_id="e1", name="Alice", email="alice@corp.com",
                assignment_group="Network Ops", level="L2",
                default_shift="Shift1", current_shift="Shift1",
                is_available=True, is_shift_active=True,
                roster_date=date.today(),
            )
        ],
        context_date=date.today(),
        created_at=datetime.now(timezone.utc),
    )
    svc.context_service = AsyncMock()
    svc.context_service.build_for_incident.return_value = ctx

    notif_teams = NotificationResult(
        success=True, channel="teams", delivery_status="simulated_success",
        message_id="SIM-T-1", recipient="alice@corp.com",
        message="body", work_note_id="wn-t-1",
    )
    notif_email = NotificationResult(
        success=True, channel="email", delivery_status="simulated_success",
        message_id="SIM-E-1", recipient="alice@corp.com",
        message="body", work_note_id="wn-e-1",
    )

    async def _send(req):
        if req.channel == NotificationChannel.TEAMS:
            return notif_teams
        return notif_email

    svc.notification_svc = AsyncMock()
    svc.notification_svc.send.side_effect = _send

    if agent_response is not None:
        svc.agent = AsyncMock()
        svc.agent.run.return_value = agent_response
        svc.agent.agent_name = "ResolutionAgent"

    return svc


@pytest.mark.asyncio
async def test_D16_on_hold_to_active_user_note_eligible():
    """ON_HOLD → ACTIVE + USER latest note → trigger eligible, processed."""
    svc = _make_resolution_service(
        latest_note_source="USER",
        agent_response=_positive_agent_resp(),
    )
    trigger = ResolutionTrigger(incident_id="inc-001", previous_state="on_hold", current_state="active")
    result = await svc.process(trigger)
    assert result.result["trigger_eligible"] is True
    assert result.result["action"] != ResolutionAction.IGNORED.value


@pytest.mark.asyncio
async def test_D17_pending_to_active_is_ignored():
    """PENDING → ACTIVE → now ignored by Resolution Agent."""
    svc = _make_resolution_service()
    trigger = ResolutionTrigger(incident_id="inc-001", previous_state="pending", current_state="active")
    result = await svc.process(trigger)
    assert result.result["trigger_eligible"] is False
    assert result.result["action"] == ResolutionAction.IGNORED.value


@pytest.mark.asyncio
async def test_D18_in_progress_to_active_is_ignored():
    """IN_PROGRESS → ACTIVE → ignored."""
    svc = _make_resolution_service()
    trigger = ResolutionTrigger(incident_id="inc-001", previous_state="in_progress", current_state="active")
    result = await svc.process(trigger)
    assert result.result["trigger_eligible"] is False
    assert result.result["action"] == ResolutionAction.IGNORED.value


@pytest.mark.asyncio
async def test_D19_new_to_active_is_ignored():
    """NEW → ACTIVE → ignored."""
    svc = _make_resolution_service()
    trigger = ResolutionTrigger(incident_id="inc-001", previous_state="new", current_state="active")
    result = await svc.process(trigger)
    assert result.result["trigger_eligible"] is False
    assert result.result["action"] == ResolutionAction.IGNORED.value


@pytest.mark.asyncio
async def test_D20_on_hold_to_active_engineer_note_ignored():
    """ON_HOLD → ACTIVE + ENGINEER latest note → ignored (only USER proceeds)."""
    svc = _make_resolution_service(latest_note_source="ENGINEER")
    trigger = ResolutionTrigger(incident_id="inc-001", previous_state="on_hold", current_state="active")
    result = await svc.process(trigger)
    assert result.result["work_note_eligible"] is False
    assert result.result["action"] == ResolutionAction.IGNORED.value


@pytest.mark.asyncio
async def test_D21_on_hold_to_active_agent_note_ignored():
    """ON_HOLD → ACTIVE + ACKNOWLEDGEMENT_AGENT latest note → ignored (only USER proceeds)."""
    svc = _make_resolution_service(latest_note_source="ACKNOWLEDGEMENT_AGENT")
    trigger = ResolutionTrigger(incident_id="inc-001", previous_state="on_hold", current_state="active")
    result = await svc.process(trigger)
    assert result.result["work_note_eligible"] is False
    assert result.result["action"] == ResolutionAction.IGNORED.value


# ===========================================================================
# E. Auto_activate=False guard — acknowledgement agent must NOT re-activate
# ===========================================================================

@pytest.mark.anyio
async def test_E_acknowledgement_work_note_does_not_reactivate(db_session):
    """
    When AcknowledgementService writes its work note with auto_activate=False,
    the incident must remain on_hold (not be moved back to in_progress).
    """
    inc = await _create_incident(db_session, state="on_hold")
    svc = WorkNoteService(db_session)

    # This is what AcknowledgementService does after setting on_hold:
    await svc.add_note(
        incident_id=inc.id,
        message="Acknowledgement Agent executed. Incident set to Pending.",
        source_type=WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT,
        source_name="AcknowledgementAgent",
        action_type=WorkNoteActionType.SEND_ACKNOWLEDGEMENT,
        auto_activate=False,  # intentional — must NOT flip back to in_progress
    )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "on_hold", (
        "AcknowledgementService work note must not undo the intentional on_hold state"
    )


@pytest.mark.anyio
async def test_E_activation_creates_state_change_audit_note(db_session):
    """
    When auto-activation fires, a STATE_CHANGE audit work note must be created
    in addition to the original note.
    """
    from sqlalchemy import select as sa_select
    from app.modules.work_notes.model import IncidentWorkNote

    inc = await _create_incident(db_session, state="on_hold")
    svc = WorkNoteService(db_session)

    await svc.add_note(
        incident_id=inc.id,
        message="User responded.",
        source_type=WorkNoteSourceType.USER,
        source_name="User",
        auto_activate=True,
    )

    # Fetch all work notes for this incident
    result = await db_session.execute(
        sa_select(IncidentWorkNote)
        .where(IncidentWorkNote.incident_id == inc.id)
        .order_by(IncidentWorkNote.created_at.asc())
    )
    notes = result.scalars().all()

    # Should have at least 2: the activation STATE_CHANGE note + the original note
    assert len(notes) >= 2

    action_types = [n.action_type for n in notes]
    assert WorkNoteActionType.STATE_CHANGE.value in action_types

    state_note = next(n for n in notes if n.action_type == WorkNoteActionType.STATE_CHANGE.value)
    assert "in_progress" in state_note.message.lower() or "work note" in state_note.message.lower()
