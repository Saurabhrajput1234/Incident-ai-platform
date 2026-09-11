"""
Focused tests for the triggering-work-note-ID fix.

Problem fixed
-------------
When a work note causes ON_HOLD → ACTIVE, the system also automatically
creates a SYSTEM STATE_CHANGE audit note.  Before this fix, ResolutionService
called get_latest() and found the SYSTEM note as the newest record, then
incorrectly rejected the trigger with "Latest work note source is SYSTEM".

Fix
---
WorkNoteService.add_note() now:
  1. Persists the user/engineer note FIRST.
  2. Calls activate_incident_from_work_note(triggering_work_note_id=note.id).

IncidentService._fire_resolution_agent() passes that ID to ResolutionTrigger.

ResolutionService.process() uses get_note_by_id() when a triggering_work_note_id
is present, bypassing get_latest().  Only SYSTEM audit notes are blocked; all
other sources (USER, ENGINEER, agents) are valid triggering notes.

Coverage
--------
T1.  ENGINEER note → ON_HOLD→ACTIVE → Resolution receives ENGINEER note (not SYSTEM)
T2.  USER note → ON_HOLD→ACTIVE → Resolution receives USER note
T3.  TRIAGE_AGENT note → ON_HOLD→ACTIVE → Resolution receives agent note
T4.  SYSTEM note is present but never selected as triggering note
T5.  Manual ON_HOLD→ACTIVE (no triggering note ID) → falls back to get_latest() safely
T6.  Work note added while already ACTIVE → no trigger
T7.  Field update without state change → no trigger
T8.  Existing SYSTEM-guard: trigger with triggering_work_note_id=None + get_latest=SYSTEM → IGNORED
T9.  triggering_work_note_id provided but note not found → falls back to get_latest()
"""
from __future__ import annotations

import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

from sqlalchemy import select

from app.modules.incidents.model import Incident
from app.modules.incidents.enums import IncidentPriority, IncidentCategory
from app.modules.incidents.service import IncidentService
from app.modules.incidents.schemas import IncidentUpdate
from app.modules.work_notes.service import WorkNoteService
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType
from app.modules.agents.resolution.service import ResolutionService
from app.modules.agents.resolution.schemas import ResolutionTrigger, ResolutionAction, LLMAnalysis
from app.modules.agents.base.response import AgentResponse


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _create_incident(db, state: str = "on_hold") -> Incident:
    inc = Incident(
        id=str(uuid.uuid4()),
        incident_number=f"INC{uuid.uuid4().hex[:7].upper()}",
        short_description="Resolution trigger note test",
        priority=IncidentPriority.MEDIUM.value,
        state=state,
    )
    db.add(inc)
    await db.commit()
    await db.refresh(inc)
    return inc


async def _reload_incident(db, incident_id: str) -> Incident:
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Mocked ResolutionService factory (unit tests)
# ---------------------------------------------------------------------------

