"""
Tests for the automatic Resolution Alert Agent trigger.

Architecture under test
-----------------------
The Resolution trigger lives EXCLUSIVELY in IncidentService._fire_resolution_agent().
It fires only when an actual ON_HOLD → IN_PROGRESS (active) state transition is
persisted to the database.

WorkNoteService.add_note() has NO resolution trigger logic whatsoever.
WorkNoteService delegates the state change to
IncidentService.activate_incident_from_work_note() via a local import.
That method owns:
  - reading current state
  - calling repo.update(state="in_progress")
  - writing the STATE_CHANGE audit work note
  - firing _fire_resolution_agent() if old_state == "on_hold"

There are THREE paths that can trigger the Resolution Agent:
  Path A — Work note addition:
      add_note(auto_activate=True)
        → WorkNoteService._maybe_activate_incident()
          → IncidentService.activate_incident_from_work_note()  [local import]
            → _fire_resolution_agent()  if on_hold → active

  Path B — Manual engineer state change:
      IncidentService.update_incident(state="in_progress")
        → _fire_resolution_agent()  if old_state was on_hold

  Path C — Agent internal state change:
      IncidentService.update_incident_internal(state="in_progress")
        → _fire_resolution_agent()  if old_state was on_hold

Patching strategy
-----------------
Since _fire_resolution_agent lives on IncidentService, we patch it at the
CLASS level:

    patch.object(IncidentService, "_fire_resolution_agent", new_callable=AsyncMock)

This intercepts the call regardless of which IncidentService instance was
created (including the instance created inside _maybe_activate_incident's
local import).

Coverage map
------------
A. Work-note-driven trigger (DB integration tests)
   F1.  ON_HOLD  + USER note      → work note saved, state=in_progress, trigger fires
   F2.  ON_HOLD  + ENGINEER note  → state=in_progress, trigger fires
   F3.  ON_HOLD  + AI-agent note  → state=in_progress, trigger fires

B. No Resolution trigger — wrong previous state
   F4.  in_progress + USER note   → state unchanged, trigger NOT fired
   F5.  NEW      + USER note      → state=in_progress, trigger NOT fired
   F6.  PENDING  + USER note      → state=in_progress, trigger NOT fired

C. Field update — no trigger
   F7.  ON_HOLD + priority update via update_incident() → no trigger
   F8.  ON_HOLD + category update via update_incident() → no trigger

D. Acknowledgement regression guard
   F9.  add_note(auto_activate=False) on ON_HOLD → no activation, no trigger

E. Correct trigger contract (unit, mocked)
   F10. ON_HOLD → ACTIVE via work note → IncidentService receives correct trigger args
   F11. ON_HOLD + ENGINEER note  → trigger fires (ResolutionService internally ignores)
   F12. PENDING + USER note      → trigger NOT fired

F. Manual state-change path
   F13. Engineer manually sets ON_HOLD → in_progress via update_incident() → trigger fires
   F14. Engineer manually sets ON_HOLD → on_hold (no change) → trigger NOT fired

G. Idempotency / error handling
   F15. Work note twice: trigger fires only on first (second call: already in_progress)
   F16. ResolutionService raises → work note still returned, incident still activated

H. Architecture invariant
   F17. WorkNoteService.add_note() does NOT have _fire_resolution_agent attribute
        (confirms no resolution logic leaked back into WorkNoteService)
   F18. add_note() on ON_HOLD incident does NOT directly call ResolutionService
        (the trigger only fires through IncidentService)
"""
from __future__ import annotations

import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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


# ---------------------------------------------------------------------------
# DB helpers
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


# ===========================================================================
# A. Work-note-driven trigger — DB integration tests
#    Patch: IncidentService._fire_resolution_agent (class-level)
# ===========================================================================

@pytest.mark.anyio
async def test_F1_on_hold_user_note_fires_trigger(db_session):
    """
    ON_HOLD + USER work note → state=in_progress, IncidentService fires trigger.
    WorkNoteService itself has no trigger logic.
    """
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    with patch.object(
        IncidentService, "_fire_resolution_agent", new_callable=AsyncMock
    ) as mock_fire:
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

    # Trigger fired exactly once from IncidentService, NOT from WorkNoteService
    mock_fire.assert_awaited_once()
    assert mock_fire.call_args.kwargs["incident_id"] == inc.id


