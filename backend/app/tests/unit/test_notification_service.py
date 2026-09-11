"""
Unit tests for the Notification integration layer.

Tests 1–14 are pure unit tests: providers and WorkNoteService are mocked
so no database is touched.

Coverage map
~~~~~~~~~~~~
1.  Email simulation succeeds (SimulatorNotificationProvider).
2.  Teams simulation succeeds (SimulatorNotificationProvider).
3.  Email returns delivery_status="simulated_success".
4.  Teams returns delivery_status="simulated_success".
5.  Each call generates a unique simulated message ID.
6.  NotificationService.send(EMAIL) creates a work note.
7.  NotificationService.send(TEAMS) creates a work note.
8.  Work note message contains the exact email subject and body.
9.  Work note message contains the exact Teams message body.
10. Work note message contains the recipient/audience.
11. Work note message contains the source agent name.
12. Provider failure returns a failed NotificationResult (success=False).
13. Work-note failure is NOT reported as a successful notification.
14. NotificationService does not directly access the database
    (only WorkNoteService.add_note is ever called, never db directly).
15. Unknown channel is handled gracefully (failure result, no exception).
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.integrations.notifications.schemas import (
    NotificationChannel,
    NotificationRequest,
    NotificationResult,
)
from app.integrations.notifications.simulator import SimulatorNotificationProvider
from app.integrations.notifications.service import NotificationService
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _email_request(
    incident_id: str = "inc-001",
    recipients: list[str] | None = None,
    subject: str = "Test subject",
    message: str = "Test email body",
    source_name: str = "TestAgent",
    source_type: str = WorkNoteSourceType.PENDING_AGENT.value,
    action_type: str = WorkNoteActionType.SEND_REMINDER.value,
) -> NotificationRequest:
    return NotificationRequest(
        incident_id=incident_id,
        channel=NotificationChannel.EMAIL,
        recipients=recipients or ["engineer@example.com"],
        subject=subject,
        message=message,
        source_name=source_name,
        source_type=source_type,
        action_type=action_type,
    )


def _teams_request(
    incident_id: str = "inc-001",
    recipients: list[str] | None = None,
    message: str = "Test Teams message",
    source_name: str = "TestAgent",
    source_type: str = WorkNoteSourceType.PENDING_AGENT.value,
    action_type: str = WorkNoteActionType.SEND_REMINDER.value,
) -> NotificationRequest:
    return NotificationRequest(
        incident_id=incident_id,
        channel=NotificationChannel.TEAMS,
        recipients=recipients or ["#incident-channel"],
        message=message,
        source_name=source_name,
        source_type=source_type,
        action_type=action_type,
    )


def _make_work_note_response(note_id: str = "wn-001") -> MagicMock:
    """Return a mock that looks like a WorkNoteResponse."""
    m = MagicMock()
    m.id = note_id
    m.message = ""
    return m


def _make_notification_service(work_note_response: MagicMock | None = None) -> tuple[NotificationService, MagicMock]:
    """
    Build a NotificationService wired to a SimulatorProvider and a mocked
    WorkNoteService.  Returns (service, mock_work_note_svc).
    """
    db = AsyncMock()
    svc = NotificationService(db)

    mock_wn = AsyncMock()
    mock_wn.add_note.return_value = work_note_response or _make_work_note_response()
    svc._work_note_svc = mock_wn

    return svc, mock_wn


# ---------------------------------------------------------------------------
# Tests 1–5: SimulatorNotificationProvider in isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_1_email_simulation_succeeds():
    """Simulator returns success=True for EMAIL."""
    provider = SimulatorNotificationProvider()
    result = await provider.send(_email_request())
    assert result.success is True


@pytest.mark.asyncio
async def test_2_teams_simulation_succeeds():
    """Simulator returns success=True for TEAMS."""
    provider = SimulatorNotificationProvider()
    result = await provider.send(_teams_request())
    assert result.success is True


@pytest.mark.asyncio
async def test_3_email_delivery_status_is_simulated_success():
    """Email delivery_status must equal 'simulated_success'."""
    provider = SimulatorNotificationProvider()
    result = await provider.send(_email_request())
    assert result.delivery_status == "simulated_success"


@pytest.mark.asyncio
async def test_4_teams_delivery_status_is_simulated_success():
    """Teams delivery_status must equal 'simulated_success'."""
    provider = SimulatorNotificationProvider()
    result = await provider.send(_teams_request())
    assert result.delivery_status == "simulated_success"


@pytest.mark.asyncio
async def test_5_unique_message_ids_generated():
    """Every send call produces a different message_id (no duplicates)."""
    provider = SimulatorNotificationProvider()
    results = [await provider.send(_email_request()) for _ in range(5)]
    ids = [r.message_id for r in results]
    # All IDs must be distinct
    assert len(set(ids)) == 5
    # All must start with the expected prefix
    for msg_id in ids:
        assert msg_id.startswith("SIM-EMAIL-")


# ---------------------------------------------------------------------------
# Tests 6–11: NotificationService work-note integration (mocked DB)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_6_email_send_creates_work_note():
    """NotificationService.send(EMAIL) must call WorkNoteService.add_note once."""
    svc, mock_wn = _make_notification_service()
    await svc.send(_email_request())
    mock_wn.add_note.assert_called_once()


@pytest.mark.asyncio
async def test_7_teams_send_creates_work_note():
    """NotificationService.send(TEAMS) must call WorkNoteService.add_note once."""
    svc, mock_wn = _make_notification_service()
    await svc.send(_teams_request())
    mock_wn.add_note.assert_called_once()


@pytest.mark.asyncio
async def test_8_work_note_contains_exact_email_subject_and_body():
    """The work note message must contain the exact subject and body sent."""
    svc, mock_wn = _make_notification_service()
    subject = "Customer confirmation requested"
    body = "Please confirm that your issue is resolved."

    await svc.send(_email_request(subject=subject, message=body))

    call_kwargs = mock_wn.add_note.call_args.kwargs
    note_message = call_kwargs["message"]
    assert subject in note_message
    assert body in note_message


@pytest.mark.asyncio
async def test_9_work_note_contains_exact_teams_message():
    """The work note message must contain the exact Teams body sent."""
    svc, mock_wn = _make_notification_service()
    teams_msg = "🔔 INC0001234 is pending your response."

    await svc.send(_teams_request(message=teams_msg))

    call_kwargs = mock_wn.add_note.call_args.kwargs
    note_message = call_kwargs["message"]
    assert teams_msg in note_message


@pytest.mark.asyncio
async def test_10_work_note_contains_recipient():
    """The work note message must include the recipient address."""
    svc, mock_wn = _make_notification_service()
    recipient = "priya.sharma@example.com"

    await svc.send(_email_request(recipients=[recipient]))

    call_kwargs = mock_wn.add_note.call_args.kwargs
    note_message = call_kwargs["message"]
    assert recipient in note_message


@pytest.mark.asyncio
async def test_11_work_note_contains_source_agent_name():
    """The work note message must include the source agent name."""
    svc, mock_wn = _make_notification_service()
    agent_name = "PendingReminderAgent"

    await svc.send(_email_request(source_name=agent_name))

    call_kwargs = mock_wn.add_note.call_args.kwargs
    # source_name is passed directly as the source_name kwarg to add_note
    assert call_kwargs["source_name"] == agent_name
    # …and it also appears in the note body
    note_message = call_kwargs["message"]
    assert agent_name in note_message


# ---------------------------------------------------------------------------
# Tests 12–13: Failure path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_12_provider_failure_returns_failed_result():
    """If the provider returns failure, NotificationService must return success=False."""
    db = AsyncMock()
    svc = NotificationService(db)

    # Replace provider with one that always fails
    failing_provider = AsyncMock()
    failing_provider.send.return_value = NotificationResult.failure(
        channel=NotificationChannel.EMAIL,
        error="Simulated provider error",
        recipient="test@example.com",
        message="body",
    )
    svc._provider = failing_provider

    mock_wn = AsyncMock()
    svc._work_note_svc = mock_wn

    result = await svc.send(_email_request())

    assert result.success is False
    assert "Simulated provider error" in (result.error or "")
    # Work note must NOT be written when delivery itself fails
    mock_wn.add_note.assert_not_called()


@pytest.mark.asyncio
async def test_13_work_note_failure_not_reported_as_success():
    """If delivery succeeds but work-note recording raises, result must be success=False."""
    db = AsyncMock()
    svc = NotificationService(db)

    # Provider succeeds
    svc._provider = SimulatorNotificationProvider()

    # Work note service raises
    mock_wn = AsyncMock()
    mock_wn.add_note.side_effect = RuntimeError("DB connection lost")
    svc._work_note_svc = mock_wn

    result = await svc.send(_email_request())

    assert result.success is False
    assert result.work_note_id is None
    assert "Work note recording failed" in (result.error or "")


# ---------------------------------------------------------------------------
# Test 14: NotificationService does not directly access the database
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_14_notification_service_does_not_directly_access_db():
    """
    NotificationService must only go through WorkNoteService — it must not
    call db.execute, db.add, db.commit, db.query, etc. directly.
    """
    db = AsyncMock()
    svc = NotificationService(db)

    mock_wn = AsyncMock()
    mock_wn.add_note.return_value = _make_work_note_response()
    svc._work_note_svc = mock_wn

    await svc.send(_email_request())

    # The db mock must never have been awaited directly
    db.execute.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Test 15: Unknown channel handled gracefully
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_15_unknown_channel_returns_failure_not_exception():
    """Simulator must return a failure result for an unrecognised channel — never raise."""
    provider = SimulatorNotificationProvider()

    # Construct a request with a bad channel by bypassing the enum
    request = NotificationRequest(
        incident_id="inc-001",
        channel=NotificationChannel.EMAIL,   # valid for construction
        recipients=["a@b.com"],
        message="hello",
        source_name="Agent",
        source_type=WorkNoteSourceType.SYSTEM.value,
    )
    # Patch channel value after construction to inject an unknown string
    object.__setattr__(request, "channel", "smoke_signal")

    result = await provider.send(request)

    assert result.success is False
    assert "smoke_signal" in (result.error or "")