def _make_svc(
    latest_note_source: str = "USER",
    latest_note_msg: str = "It is resolved.",
    note_by_id_source: str | None = None,
    note_by_id_msg: str = "Specific note.",
    note_by_id_returns_none: bool = False,
    agent_response: AgentResponse | None = None,
) -> ResolutionService:
    """Build a ResolutionService with all sub-services mocked."""
    from datetime import date
    from app.modules.context.schemas import AIContext, IncidentContext, EngineerContext

    db = AsyncMock()
    svc = ResolutionService(db)

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

    # latest work note (returned by get_latest)
    latest_note = MagicMock()
    latest_note.source_type = latest_note_source
    latest_note.message = latest_note_msg
    latest_note.created_at = datetime.now(timezone.utc)

    # note returned by get_note_by_id
    if note_by_id_returns_none:
        specific_note = None
    else:
        specific_note = MagicMock()
        specific_note.source_type = note_by_id_source or latest_note_source
        specific_note.message = note_by_id_msg
        specific_note.created_at = datetime.now(timezone.utc)

    svc.work_note_svc = AsyncMock()
    svc.work_note_svc.get_latest.return_value = latest_note
    svc.work_note_svc.get_note_by_id.return_value = specific_note
    svc.work_note_svc.add_note.return_value = MagicMock(id="audit-wn-1")

    ack_note = MagicMock()
    ack_note.source_type = WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT.value
    svc.work_note_svc.get_by_source_type.return_value = [ack_note]

    svc.pending_cycle_svc = AsyncMock()
    cycle = MagicMock()
    cycle.id = "cycle-1"
    svc.pending_cycle_svc.cancel_active_cycle.return_value = cycle

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
                default_shift="Shift1", current_shift="Shift1",
                is_available=True, is_shift_active=True,
                roster_date=datetime.now(timezone.utc).date(),
            )
        ],
        context_date=datetime.now(timezone.utc).date(),
        created_at=datetime.now(timezone.utc),
    )
    svc.context_service = AsyncMock()
    svc.context_service.build_for_incident.return_value = ctx

    from app.integrations.notifications.schemas import NotificationResult, NotificationChannel

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


def _positive_resp() -> AgentResponse:
    from app.modules.agents.resolution.schemas import ResolutionIntent
    return AgentResponse(
        success=True,
        agent_name="ResolutionAgent",
        result={"llm_analysis": LLMAnalysis(
            intent=ResolutionIntent.ISSUE_RESOLVED,
            positive_resolution=True, confidence=0.95,
            summary="Resolved.", next_best_action="Close.",
        ).model_dump()},
    )


# ===========================================================================
# T1–T3: Work-note-driven trigger uses the triggering note, not get_latest
# ===========================================================================

@pytest.mark.asyncio
async def test_T1_engineer_note_ignored_at_step4():
    """
    ResolutionService must ignore ENGINEER triggering notes.
    When triggering_work_note_source is None (manual fallback path) and
    get_note_by_id returns an ENGINEER note, step 4 rejects it.
    Only USER is eligible.
    """
    svc = _make_svc(
        latest_note_source="SYSTEM",       # what get_latest() would return
        note_by_id_source="ENGINEER",      # what get_note_by_id() returns
        note_by_id_msg="Issue resolved! close the ticket.",
    )
    trigger = ResolutionTrigger(
        incident_id="inc-001",
        previous_state="on_hold",
        current_state="active",
        triggering_work_note_id="wn-engineer-001",
        # triggering_work_note_source intentionally None — simulates path where
        # source wasn't threaded (e.g. legacy call or manual path)
    )
    result = await svc.process(trigger)

    # get_note_by_id must have been called (step 3 loaded the note)
    svc.work_note_svc.get_note_by_id.assert_called_once_with("wn-engineer-001")

    # But step 4 rejects ENGINEER — only USER is eligible
    assert result.result["work_note_eligible"] is False
    assert result.result["action"] == ResolutionAction.IGNORED.value


@pytest.mark.asyncio
async def test_T1b_pending_agent_source_on_trigger_ignored_fast_path():
    """
    When triggering_work_note_source="PENDING_AGENT" is set on the trigger,
    step 1b ignores it immediately — no DB calls needed.
    """
    svc = _make_svc(
        latest_note_source="SYSTEM",
        note_by_id_source="PENDING_AGENT",
    )
    trigger = ResolutionTrigger(
        incident_id="inc-001",
        previous_state="on_hold",
        current_state="active",
        triggering_work_note_id="wn-pending-001",
        triggering_work_note_source="PENDING_AGENT",  # fast path
    )
    result = await svc.process(trigger)

    # Fast-path: neither get_note_by_id nor get_latest should be called
    svc.work_note_svc.get_note_by_id.assert_not_called()
    svc.work_note_svc.get_latest.assert_not_called()

    assert result.result["action"] == ResolutionAction.IGNORED.value


