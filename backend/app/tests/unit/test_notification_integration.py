"""
Integration tests for the Notification layer against a real SQLite session.

Uses the same db_session / engine fixtures from conftest.py so we exercise
the full stack:

    NotificationService.send()
        → SimulatorNotificationProvider.send()     (no real I/O)
        → WorkNoteService.add_note()               (real DB write)
        → IncidentWorkNote row in SQLite in-memory

These tests verify:
    A. A work note row is created with the correct incident_id.
    B. The work note carries the correct source_type and action_type.
    C. The work note message contains the exact notification body.
    D. The work note message contains the recipient.
    E. Email work notes contain the subject.
    F. Teams work notes do NOT contain a subject line header.
    G. Multiple notifications to the same incident create separate rows.
    H. The returned NotificationResult.work_note_id matches the persisted row.
"""
from __future__ import annotations

import uuid
import pytest
from sqlalchemy import select

from app.integrations.notifications.schemas import (
    NotificationChannel,
    NotificationRequest,
)
from app.integrations.notifications.service import NotificationService
from app.modules.incidents.model import Incident
from app.modules.incidents.enums import IncidentPriority, IncidentState
from app.modules.work_notes.model import IncidentWorkNote
from app.modules.work_notes.repository import WorkNoteRepository
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_test_incident(db) -> Incident:
    """Insert a minimal Incident row into the test DB and return it."""
    inc = Incident(
        id=str(uuid.uuid4()),
        incident_number=f"INC{uuid.uuid4().hex[:7].upper()}",
        short_description="Notification integration test",
        priority=IncidentPriority.MEDIUM,
        state=IncidentState.PENDING,
    )
    db.add(inc)
    await db.commit()
    await db.refresh(inc)
    return inc


