"""
Tests for the automatic Resolution Alert Agent trigger.

Architecture under test
-----------------------
The Resolution trigger now flows through the event bus.
When an ON_HOLD → IN_PROGRESS state transition is persisted, IncidentService
publishes an IncidentStateChangedEvent.  ResolutionHandler picks this up and
calls ResolutionService.

WorkNoteService.add_note() also publishes a WorkNoteAddedEvent (new path).
It delegates auto-activation to IncidentService.activate_incident_from_work_note(),
which publishes an IncidentStateChangedEvent when state changes.

Patching strategy
-----------------
We patch the event_bus singleton's publish method:

    patch.object(event_bus, "publish", new_callable=AsyncMock)

This intercepts all events published through the bus regardless of which service
instance published them.  We then inspect the call_args_list to find events
of type IncidentStateChangedEvent with previous_state=="on_hold".

Coverage map
------------
A. Work-note-driven trigger (DB integration tests)
   F1.  ON_HOLD  + USER note      → work note saved, state=in_progress, StateChanged event fired
   F2.  ON_HOLD  + ENGINEER note  → state=in_progress, StateChanged event fired
   F3.  ON_HOLD  + AI-agent note  → state=in_progress, StateChanged event fired

B. No Resolution trigger — wrong previous state
   F4.  in_progress + USER note   → state unchanged, no on_hold→active StateChanged event
   F5.  NEW      + USER note      → state=in_progress, no on_hold→active event
   F6.  PENDING  + USER note      → state=in_progress, no on_hold→active event

C. Field update — no trigger
   F7.  ON_HOLD + priority update via update_incident() → no trigger
   F8.  ON_HOLD + category update via update_incident() → no trigger

D. Acknowledgement regression guard
   F9.  add_note(auto_activate=False) on ON_HOLD → no activation, no trigger

E. Correct trigger contract (unit, mocked)
   F10. ON_HOLD → ACTIVE via work note → StateChanged event carries correct incident_id
   F11. ON_HOLD + ENGINEER note  → StateChanged event fires (ResolutionHandler filters source)
   F12. PENDING + USER note      → no on_hold trigger (previous was 'pending')

F. Manual state-change path
   F13. Engineer manually sets ON_HOLD → in_progress → StateChanged event fires
   F14. Engineer manually sets ON_HOLD → no state change → no StateChanged event

G. Idempotency / error handling
   F15. Work note twice: on_hold→active event fires only on first transition
   F16. ResolutionService raises → work note still returned, incident still activated

H. Architecture invariant
   F17. WorkNoteService.add_note() does NOT have _fire_resolution_agent attribute
   F18. add_note() on ON_HOLD incident does NOT directly call ResolutionService
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
from app.modules.agents.resolution.schemas import (
    ResolutionAction,
    ResolutionTrigger,
    LLMAnalysis,
)
from app.modules.agents.base.response import AgentResponse
from app.integrations.notifications.schemas import NotificationChannel, NotificationResult
from app.orchestrator.bus import event_bus
from app.orchestrator.events import IncidentStateChangedEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_incident(db, state: str = "on_hold") -> Incident:
    inc = Incident(
        id=str(uuid.uuid4()),
        incident_number=f"INC{uuid.uuid4().hex[:7].upper()}",
        short_description="Auto-trigger test",
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


def _on_hold_state_events(mock_publish) -> list:
    """Extract IncidentStateChangedEvents with previous_state==on_hold from publish calls."""
    result = []
    for c in mock_publish.call_args_list:
        event = c.args[0] if c.args else None
        if (
            isinstance(event, IncidentStateChangedEvent)
            and event.previous_state == "on_hold"
        ):
            result.append(event)
    return result


# ===========================================================================
# A. Work-note-driven trigger — DB integration tests
# ===========================================================================

@pytest.mark.anyio
async def test_F1_on_hold_user_note_fires_trigger(db_session):
    """ON_HOLD + USER work note → state=in_progress, StateChanged(on_hold→in_progress) fired."""
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        note = await wn_svc.add_note(
            incident_id=inc.id,
            message="The issue is resolved now.",
            source_type=WorkNoteSourceType.USER,
            source_name="Bob (Reporter)",
            auto_activate=True,
        )

    assert note is not None
    assert note.incident_id == inc.id

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"

    on_hold_events = _on_hold_state_events(mock_publish)
    assert len(on_hold_events) == 1
    assert on_hold_events[0].incident_id == inc.id
    assert on_hold_events[0].current_state == "in_progress"


@pytest.mark.anyio
async def test_F2_on_hold_engineer_note_fires_trigger(db_session):
    """ON_HOLD + ENGINEER work note → state=in_progress, StateChanged event fires."""
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Engineer added diagnostics.",
            source_type=WorkNoteSourceType.ENGINEER,
            source_name="Alice Smith",
            auto_activate=True,
        )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"

    on_hold_events = _on_hold_state_events(mock_publish)
    assert len(on_hold_events) == 1
    assert on_hold_events[0].incident_id == inc.id


@pytest.mark.anyio
async def test_F3_on_hold_agent_activity_note_fires_trigger(db_session):
    """ON_HOLD + TRIAGE_AGENT note (auto_activate=True) → StateChanged event fires."""
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Triage re-analysis complete.",
            source_type=WorkNoteSourceType.TRIAGE_AGENT,
            source_name="TriageAgent",
            auto_activate=True,
        )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"

    on_hold_events = _on_hold_state_events(mock_publish)
    assert len(on_hold_events) == 1


# ===========================================================================
# B. No Resolution trigger — wrong previous state
# ===========================================================================

@pytest.mark.anyio
async def test_F4_active_user_note_does_not_fire_trigger(db_session):
    """Already in_progress + USER note → no state change, no on_hold trigger."""
    inc = await _create_incident(db_session, state="in_progress")
    wn_svc = WorkNoteService(db_session)

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Still looking into it.",
            source_type=WorkNoteSourceType.USER,
            source_name="Bob",
            auto_activate=True,
        )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"

    on_hold_events = _on_hold_state_events(mock_publish)
    assert len(on_hold_events) == 0


@pytest.mark.anyio
async def test_F5_new_user_note_activates_but_no_trigger(db_session):
    """NEW + USER note → state=in_progress, no on_hold→active event (prev was 'new')."""
    inc = await _create_incident(db_session, state="new")
    wn_svc = WorkNoteService(db_session)

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Here's more info.",
            source_type=WorkNoteSourceType.USER,
            source_name="Carol",
            auto_activate=True,
        )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"

    on_hold_events = _on_hold_state_events(mock_publish)
    assert len(on_hold_events) == 0


@pytest.mark.anyio
async def test_F6_pending_user_note_activates_but_no_trigger(db_session):
    """PENDING + USER note → state=in_progress, no on_hold trigger."""
    inc = await _create_incident(db_session, state="pending")
    wn_svc = WorkNoteService(db_session)

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Checking in.",
            source_type=WorkNoteSourceType.USER,
            source_name="Dave",
            auto_activate=True,
        )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"

    on_hold_events = _on_hold_state_events(mock_publish)
    assert len(on_hold_events) == 0


# ===========================================================================
# C. Field update — no trigger
# ===========================================================================

@pytest.mark.anyio
async def test_F7_on_hold_priority_update_no_trigger(db_session):
    """ON_HOLD + priority update → state stays on_hold, no StateChanged event."""
    inc = await _create_incident(db_session, state="on_hold")
    inc_svc = IncidentService(db_session)

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        await inc_svc.update_incident(inc.id, IncidentUpdate(priority=IncidentPriority.HIGH))

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "on_hold"

    on_hold_events = _on_hold_state_events(mock_publish)
    assert len(on_hold_events) == 0


@pytest.mark.anyio
async def test_F8_on_hold_category_update_no_trigger(db_session):
    """ON_HOLD + category update → state stays on_hold, no StateChanged event."""
    inc = await _create_incident(db_session, state="on_hold")
    inc_svc = IncidentService(db_session)

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        await inc_svc.update_incident(inc.id, IncidentUpdate(category=IncidentCategory.SOFTWARE))

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "on_hold"

    on_hold_events = _on_hold_state_events(mock_publish)
    assert len(on_hold_events) == 0


# ===========================================================================
# D. Acknowledgement regression guard
# ===========================================================================

@pytest.mark.anyio
async def test_F9_acknowledgement_agent_auto_activate_false_no_trigger(db_session):
    """auto_activate=False on ON_HOLD → no state change, no event."""
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Acknowledgement Agent executed. Incident set to Pending.",
            source_type=WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT,
            source_name="AcknowledgementAgent",
            action_type=WorkNoteActionType.SEND_ACKNOWLEDGEMENT,
            auto_activate=False,
        )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "on_hold", (
        "auto_activate=False must not move the incident to in_progress"
    )

    on_hold_events = _on_hold_state_events(mock_publish)
    assert len(on_hold_events) == 0


# ===========================================================================
# E. Correct trigger contract
# ===========================================================================

@pytest.mark.anyio
async def test_F10_trigger_contract_correct_args(db_session):
    """ON_HOLD → ACTIVE via work note: IncidentStateChangedEvent carries correct incident_id."""
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Issue is resolved.",
            source_type=WorkNoteSourceType.USER,
            source_name="Bob",
            auto_activate=True,
        )

    on_hold_events = _on_hold_state_events(mock_publish)
    assert len(on_hold_events) == 1
    assert on_hold_events[0].incident_id == inc.id
    assert on_hold_events[0].previous_state == "on_hold"
    assert on_hold_events[0].current_state == "in_progress"


@pytest.mark.anyio
async def test_F11_on_hold_engineer_note_trigger_fires_resolution_ignores(db_session):
    """ON_HOLD + ENGINEER note → StateChanged event fires. ResolutionHandler filters source internally."""
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Engineer info.",
            source_type=WorkNoteSourceType.ENGINEER,
            source_name="Alice",
            auto_activate=True,
        )

    on_hold_events = _on_hold_state_events(mock_publish)
    assert len(on_hold_events) == 1
    assert on_hold_events[0].incident_id == inc.id


@pytest.mark.anyio
async def test_F12_pending_state_no_trigger(db_session):
    """PENDING + USER note → state=in_progress but no on_hold→active event (prev was 'pending')."""
    inc = await _create_incident(db_session, state="pending")
    wn_svc = WorkNoteService(db_session)

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Checking in.",
            source_type=WorkNoteSourceType.USER,
            source_name="Carol",
            auto_activate=True,
        )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"

    on_hold_events = _on_hold_state_events(mock_publish)
    assert len(on_hold_events) == 0


# ===========================================================================
# F. Manual state-change path — IncidentService.update_incident()
# ===========================================================================

@pytest.mark.anyio
async def test_F13_manual_on_hold_to_active_fires_trigger(db_session):
    """Engineer manually sets ON_HOLD → in_progress → StateChanged event fires."""
    inc = await _create_incident(db_session, state="on_hold")
    inc_svc = IncidentService(db_session)

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        await inc_svc.update_incident(
            inc.id,
            IncidentUpdate(state="in_progress"),
        )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"

    on_hold_events = _on_hold_state_events(mock_publish)
    assert len(on_hold_events) == 1
    assert on_hold_events[0].incident_id == inc.id


@pytest.mark.anyio
async def test_F14_manual_on_hold_to_on_hold_no_trigger(db_session):
    """Priority-only update on ON_HOLD → no StateChanged event."""
    inc = await _create_incident(db_session, state="on_hold")
    inc_svc = IncidentService(db_session)

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        await inc_svc.update_incident(
            inc.id,
            IncidentUpdate(priority=IncidentPriority.HIGH),
        )

    on_hold_events = _on_hold_state_events(mock_publish)
    assert len(on_hold_events) == 0


# ===========================================================================
# G. Idempotency / error handling
# ===========================================================================

@pytest.mark.anyio
async def test_F15_second_call_no_duplicate_trigger(db_session):
    """
    add_note called twice on same ON_HOLD incident:
    First call fires StateChanged(on_hold→in_progress).
    Second call: already in_progress → no on_hold transition → no duplicate event.
    """
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="First response.",
            source_type=WorkNoteSourceType.USER,
            source_name="Bob",
            auto_activate=True,
        )
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Follow-up.",
            source_type=WorkNoteSourceType.USER,
            source_name="Bob",
            auto_activate=True,
        )

    on_hold_events = _on_hold_state_events(mock_publish)
    assert len(on_hold_events) == 1, (
        "StateChanged(on_hold→in_progress) must fire exactly once — "
        "second call finds incident already in_progress."
    )


@pytest.mark.anyio
async def test_F16_resolution_agent_failure_does_not_fail_work_note(db_session):
    """
    If ResolutionService.process() raises inside ResolutionHandler,
    the error is swallowed — the work note and state transition must both succeed.
    """
    inc = await _create_incident(db_session, state="on_hold")
    inc_id = inc.id
    wn_svc = WorkNoteService(db_session)

    with patch(
        "app.modules.agents.resolution.service.ResolutionService",
    ) as MockRS:
        mock_rs_instance = AsyncMock()
        mock_rs_instance.process.side_effect = RuntimeError("Simulated LLM failure")
        MockRS.return_value = mock_rs_instance

        note = await wn_svc.add_note(
            incident_id=inc_id,
            message="User responded.",
            source_type=WorkNoteSourceType.USER,
            source_name="Bob",
            auto_activate=True,
        )

    assert note is not None
    assert note.incident_id == inc_id

    # Reload fresh from DB without expire_all
    refreshed = await _reload_incident(db_session, inc_id)
    assert refreshed.state == "in_progress", (
        "Incident must still be activated even when Resolution Agent fails"
    )


# ===========================================================================
# H. Architecture invariant — WorkNoteService must not own trigger logic
# ===========================================================================

def test_F17_work_note_service_has_no_fire_resolution_method():
    """WorkNoteService must NOT have _fire_resolution_agent."""
    assert not hasattr(WorkNoteService, "_fire_resolution_agent"), (
        "WorkNoteService must not have _fire_resolution_agent — "
        "the trigger belongs to the event bus orchestration layer."
    )


def test_F18_work_note_service_has_no_resolution_constants():
    """WorkNoteService module must not define _RESOLUTION_TRIGGER_* constants."""
    import app.modules.work_notes.service as wn_module
    assert not hasattr(wn_module, "_RESOLUTION_TRIGGER_PREV_STATE")
    assert not hasattr(wn_module, "_RESOLUTION_TRIGGER_CURR_STATE")
