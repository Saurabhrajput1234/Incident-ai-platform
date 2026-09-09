"""
Unit tests for Pending Agent components:
- PendingReminderRenderer
- PendingWorkNoteAnalyzer
- PendingCycleRepository
- PendingService
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.modules.agents.pending.models.pending_cycle import PendingCycle, PendingCycleStatus
from app.modules.agents.pending.reminder_renderer import PendingReminderRenderer
from app.modules.agents.pending.work_note_analyzer import PendingWorkNoteAnalyzer
from app.modules.agents.pending.service import PendingService


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


@pytest.mark.asyncio
async def test_analyzer_fast_path_acknowledgement_agent():
    analyzer = PendingWorkNoteAnalyzer()
    res = await analyzer.analyze(
        latest_work_note="Acknowledgement Agent executed successfully.\nUser notified to submit RITM.",
        source_name="AcknowledgementAgent",
    )
    assert res.is_caller_action_required is True
    assert res.confidence == 1.0


@pytest.mark.asyncio
async def test_pending_service_preserves_active_cycle():
    db = AsyncMock()
    service = PendingService(db)

    # Mock active cycle exists
    mock_cycle = MagicMock()
    mock_cycle.id = "PC-TEST-001"
    mock_cycle.status = PendingCycleStatus.ACTIVE
    mock_cycle.reminder_count = 1
    mock_cycle.max_reminders = 3
    mock_cycle.next_reminder_at = None

    service.cycle_repo.get_active_cycle = AsyncMock(return_value=mock_cycle)

    mock_incident = MagicMock()
    mock_incident.id = "inc-123"
    mock_incident.incident_number = "INC0000099"
    mock_incident.caller = "Alice"
    mock_incident.assigned_to = "Bob"
    mock_incident.assignment_group = "Support"
    mock_incident.state = "pending"
    service.incident_service.get_incident = AsyncMock(return_value=mock_incident)

    resp = await service.process_pending_transition(incident_id="inc-123", force_reminder=False)
    assert resp.success is True
    assert resp.result["action_taken"] == "CYCLE_PRESERVED"
    assert resp.result["cycle_id"] == "PC-TEST-001"
    assert resp.result["email_sent"] is False


@pytest.mark.asyncio
async def test_pending_service_two_notes_analysis():
    db = AsyncMock()
    service = PendingService(db)

    service.cycle_repo.get_active_cycle = AsyncMock(return_value=None)
    mock_new_cycle = MagicMock()
    mock_new_cycle.id = "PC-NEW-002"
    mock_new_cycle.status = PendingCycleStatus.ACTIVE
    mock_new_cycle.reminder_count = 1
    mock_new_cycle.max_reminders = 3
    mock_new_cycle.next_reminder_at = None
    service.cycle_repo.create_cycle = AsyncMock(return_value=mock_new_cycle)

    mock_incident = MagicMock()
    mock_incident.id = "inc-456"
    mock_incident.incident_number = "INC0000100"
    mock_incident.caller = "Tina"
    mock_incident.assigned_to = "Aman Mourya"
    mock_incident.assignment_group = "Apps Run-SFDC"
    mock_incident.short_description = "Cannot open GTS"
    mock_incident.state = "on_hold"
    service.incident_service.get_incident = AsyncMock(return_value=mock_incident)

    # Two work notes: Latest is state change, previous is engineer query
    note1 = MagicMock()
    note1.message = "State changed to: on_hold"
    note1.source_name = "Aman Mourya"
    note1.source_type = "ENGINEER"

    note2 = MagicMock()
    note2.message = "Could you please provide the screenshot of the error message when opening GTS EANZ?"
    note2.source_name = "Aman Mourya"
    note2.source_type = "ENGINEER"

    service.work_note_svc.get_notes = AsyncMock(return_value=[note1, note2])
    service.work_note_svc.add_note = AsyncMock()
    service.incident_service.update_incident_internal = AsyncMock()

    resp = await service.process_pending_transition(incident_id="inc-456")
    assert resp.success is True
    assert resp.result["action_taken"] == "CYCLE_STARTED"
    assert resp.result["email_sent"] is True
    assert "Pending Agent: Reminder 1 of 3 sent to user." in resp.result["work_notes_added"]
    assert "Details Needed from You:" in resp.result["work_notes_added"]