async def _note_by_id(db, note_id: str) -> IncidentWorkNote | None:
    """Fetch a single IncidentWorkNote by primary key."""
    result = await db.execute(
        select(IncidentWorkNote).where(IncidentWorkNote.id == note_id)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_integration_email_work_note_row_exists(db_session):
    """
    After sending an EMAIL notification, exactly one work note row must
    exist in the database for the incident.
    """
    inc = await _create_test_incident(db_session)
    svc = NotificationService(db_session)

    result = await svc.send(NotificationRequest(
        incident_id=inc.id,
        channel=NotificationChannel.EMAIL,
        recipients=["caller@example.com"],
        subject="Your ticket is pending",
        message="Please confirm the issue is resolved.",
        source_name="PendingReminderAgent",
        source_type=WorkNoteSourceType.PENDING_AGENT.value,
        action_type=WorkNoteActionType.SEND_REMINDER.value,
    ))

    assert result.success is True
    assert result.work_note_id is not None

    repo = WorkNoteRepository(db_session)
    notes = await repo.get_by_incident(inc.id)
    assert len(notes) == 1
    assert notes[0].id == result.work_note_id


@pytest.mark.anyio
async def test_integration_correct_incident_id_on_work_note(db_session):
    """Work note incident_id must match the incident passed in the request."""
    inc = await _create_test_incident(db_session)
    svc = NotificationService(db_session)

    result = await svc.send(NotificationRequest(
        incident_id=inc.id,
        channel=NotificationChannel.EMAIL,
        recipients=["a@b.com"],
        subject="Check",
        message="Body text.",
        source_name="TestAgent",
        source_type=WorkNoteSourceType.SYSTEM.value,
        action_type=WorkNoteActionType.SEND_REMINDER.value,
    ))

    note = await _note_by_id(db_session, result.work_note_id)
    assert note is not None
    assert note.incident_id == inc.id


@pytest.mark.anyio
async def test_integration_correct_source_and_action_type(db_session):
    """Work note must carry source_type=PENDING_AGENT and action_type=SEND_REMINDER."""
    inc = await _create_test_incident(db_session)
    svc = NotificationService(db_session)

    result = await svc.send(NotificationRequest(
        incident_id=inc.id,
        channel=NotificationChannel.EMAIL,
        recipients=["eng@example.com"],
        subject="Reminder",
        message="This is the reminder body.",
        source_name="PendingReminderAgent",
        source_type=WorkNoteSourceType.PENDING_AGENT.value,
        action_type=WorkNoteActionType.SEND_REMINDER.value,
    ))

    note = await _note_by_id(db_session, result.work_note_id)
    assert note is not None
    assert note.source_type == WorkNoteSourceType.PENDING_AGENT.value
    assert note.action_type == WorkNoteActionType.SEND_REMINDER.value
    assert note.source_name == "PendingReminderAgent"


@pytest.mark.anyio
async def test_integration_work_note_contains_exact_email_message(db_session):
    """The persisted work note message must contain the exact email body sent."""
    inc = await _create_test_incident(db_session)
    svc = NotificationService(db_session)

    body = "Hi Jane, your ticket INC0001234 is awaiting confirmation."
    result = await svc.send(NotificationRequest(
        incident_id=inc.id,
        channel=NotificationChannel.EMAIL,
        recipients=["jane@example.com"],
        subject="Action required",
        message=body,
        source_name="PendingReminderAgent",
        source_type=WorkNoteSourceType.PENDING_AGENT.value,
        action_type=WorkNoteActionType.SEND_REMINDER.value,
    ))

    note = await _note_by_id(db_session, result.work_note_id)
    assert note is not None
    assert body in note.message


@pytest.mark.anyio
async def test_integration_work_note_contains_recipient(db_session):
    """The persisted work note must include the recipient address."""
    inc = await _create_test_incident(db_session)
    svc = NotificationService(db_session)

    recipient = "priya.sharma@example.com"
    result = await svc.send(NotificationRequest(
        incident_id=inc.id,
        channel=NotificationChannel.EMAIL,
        recipients=[recipient],
        subject="Sub",
        message="Body",
        source_name="Agent",
        source_type=WorkNoteSourceType.PENDING_AGENT.value,
        action_type=WorkNoteActionType.SEND_REMINDER.value,
    ))

    note = await _note_by_id(db_session, result.work_note_id)
    assert note is not None
    assert recipient in note.message


@pytest.mark.anyio
async def test_integration_email_work_note_contains_subject(db_session):
    """For EMAIL, the persisted work note must include the subject line."""
    inc = await _create_test_incident(db_session)
    svc = NotificationService(db_session)

    subject = "Please confirm resolution of INC0001234"
    result = await svc.send(NotificationRequest(
        incident_id=inc.id,
        channel=NotificationChannel.EMAIL,
        recipients=["user@example.com"],
        subject=subject,
        message="Confirmation body.",
        source_name="Agent",
        source_type=WorkNoteSourceType.PENDING_AGENT.value,
        action_type=WorkNoteActionType.SEND_REMINDER.value,
    ))

    note = await _note_by_id(db_session, result.work_note_id)
    assert note is not None
    assert subject in note.message


@pytest.mark.anyio
async def test_integration_teams_work_note_contains_message(db_session):
    """Teams work note must contain the exact Teams message body."""
    inc = await _create_test_incident(db_session)
    svc = NotificationService(db_session)

    teams_body = "🔔 Ticket INC0001234 is still pending — please respond."
    result = await svc.send(NotificationRequest(
        incident_id=inc.id,
        channel=NotificationChannel.TEAMS,
        recipients=["#incident-ops"],
        message=teams_body,
        source_name="PendingReminderAgent",
        source_type=WorkNoteSourceType.PENDING_AGENT.value,
        action_type=WorkNoteActionType.SEND_REMINDER.value,
    ))

    assert result.success is True
    note = await _note_by_id(db_session, result.work_note_id)
    assert note is not None
    assert teams_body in note.message


@pytest.mark.anyio
async def test_integration_teams_work_note_no_subject_header(db_session):
    """Teams work note must NOT contain a 'Subject :' line (Teams has no subject)."""
    inc = await _create_test_incident(db_session)
    svc = NotificationService(db_session)

    result = await svc.send(NotificationRequest(
        incident_id=inc.id,
        channel=NotificationChannel.TEAMS,
        recipients=["#ops"],
        message="Teams alert body.",
        source_name="Agent",
        source_type=WorkNoteSourceType.PENDING_AGENT.value,
        action_type=WorkNoteActionType.SEND_REMINDER.value,
    ))

    note = await _note_by_id(db_session, result.work_note_id)
    assert note is not None
    # The structured note format only adds "Subject    :" for email
    assert "Subject    :" not in note.message


@pytest.mark.anyio
async def test_integration_multiple_notifications_create_separate_rows(db_session):
    """Two notifications to the same incident produce two distinct work note rows."""
    inc = await _create_test_incident(db_session)
    svc = NotificationService(db_session)

    base = dict(
        incident_id=inc.id,
        channel=NotificationChannel.EMAIL,
        recipients=["a@b.com"],
        subject="Reminder",
        source_name="Agent",
        source_type=WorkNoteSourceType.PENDING_AGENT.value,
        action_type=WorkNoteActionType.SEND_REMINDER.value,
    )

    r1 = await svc.send(NotificationRequest(**{**base, "message": "First reminder."}))
    r2 = await svc.send(NotificationRequest(**{**base, "message": "Second reminder."}))

    assert r1.success is True
    assert r2.success is True
    assert r1.work_note_id != r2.work_note_id

    repo = WorkNoteRepository(db_session)
    notes = await repo.get_by_incident(inc.id)
    assert len(notes) == 2


@pytest.mark.anyio
async def test_integration_result_work_note_id_matches_db_row(db_session):
    """NotificationResult.work_note_id must equal the id of the DB-persisted row."""
    inc = await _create_test_incident(db_session)
    svc = NotificationService(db_session)

    result = await svc.send(NotificationRequest(
        incident_id=inc.id,
        channel=NotificationChannel.EMAIL,
        recipients=["x@y.com"],
        subject="Tracing test",
        message="Trace me.",
        source_name="AuditAgent",
        source_type=WorkNoteSourceType.SYSTEM.value,
        action_type=WorkNoteActionType.SEND_ACKNOWLEDGEMENT.value,
    ))

    assert result.success is True
    note = await _note_by_id(db_session, result.work_note_id)
    assert note is not None
    assert note.id == result.work_note_id