@pytest.mark.asyncio
async def test_T2_user_note_used_not_system_note():
    """
    USER note is the triggering note; SYSTEM note exists as the latest DB entry.
    ResolutionService must use the USER note.
    """
    svc = _make_svc(
        latest_note_source="SYSTEM",
        note_by_id_source="USER",
        note_by_id_msg="Yes, the issue is resolved.",
        agent_response=_positive_resp(),
    )
    trigger = ResolutionTrigger(
        incident_id="inc-001",
        previous_state="on_hold",
        current_state="active",
        triggering_work_note_id="wn-user-001",
    )
    result = await svc.process(trigger)

    svc.work_note_svc.get_note_by_id.assert_called_once_with("wn-user-001")
    svc.work_note_svc.get_latest.assert_not_called()
    assert result.result["work_note_eligible"] is True
    assert result.result["latest_work_note_source"] == "USER"


@pytest.mark.asyncio
async def test_T3_triage_agent_note_ignored():
    """
    TRIAGE_AGENT note is the triggering note — ignored (not USER).
    """
    svc = _make_svc(
        latest_note_source="SYSTEM",
        note_by_id_source="TRIAGE_AGENT",
        note_by_id_msg="Triage re-run complete.",
    )
    trigger = ResolutionTrigger(
        incident_id="inc-001",
        previous_state="on_hold",
        current_state="active",
        triggering_work_note_id="wn-triage-001",
    )
    result = await svc.process(trigger)

    # Step 3 loads the note, step 4 rejects it (not USER)
    svc.work_note_svc.get_note_by_id.assert_called_once_with("wn-triage-001")
    assert result.result["work_note_eligible"] is False
    assert result.result["action"] == ResolutionAction.IGNORED.value


@pytest.mark.asyncio
async def test_T4_system_note_as_triggering_note_is_still_blocked():
    """
    If for any reason a SYSTEM note ID is passed as triggering_work_note_id,
    it must still be rejected — SYSTEM notes are always audit records.
    """
    svc = _make_svc(
        latest_note_source="SYSTEM",
        note_by_id_source="SYSTEM",
        note_by_id_msg="Audit: state changed.",
    )
    trigger = ResolutionTrigger(
        incident_id="inc-001",
        previous_state="on_hold",
        current_state="active",
        triggering_work_note_id="wn-system-001",
    )
    result = await svc.process(trigger)

    svc.work_note_svc.get_note_by_id.assert_called_once_with("wn-system-001")
    assert result.result["work_note_eligible"] is False
    assert result.result["action"] == ResolutionAction.IGNORED.value


# ===========================================================================
# T5: Manual state change — no triggering note ID — falls back to get_latest
# ===========================================================================

@pytest.mark.asyncio
async def test_T5_manual_state_change_no_triggering_note_uses_get_latest():
    """
    Manual engineer state change (ON_HOLD → ACTIVE via update_incident) provides
    no triggering_work_note_id.  ResolutionService falls back to get_latest().
    """
    svc = _make_svc(
        latest_note_source="USER",
        latest_note_msg="Manual check: everything is fine.",
        agent_response=_positive_resp(),
    )
    trigger = ResolutionTrigger(
        incident_id="inc-001",
        previous_state="on_hold",
        current_state="active",
        triggering_work_note_id=None,   # no specific note — manual change
    )
    result = await svc.process(trigger)

    # get_latest must be called (no triggering_work_note_id)
    svc.work_note_svc.get_latest.assert_called_once()
    # get_note_by_id must NOT be called
    svc.work_note_svc.get_note_by_id.assert_not_called()
    assert result.result["work_note_eligible"] is True


# ===========================================================================
# T6, T7: No trigger for wrong conditions
# ===========================================================================