@pytest.mark.anyio
async def test_F2_on_hold_engineer_note_fires_trigger(db_session):
    """ON_HOLD + ENGINEER work note → trigger fires via IncidentService."""
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    with patch.object(
        IncidentService, "_fire_resolution_agent", new_callable=AsyncMock
    ) as mock_fire:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Engineer added diagnostics.",
            source_type=WorkNoteSourceType.ENGINEER,
            source_name="Alice Smith",
            auto_activate=True,
        )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"
    mock_fire.assert_awaited_once()
    assert mock_fire.call_args.kwargs["incident_id"] == inc.id


@pytest.mark.anyio
async def test_F3_on_hold_agent_activity_note_fires_trigger(db_session):
    """ON_HOLD + TRIAGE_AGENT note (auto_activate=True) → trigger fires."""
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    with patch.object(
        IncidentService, "_fire_resolution_agent", new_callable=AsyncMock
    ) as mock_fire:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Triage re-analysis complete.",
            source_type=WorkNoteSourceType.TRIAGE_AGENT,
            source_name="TriageAgent",
            auto_activate=True,
        )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"
    mock_fire.assert_awaited_once()


# ===========================================================================
# B. No Resolution trigger — wrong previous state
# ===========================================================================

@pytest.mark.anyio
async def test_F4_active_user_note_does_not_fire_trigger(db_session):
    """Already in_progress + USER note → no state change, trigger NOT fired."""
    inc = await _create_incident(db_session, state="in_progress")
    wn_svc = WorkNoteService(db_session)

    with patch.object(
        IncidentService, "_fire_resolution_agent", new_callable=AsyncMock
    ) as mock_fire:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Still looking into it.",
            source_type=WorkNoteSourceType.USER,
            source_name="Bob",
            auto_activate=True,
        )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"
    mock_fire.assert_not_awaited()


@pytest.mark.anyio
async def test_F5_new_user_note_activates_but_no_trigger(db_session):
    """NEW + USER note → state=in_progress, trigger NOT fired (prev was 'new')."""
    inc = await _create_incident(db_session, state="new")
    wn_svc = WorkNoteService(db_session)

    with patch.object(
        IncidentService, "_fire_resolution_agent", new_callable=AsyncMock
    ) as mock_fire:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Here's more info.",
            source_type=WorkNoteSourceType.USER,
            source_name="Carol",
            auto_activate=True,
        )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"
    mock_fire.assert_not_awaited()


@pytest.mark.anyio
async def test_F6_pending_user_note_activates_but_no_trigger(db_session):
    """PENDING + USER note → state=in_progress, trigger NOT fired."""
    inc = await _create_incident(db_session, state="pending")
    wn_svc = WorkNoteService(db_session)

    with patch.object(
        IncidentService, "_fire_resolution_agent", new_callable=AsyncMock
    ) as mock_fire:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Checking in.",
            source_type=WorkNoteSourceType.USER,
            source_name="Dave",
            auto_activate=True,
        )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"
    mock_fire.assert_not_awaited()


# ===========================================================================
# C. Field update — no trigger
# ===========================================================================

@pytest.mark.anyio
async def test_F7_on_hold_priority_update_no_trigger(db_session):
    """
    ON_HOLD + engineer updates priority via update_incident() →
    state remains on_hold, trigger NOT fired.
    """
    inc = await _create_incident(db_session, state="on_hold")
    inc_svc = IncidentService(db_session)

    with patch.object(
        IncidentService, "_fire_resolution_agent", new_callable=AsyncMock
    ) as mock_fire:
        await inc_svc.update_incident(inc.id, IncidentUpdate(priority=IncidentPriority.HIGH))

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "on_hold"
    mock_fire.assert_not_awaited()


