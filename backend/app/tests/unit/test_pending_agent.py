"""
Unit tests for Pending Agent components:
- PendingReminderRenderer
- PendingWorkNoteAnalyzer
- PendingService (using canonical PendingCycleService)

After the refactor, PendingService.cycle_svc is a PendingCycleService instance.
The duplicate PendingCycleRepository inside the pending agent is gone.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.modules.pending_cycles.enums import PendingCycleStatus
from app.modules.agents.pending.reminder_renderer import PendingReminderRenderer
from app.modules.agents.pending.work_note_analyzer import PendingWorkNoteAnalyzer
from app.modules.agents.pending.service import PendingService
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType


# ---------------------------------------------------------------------------
# Renderer tests (unchanged — no dependency on cycle model)
# ---------------------------------------------------------------------------

def test_reminder_renderer_tier_1():
    renderer = PendingReminderRenderer()
    ctx = {
        "ticket_number": "INC0000064",
        "caller_name": "Tina",
        "short_description": "Cannot access Salesforce",
        "assignment_group": "Apps Run-SFDC",
        "assigned_engineer_name": "Aman Mourya",
        "reminder_count": 1,
        "max_reminders": 3,
        "is_final": False,
    }
    text_content = renderer.render_plain_text_email(ctx)
    assert "Follow-up Reminder (1/3) - Ticket INC0000064" in text_content
    assert "Hello Tina," in text_content
    assert "Reminder 1 of 3" in text_content
    assert "Portal Link:" in text_content

    html_content = renderer.render_html(ctx)
    assert "INC0000064" in html_content
    assert "Pending Ticket Follow-up (1/3)" in html_content


def test_reminder_renderer_tier_3_final():
    renderer = PendingReminderRenderer()
    ctx = {
        "ticket_number": "INC0000064",
        "caller_name": "Tina",
        "short_description": "Cannot access Salesforce",
        "assignment_group": "Apps Run-SFDC",
        "assigned_engineer_name": "Aman Mourya",
        "reminder_count": 3,
        "max_reminders": 3,
        "is_final": True,
    }
    text_content = renderer.render_plain_text_email(ctx)
    assert "FINAL REMINDER (3/3)" in text_content
    assert "FINAL WARNING: Action Required to Prevent Ticket Closure" in text_content

    html_content = renderer.render_html(ctx)
    assert "Final Reminder (3/3)" in html_content


# ---------------------------------------------------------------------------
# Analyzer tests (unchanged — no dependency on cycle model)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyzer_fast_path_acknowledgement_agent():
    analyzer = PendingWorkNoteAnalyzer()
    res = await analyzer.analyze(
        latest_work_note="Acknowledgement Agent executed successfully.\nUser notified to submit RITM.",
        source_name="AcknowledgementAgent",
    )
    assert res.is_caller_action_required is True
    assert res.confidence == 1.0


# ---------------------------------------------------------------------------
# PendingService — uses canonical PendingCycleService (self.cycle_svc)
# ---------------------------------------------------------------------------

def _mock_incident(
    inc_id="inc-123",
    number="INC0000099",
    state="pending",
    caller="Alice",
    assigned_to="Bob",
    group="Support",
    description="Cannot connect to VPN",
    short_description="VPN issue",
):
    m = MagicMock()
    m.id = inc_id
    m.incident_number = number
    m.caller = caller
    m.assigned_to = assigned_to
    m.assignment_group = group
    m.state = state
    m.description = description
    m.short_description = short_description
    return m


def _mock_cycle(
    cycle_id="PC-TEST-001",
    status=PendingCycleStatus.ACTIVE,
    reminder_count=1,
    max_reminders=3,
    next_reminder_at=None,
    incident_id="inc-123",
):
    m = MagicMock()
    m.id = cycle_id
    m.incident_id = incident_id
    m.status = status.value if hasattr(status, "value") else str(status)
    m.reminder_count = reminder_count
    m.max_reminders = max_reminders
    m.next_reminder_at = next_reminder_at
    m.created_at = None
    m.updated_at = None
    return m


def _make_service() -> PendingService:
    """Build a PendingService with all sub-services mocked."""
    db = AsyncMock()
    svc = PendingService(db)
    svc.incident_service = AsyncMock()
    svc.work_note_svc = AsyncMock()
    svc.cycle_svc = AsyncMock()  # canonical PendingCycleService
    svc.analyzer = AsyncMock()
    return svc


# ------ Test: existing active cycle is preserved (force_reminder=False) ------

@pytest.mark.asyncio
async def test_pending_service_preserves_active_cycle():
    """
    When an active cycle exists and force_reminder=False, the service
    preserves the cycle and returns CYCLE_PRESERVED without sending a reminder.
    """
    svc = _make_service()

    existing_cycle = _mock_cycle(reminder_count=1)
    svc.cycle_svc.get_active_cycle.return_value = existing_cycle
    svc.incident_service.get_incident.return_value = _mock_incident(state="pending")

    resp = await svc.process_pending_transition(incident_id="inc-123", force_reminder=False)

    assert resp.success is True
    assert resp.result["action_taken"] == "CYCLE_PRESERVED"
    assert resp.result["cycle_id"] == "PC-TEST-001"
    assert resp.result["email_sent"] is False
    assert resp.result["reminder_count"] == 1

    # cycle_svc.create_cycle_if_not_exists must NOT be called
    svc.cycle_svc.create_cycle_if_not_exists.assert_not_called()
    # cycle_svc.increment_reminder must NOT be called
    svc.cycle_svc.increment_reminder.assert_not_called()
    # No work note added
    svc.work_note_svc.add_note.assert_not_called()


# ------ Test: no active cycle — creates new cycle and sends reminder ------

@pytest.mark.asyncio
async def test_pending_service_creates_new_cycle_and_sends_reminder():
    """
    When no active cycle exists, the service:
    1. Calls create_cycle_if_not_exists.
    2. Calls increment_reminder (count 0 → 1).
    3. Adds a work note via WorkNoteService.
    """
    svc = _make_service()

    svc.cycle_svc.get_active_cycle.return_value = None

    # create_cycle_if_not_exists returns a fresh cycle (count=0)
    fresh_cycle = _mock_cycle(cycle_id="PC-NEW-001", reminder_count=0)
    svc.cycle_svc.create_cycle_if_not_exists.return_value = fresh_cycle

    # increment_reminder advances count to 1
    advanced_cycle = _mock_cycle(cycle_id="PC-NEW-001", reminder_count=1)
    svc.cycle_svc.increment_reminder.return_value = advanced_cycle

    svc.incident_service.get_incident.return_value = _mock_incident(state="on_hold")

    note1 = MagicMock()
    note1.message = "State changed to: on_hold"
    note1.source_name = "Aman"
    note1.source_type = "ENGINEER"
    note1.action_type = WorkNoteActionType.STATE_CHANGE

    note2 = MagicMock()
    note2.message = "Could you provide more details?"
    note2.source_name = "Aman"
    note2.source_type = "ENGINEER"
    note2.action_type = WorkNoteActionType.MANUAL_NOTE

    svc.work_note_svc.get_notes.return_value = [note1, note2]
    svc.work_note_svc.add_note.return_value = MagicMock()
    svc.incident_service.update_incident_internal = AsyncMock()

    from app.modules.agents.pending.schemas import PendingWorkNoteAnalysis
    svc.analyzer.analyze.return_value = PendingWorkNoteAnalysis(
        is_caller_action_required=True,
        reasoning="Awaiting caller confirmation.",
        confidence=1.0,
    )

    resp = await svc.process_pending_transition(incident_id="inc-123", force_reminder=False)

    # With the new behavior, force_reminder=False + no active cycle → SCHEDULES Reminder 1,
    # does NOT send it immediately.
    assert resp.success is True
    assert resp.result["action_taken"] == "REMINDER_SCHEDULED"
    assert resp.result["cycle_id"] == "PC-NEW-001"
    assert resp.result["reminder_count"] == 1
    assert resp.result["email_sent"] is False  # not sent yet — scheduled

    # create_cycle_if_not_exists called with incident id
    svc.cycle_svc.create_cycle_if_not_exists.assert_called_once_with(
        incident_id="inc-123",
        max_reminders=3,
    )
    # increment_reminder called once (to schedule Reminder 1 with next_reminder_at)
    svc.cycle_svc.increment_reminder.assert_called_once()
    call_args = svc.cycle_svc.increment_reminder.call_args
    assert call_args.args[0] == "PC-NEW-001"
    assert call_args.kwargs.get("next_reminder_at") is not None  # scheduled time set

    # Work note NOT added during scheduling — it fires when the scheduler executes
    svc.work_note_svc.add_note.assert_not_called()


# ------ Test: force_reminder=True advances existing cycle ------

@pytest.mark.asyncio
async def test_pending_service_force_reminder_increments_existing_cycle():
    """
    When force_reminder=True and an active cycle exists, the service
    increments the reminder count and sends the next reminder.
    """
    svc = _make_service()

    existing_cycle = _mock_cycle(cycle_id="PC-EX-001", reminder_count=1)
    svc.cycle_svc.get_active_cycle.return_value = existing_cycle

    # After increment: count becomes 2
    advanced_cycle = _mock_cycle(cycle_id="PC-EX-001", reminder_count=2)
    svc.cycle_svc.increment_reminder.return_value = advanced_cycle

    svc.incident_service.get_incident.return_value = _mock_incident(state="on_hold")
    svc.work_note_svc.get_notes.return_value = []
    svc.work_note_svc.add_note.return_value = MagicMock()

    from app.modules.agents.pending.schemas import PendingWorkNoteAnalysis
    svc.analyzer.analyze.return_value = PendingWorkNoteAnalysis(
        is_caller_action_required=True,
        reasoning="Still awaiting.",
        confidence=1.0,
    )

    resp = await svc.process_pending_transition(incident_id="inc-123", force_reminder=True)

    assert resp.success is True
    # reminder_count in result = the reminder tier that was SENT (existing_cycle.reminder_count=1)
    assert resp.result["reminder_count"] == 1
    assert resp.result["email_sent"] is True

    # Existing cycle was advanced (increment_reminder called), not recreated
    svc.cycle_svc.create_cycle_if_not_exists.assert_not_called()
    svc.cycle_svc.increment_reminder.assert_called_once()
    # Verify it was called with the correct cycle id and a next_reminder_at kwarg
    call = svc.cycle_svc.increment_reminder.call_args
    assert call.args[0] == "PC-EX-001"
    assert call.kwargs.get("next_reminder_at") is not None  # schedules Reminder 2


# ------ Test: no duplicate cycle creation ------

@pytest.mark.asyncio
async def test_pending_service_does_not_create_duplicate_cycle():
    """
    create_cycle_if_not_exists is called exactly once.
    The service trusts PendingCycleService for idempotency — no extra
    duplicate-cycle check inside PendingService.
    """
    svc = _make_service()
    svc.cycle_svc.get_active_cycle.return_value = None

    cycle = _mock_cycle(cycle_id="PC-IDEM-001", reminder_count=0)
    svc.cycle_svc.create_cycle_if_not_exists.return_value = cycle

    incremented = _mock_cycle(cycle_id="PC-IDEM-001", reminder_count=1)
    svc.cycle_svc.increment_reminder.return_value = incremented

    svc.incident_service.get_incident.return_value = _mock_incident(state="on_hold")
    svc.work_note_svc.get_notes.return_value = []
    svc.work_note_svc.add_note.return_value = MagicMock()

    from app.modules.agents.pending.schemas import PendingWorkNoteAnalysis
    svc.analyzer.analyze.return_value = PendingWorkNoteAnalysis(
        is_caller_action_required=True,
        reasoning="Waiting.",
        confidence=1.0,
    )

    await svc.process_pending_transition(incident_id="inc-123", force_reminder=False)

    # Called exactly once — no duplicate creation logic
    assert svc.cycle_svc.create_cycle_if_not_exists.call_count == 1


# ------ Test: work note uses WorkNoteService ------

@pytest.mark.asyncio
async def test_pending_service_work_note_uses_work_note_service():
    """
    When a scheduled reminder executes (force_reminder=True), the work note
    goes through WorkNoteService.add_note() — not directly via a repository.
    """
    svc = _make_service()

    # force_reminder=True path: active cycle exists with count=1 (Reminder 1 due)
    existing_cycle = _mock_cycle(cycle_id="PC-WN-001", reminder_count=1)
    svc.cycle_svc.get_active_cycle.return_value = existing_cycle

    # After increment: schedule Reminder 2
    incremented = _mock_cycle(cycle_id="PC-WN-001", reminder_count=2)
    svc.cycle_svc.increment_reminder.return_value = incremented

    svc.incident_service.get_incident.return_value = _mock_incident(state="on_hold")
    svc.work_note_svc.get_notes.return_value = []

    mock_note = MagicMock()
    mock_note.id = "wn-reminder-001"
    svc.work_note_svc.add_note.return_value = mock_note
    svc.incident_service.update_incident_internal = AsyncMock()

    from app.modules.agents.pending.schemas import PendingWorkNoteAnalysis
    svc.analyzer.analyze.return_value = PendingWorkNoteAnalysis(
        is_caller_action_required=True,
        reasoning="Still waiting.",
        confidence=1.0,
    )

    await svc.process_pending_transition(incident_id="inc-123", force_reminder=True)

    # add_note was called via WorkNoteService (not bypassed)
    svc.work_note_svc.add_note.assert_called_once()
    kwargs = svc.work_note_svc.add_note.call_args.kwargs
    assert kwargs["incident_id"] == "inc-123"
    assert kwargs["source_type"] == WorkNoteSourceType.PENDING_AGENT
    assert kwargs["action_type"] == WorkNoteActionType.SEND_REMINDER


# ------ Test: two-note analysis (regression from original tests) ------

@pytest.mark.asyncio
async def test_pending_service_two_notes_analysis():
    """
    Regression: when the latest notes are fetched, the reminder work note
    is generated with the correct message prefix.
    """
    svc = _make_service()
    svc.cycle_svc.get_active_cycle.return_value = None

    cycle = _mock_cycle(cycle_id="PC-TWO-002", reminder_count=0)
    svc.cycle_svc.create_cycle_if_not_exists.return_value = cycle

    advanced = _mock_cycle(cycle_id="PC-TWO-002", reminder_count=1)
    svc.cycle_svc.increment_reminder.return_value = advanced

    svc.incident_service.get_incident.return_value = _mock_incident(
        inc_id="inc-456",
        number="INC0000100",
        state="on_hold",
        caller="Tina",
        assigned_to="Aman Mourya",
        group="Apps Run-SFDC",
        short_description="Cannot open GTS",
    )

    note1 = MagicMock()
    note1.message = "State changed to: on_hold"
    note1.source_name = "Aman Mourya"
    note1.source_type = "ENGINEER"
    note1.action_type = WorkNoteActionType.STATE_CHANGE

    note2 = MagicMock()
    note2.message = "Could you please provide the screenshot of the error message when opening GTS EANZ?"
    note2.source_name = "Aman Mourya"
    note2.source_type = "ENGINEER"
    note2.action_type = WorkNoteActionType.MANUAL_NOTE

    svc.work_note_svc.get_notes.return_value = [note1, note2]
    svc.work_note_svc.add_note.return_value = MagicMock()
    svc.incident_service.update_incident_internal = AsyncMock()

    from app.modules.agents.pending.schemas import PendingWorkNoteAnalysis
    svc.analyzer.analyze.return_value = PendingWorkNoteAnalysis(
        is_caller_action_required=True,
        reasoning="Awaiting screenshot.",
        confidence=1.0,
    )

    resp = await svc.process_pending_transition(incident_id="inc-456")

    # force_reminder=False + no active cycle → schedules Reminder 1, does NOT send yet
    assert resp.success is True
    assert resp.result["action_taken"] == "REMINDER_SCHEDULED"
    assert resp.result["email_sent"] is False
    assert resp.result["reminder_count"] == 1


# ------ Test: no duplicate PendingCycleRepository in service ------

def test_pending_service_uses_cycle_svc_not_cycle_repo():
    """
    PendingService must use self.cycle_svc (PendingCycleService),
    not self.cycle_repo (the old duplicate repository).
    """
    db = AsyncMock()
    svc = PendingService(db)

    assert hasattr(svc, "cycle_svc"), "PendingService must have cycle_svc attribute"
    assert not hasattr(svc, "cycle_repo"), (
        "PendingService must NOT have cycle_repo — "
        "the duplicate PendingCycleRepository has been removed"
    )

    from app.modules.pending_cycles.service import PendingCycleService
    assert isinstance(svc.cycle_svc, PendingCycleService)


# ===========================================================================
# Max-reminders enforcement tests (new requirement)
# ===========================================================================

def _make_service_for_reminder_exec() -> PendingService:
    """PendingService wired for executing a reminder (force_reminder=True path)."""
    from app.modules.agents.pending.schemas import PendingWorkNoteAnalysis
    svc = _make_service()
    svc.work_note_svc.get_notes.return_value = []
    svc.work_note_svc.add_note.return_value = MagicMock()
    svc.incident_service.update_incident_internal = AsyncMock()
    svc.analyzer.analyze.return_value = PendingWorkNoteAnalysis(
        is_caller_action_required=True,
        reasoning="Awaiting response.",
        confidence=1.0,
    )
    return svc


@pytest.mark.asyncio
async def test_max_reminders_sends_exactly_3():
    """
    Reminders 1, 2, 3 each execute and send a work note.
    No 4th reminder is sent.
    """
    svc = _make_service_for_reminder_exec()
    inc = _mock_incident(state="on_hold")
    svc.incident_service.get_incident.return_value = inc

    send_count = 0

    for reminder_num in range(1, 4):
        cycle = _mock_cycle(cycle_id="PC-MAX-001", reminder_count=reminder_num, max_reminders=3)
        svc.cycle_svc.get_active_cycle.return_value = cycle
        svc.cycle_svc.increment_reminder.reset_mock()
        svc.cycle_svc.complete_cycle.reset_mock()

        if reminder_num < 3:
            # Non-final: increment_reminder schedules the next
            next_cycle = _mock_cycle(cycle_id="PC-MAX-001", reminder_count=reminder_num + 1)
            svc.cycle_svc.increment_reminder.return_value = next_cycle
        else:
            # Final (Reminder 3): complete_cycle called
            completed = MagicMock(id="PC-MAX-001", reminder_count=3, max_reminders=3, next_reminder_at=None)
            svc.cycle_svc.complete_cycle.return_value = completed

        resp = await svc.process_pending_transition(incident_id="inc-123", force_reminder=True)
        assert resp.result["email_sent"] is True, f"Reminder {reminder_num} must be sent"
        send_count += 1

    assert send_count == 3

    # Simulate a 4th stale call — cycle is now gone (completed/cancelled)
    svc.cycle_svc.get_active_cycle.return_value = None
    resp4 = await svc.process_pending_transition(incident_id="inc-123", force_reminder=True)
    assert resp4.result["email_sent"] is False
    assert resp4.result["action_taken"] == "DISCARDED"


@pytest.mark.asyncio
async def test_reminder_4_never_sent():
    """
    After max_reminders have been sent (reminder_count > max_reminders due to a
    stale or duplicate scheduler call), no further reminder is sent.
    """
    svc = _make_service_for_reminder_exec()
    inc = _mock_incident(state="on_hold")
    svc.incident_service.get_incident.return_value = inc

    # Cycle where count already exceeds max (e.g. a race/duplicate trigger)
    exhausted_cycle = _mock_cycle(cycle_id="PC-EX-001", reminder_count=4, max_reminders=3)
    svc.cycle_svc.get_active_cycle.return_value = exhausted_cycle
    svc.cycle_svc.complete_cycle.return_value = MagicMock(id="PC-EX-001")

    resp = await svc.process_pending_transition(incident_id="inc-123", force_reminder=True)

    # Nothing sent
    assert resp.result["email_sent"] is False
    assert resp.result["action_taken"] == "DISCARDED"
    svc.work_note_svc.add_note.assert_not_called()
    # complete_cycle called to finalise the exhausted cycle
    svc.cycle_svc.complete_cycle.assert_called_once_with("PC-EX-001")


@pytest.mark.asyncio
async def test_cycle_completed_after_reminder_3():
    """
    After executing Reminder 3 (the final reminder), the cycle must be COMPLETED
    not merely ACTIVE with next_reminder_at=None.
    """
    svc = _make_service_for_reminder_exec()
    inc = _mock_incident(state="on_hold")
    svc.incident_service.get_incident.return_value = inc

    final_cycle = _mock_cycle(cycle_id="PC-FIN-001", reminder_count=3, max_reminders=3)
    svc.cycle_svc.get_active_cycle.return_value = final_cycle
    completed_response = MagicMock(id="PC-FIN-001", reminder_count=3, max_reminders=3, next_reminder_at=None)
    svc.cycle_svc.complete_cycle.return_value = completed_response

    resp = await svc.process_pending_transition(incident_id="inc-123", force_reminder=True)

    assert resp.result["action_taken"] == "CYCLE_COMPLETED"
    # complete_cycle (not increment_reminder) must be called for the final reminder
    svc.cycle_svc.complete_cycle.assert_called_once_with("PC-FIN-001")
    svc.cycle_svc.increment_reminder.assert_not_called()


@pytest.mark.asyncio
async def test_no_next_reminder_scheduled_after_reminder_3():
    """
    After Reminder 3, next_reminder_at is None — the scheduler will not
    pick up a 4th reminder.
    """
    svc = _make_service_for_reminder_exec()
    inc = _mock_incident(state="on_hold")
    svc.incident_service.get_incident.return_value = inc

    final_cycle = _mock_cycle(cycle_id="PC-FIN-002", reminder_count=3, max_reminders=3)
    svc.cycle_svc.get_active_cycle.return_value = final_cycle
    completed_response = MagicMock(id="PC-FIN-002", reminder_count=3, max_reminders=3, next_reminder_at=None)
    svc.cycle_svc.complete_cycle.return_value = completed_response

    resp = await svc.process_pending_transition(incident_id="inc-123", force_reminder=True)

    # next_reminder_at must be None so the scheduler never fires again
    assert resp.result["next_reminder_at"] is None


@pytest.mark.asyncio
async def test_stale_scheduler_call_after_completion_does_nothing():
    """
    If a stale/duplicate scheduler job fires after the cycle is already completed
    (get_active_cycle returns None), the execution must be silently discarded.
    No reminder sent, no work note, no exception.
    """
    svc = _make_service_for_reminder_exec()
    inc = _mock_incident(state="on_hold")
    svc.incident_service.get_incident.return_value = inc

    # No active cycle — already completed or cancelled
    svc.cycle_svc.get_active_cycle.return_value = None

    resp = await svc.process_pending_transition(incident_id="inc-123", force_reminder=True)

    assert resp.success is True
    assert resp.result["action_taken"] == "DISCARDED"
    assert resp.result["email_sent"] is False
    svc.work_note_svc.add_note.assert_not_called()
    svc.cycle_svc.increment_reminder.assert_not_called()
    svc.cycle_svc.complete_cycle.assert_not_called()


@pytest.mark.asyncio
async def test_existing_active_cycle_reused_reminder_count_preserved():
    """
    When force_reminder=False and an active cycle already exists,
    the service preserves the cycle without resetting reminder_count.
    """
    svc = _make_service()
    inc = _mock_incident(state="on_hold")
    svc.incident_service.get_incident.return_value = inc

    # Cycle already at reminder 2 — must be preserved as-is
    existing = _mock_cycle(cycle_id="PC-REUSE-001", reminder_count=2, max_reminders=3)
    svc.cycle_svc.get_active_cycle.return_value = existing

    resp = await svc.process_pending_transition(incident_id="inc-123", force_reminder=False)

    assert resp.result["action_taken"] == "CYCLE_PRESERVED"
    assert resp.result["reminder_count"] == 2  # count preserved, not reset
    assert resp.result["email_sent"] is False

    svc.cycle_svc.create_cycle_if_not_exists.assert_not_called()
    svc.cycle_svc.increment_reminder.assert_not_called()
    svc.work_note_svc.add_note.assert_not_called()