@pytest.mark.anyio
async def test_T6_no_trigger_when_already_active(db_session):
    """Adding a work note to an already active incident does not trigger Resolution Agent."""
    inc = await _create_incident(db_session, state="in_progress")
    wn_svc = WorkNoteService(db_session)

    with patch.object(IncidentService, "_fire_resolution_agent", new_callable=AsyncMock) as mock_fire:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Still working on it.",
            source_type=WorkNoteSourceType.USER,
            source_name="Bob",
            auto_activate=True,
        )

    mock_fire.assert_not_awaited()


@pytest.mark.anyio
async def test_T7_field_update_no_trigger(db_session):
    """Engineer updates priority on ON_HOLD incident — no state change, no trigger."""
    inc = await _create_incident(db_session, state="on_hold")
    inc_svc = IncidentService(db_session)

    with patch.object(IncidentService, "_fire_resolution_agent", new_callable=AsyncMock) as mock_fire:
        await inc_svc.update_incident(inc.id, IncidentUpdate(priority=IncidentPriority.HIGH))

    mock_fire.assert_not_awaited()


# ===========================================================================
# T8: SYSTEM note via get_latest (manual path, no triggering ID) → still IGNORED
# ===========================================================================

@pytest.mark.asyncio
async def test_T8_system_note_via_get_latest_is_ignored():
    """
    If triggering_work_note_id is None and get_latest() returns a SYSTEM note,
    the agent must still be ignored (original bug case for manual state changes).
    """
    svc = _make_svc(
        latest_note_source="SYSTEM",
        latest_note_msg="Incident automatically moved to In Progress.",
    )
    trigger = ResolutionTrigger(
        incident_id="inc-001",
        previous_state="on_hold",
        current_state="active",
        triggering_work_note_id=None,
    )
    result = await svc.process(trigger)

    svc.work_note_svc.get_latest.assert_called_once()
    assert result.result["work_note_eligible"] is False
    assert result.result["action"] == ResolutionAction.IGNORED.value


# ===========================================================================
# T9: triggering_work_note_id provided but note not found → fallback to get_latest
# ===========================================================================

@pytest.mark.asyncio
async def test_T9_triggering_note_not_found_falls_back_to_get_latest():
    """
    If get_note_by_id returns None (note was deleted or ID is wrong),
    ResolutionService falls back to get_latest() gracefully.
    """
    svc = _make_svc(
        latest_note_source="USER",
        latest_note_msg="Fallback note.",
        note_by_id_returns_none=True,
        agent_response=_positive_resp(),
    )
    trigger = ResolutionTrigger(
        incident_id="inc-001",
        previous_state="on_hold",
        current_state="active",
        triggering_work_note_id="wn-missing-001",
    )
    result = await svc.process(trigger)

    svc.work_note_svc.get_note_by_id.assert_called_once_with("wn-missing-001")
    svc.work_note_svc.get_latest.assert_called_once()
    assert result.result["work_note_eligible"] is True


# ===========================================================================
# Integration: verify triggering_work_note_id is threaded through correctly
# ===========================================================================

@pytest.mark.anyio
async def test_integration_triggering_note_id_passed_to_trigger(db_session):
    """
    DB integration: when add_note causes ON_HOLD→ACTIVE,
    _fire_resolution_agent is called with the user note's ID, not None.
    """
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    captured_ids: list[str | None] = []

    async def _capture(self, *, incident_id: str, triggering_work_note_id: str | None = None, triggering_work_note_source: str | None = None) -> None:  # noqa: N805
        captured_ids.append(triggering_work_note_id)

    with patch.object(IncidentService, "_fire_resolution_agent", _capture):
        note = await wn_svc.add_note(
            incident_id=inc.id,
            message="Issue resolved! close the ticket.",
            source_type=WorkNoteSourceType.ENGINEER,
            source_name="Aman",
            auto_activate=True,
        )

    # The trigger must carry the ID of the ENGINEER note, not None
    assert len(captured_ids) == 1
    assert captured_ids[0] == note.id, (
        f"Resolution trigger received triggering_work_note_id={captured_ids[0]!r} "
        f"but expected the ENGINEER note id={note.id!r}"
    )