@pytest.mark.anyio
async def test_F8_on_hold_category_update_no_trigger(db_session):
    """ON_HOLD + category update → state remains on_hold, trigger NOT fired."""
    inc = await _create_incident(db_session, state="on_hold")
    inc_svc = IncidentService(db_session)

    with patch.object(
        IncidentService, "_fire_resolution_agent", new_callable=AsyncMock
    ) as mock_fire:
        await inc_svc.update_incident(inc.id, IncidentUpdate(category=IncidentCategory.SOFTWARE))

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "on_hold"
    mock_fire.assert_not_awaited()


# ===========================================================================
# D. Acknowledgement regression guard
# ===========================================================================

@pytest.mark.anyio
async def test_F9_acknowledgement_agent_auto_activate_false_no_trigger(db_session):
    """
    AcknowledgementService writes its work note with auto_activate=False.
    The note must NOT activate the incident and must NOT trigger Resolution Agent.
    """
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    with patch.object(
        IncidentService, "_fire_resolution_agent", new_callable=AsyncMock
    ) as mock_fire:
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
    mock_fire.assert_not_awaited()


# ===========================================================================
# E. Correct trigger contract (unit tests with mocked IncidentService)
# ===========================================================================

@pytest.mark.anyio
async def test_F10_trigger_contract_correct_args(db_session):
    """
    ON_HOLD → ACTIVE via work note:
    IncidentService._fire_resolution_agent() is called with incident_id only.
    The trigger contract (previous_state="on_hold", current_state="active")
    is built inside _fire_resolution_agent itself.
    """
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    fired_with: list[str] = []

    async def _capture(self, *, incident_id: str, triggering_work_note_id: str | None = None, triggering_work_note_source: str | None = None) -> None:  # noqa: N805
        fired_with.append(incident_id)

    with patch.object(IncidentService, "_fire_resolution_agent", _capture):
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Issue is resolved.",
            source_type=WorkNoteSourceType.USER,
            source_name="Bob",
            auto_activate=True,
        )

    assert len(fired_with) == 1
    assert fired_with[0] == inc.id


@pytest.mark.anyio
async def test_F11_on_hold_engineer_note_trigger_fires_resolution_ignores(db_session):
    """
    ON_HOLD + ENGINEER note → trigger fires (IncidentService._fire_resolution_agent).
    ResolutionService internally ignores ENGINEER notes — but IncidentService
    fires the trigger regardless of note source type.
    """
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    with patch.object(
        IncidentService, "_fire_resolution_agent", new_callable=AsyncMock
    ) as mock_fire:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Engineer info.",
            source_type=WorkNoteSourceType.ENGINEER,
            source_name="Alice",
            auto_activate=True,
        )

    mock_fire.assert_awaited_once()
    assert mock_fire.call_args.kwargs["incident_id"] == inc.id


@pytest.mark.anyio
async def test_F12_pending_state_no_trigger(db_session):
    """
    PENDING + USER note → state moves to in_progress, trigger NOT fired
    (previous_state was "pending", not "on_hold").
    """
    inc = await _create_incident(db_session, state="pending")
    wn_svc = WorkNoteService(db_session)

    with patch.object(
        IncidentService, "_fire_resolution_agent", new_callable=AsyncMock
    ) as mock_fire:
        await wn_svc.add_note(
            incident_id=inc.id,
            message="Checking in.",
            source_type=WorkNoteSourceType.USER,
            source_name="Carol",
            auto_activate=True,
        )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"
    mock_fire.assert_not_awaited()


# ===========================================================================
# F. Manual state-change path — IncidentService.update_incident()
# ===========================================================================

@pytest.mark.anyio
async def test_F13_manual_on_hold_to_active_fires_trigger(db_session):
    """
    Engineer manually sets state ON_HOLD → in_progress via update_incident().
    Resolution trigger fires via IncidentService._fire_resolution_agent().
    """
    inc = await _create_incident(db_session, state="on_hold")
    inc_svc = IncidentService(db_session)

    with patch.object(
        IncidentService, "_fire_resolution_agent", new_callable=AsyncMock
    ) as mock_fire:
        await inc_svc.update_incident(
            inc.id,
            IncidentUpdate(state="in_progress"),
        )

    refreshed = await _reload_incident(db_session, inc.id)
    assert refreshed.state == "in_progress"
    mock_fire.assert_awaited_once()
    assert mock_fire.call_args.kwargs["incident_id"] == inc.id


@pytest.mark.anyio
async def test_F14_manual_on_hold_to_on_hold_no_trigger(db_session):
    """
    update_incident() with no state change → trigger NOT fired.
    (Only a real ON_HOLD → in_progress triggers it.)
    """
    inc = await _create_incident(db_session, state="on_hold")
    inc_svc = IncidentService(db_session)

    with patch.object(
        IncidentService, "_fire_resolution_agent", new_callable=AsyncMock
    ) as mock_fire:
        # Update priority only — no state change
        await inc_svc.update_incident(
            inc.id,
            IncidentUpdate(priority=IncidentPriority.HIGH),
        )

    mock_fire.assert_not_awaited()


# ===========================================================================
# G. Idempotency / error handling
# ===========================================================================

@pytest.mark.anyio
async def test_F15_second_call_no_duplicate_trigger(db_session):
    """
    add_note called twice on same ON_HOLD incident:
    - First call: on_hold → in_progress → trigger fires once
    - Second call: already in_progress → no transition → trigger NOT fired
    """
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    fire_count = 0

    async def _count(self, *, incident_id: str, triggering_work_note_id: str | None = None, triggering_work_note_source: str | None = None) -> None:  # noqa: N805
        nonlocal fire_count
        fire_count += 1

    with patch.object(IncidentService, "_fire_resolution_agent", _count):
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

    assert fire_count == 1, (
        "Resolution trigger must fire exactly once — "
        "second call finds incident already in_progress."
    )


@pytest.mark.anyio
async def test_F16_resolution_agent_failure_does_not_fail_work_note(db_session):
    """
    If ResolutionService.process() raises inside IncidentService._fire_resolution_agent(),
    the error is swallowed — the work note and the state transition must both succeed.
    """
    inc = await _create_incident(db_session, state="on_hold")
    wn_svc = WorkNoteService(db_session)

    with patch(
        "app.modules.agents.resolution.service.ResolutionService",
    ) as MockRS:
        mock_rs_instance = AsyncMock()
        mock_rs_instance.process.side_effect = RuntimeError("Simulated LLM failure")
        MockRS.return_value = mock_rs_instance

        note = await wn_svc.add_note(
            incident_id=inc.id,
            message="User responded.",
            source_type=WorkNoteSourceType.USER,
            source_name="Bob",
            auto_activate=True,
        )

    assert note is not None
    assert note.incident_id == inc.id

    inc_id = inc.id
    db_session.expire_all()
    refreshed = await _reload_incident(db_session, inc_id)
    assert refreshed.state == "in_progress", (
        "Incident must still be activated even when Resolution Agent fails"
    )


# ===========================================================================
# H. Architecture invariant — WorkNoteService must not own any trigger logic
# ===========================================================================

def test_F17_work_note_service_has_no_fire_resolution_method():
    """
    WorkNoteService must NOT have _fire_resolution_agent.
    This is the definitive check that the trigger did not leak back.
    """
    assert not hasattr(WorkNoteService, "_fire_resolution_agent"), (
        "WorkNoteService must not have _fire_resolution_agent — "
        "the trigger belongs exclusively to IncidentService."
    )


def test_F18_work_note_service_has_no_resolution_constants():
    """
    WorkNoteService module must not define _RESOLUTION_TRIGGER_* constants.
    """
    import app.modules.work_notes.service as wn_module
    assert not hasattr(wn_module, "_RESOLUTION_TRIGGER_PREV_STATE"), (
        "_RESOLUTION_TRIGGER_PREV_STATE must not exist in work_notes.service"
    )
    assert not hasattr(wn_module, "_RESOLUTION_TRIGGER_CURR_STATE"), (
        "_RESOLUTION_TRIGGER_CURR_STATE must not exist in work_notes.service"
    )
