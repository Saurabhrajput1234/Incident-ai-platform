"""Unit tests for WorkNoteService using a mocked repository."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.work_notes.service import WorkNoteService
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType


def _make_note(
    incident_id="inc-1",
    source_type=WorkNoteSourceType.TRIAGE_AGENT,
    source_name="TriageAgent",
    action_type=WorkNoteActionType.ASSIGN_ENGINEER,
    message="Assigned to Alice",
    source_id=None,
):
    m = MagicMock()
    m.id = "note-1"
    m.incident_id = incident_id
    m.message = message
    m.source_type = source_type.value
    m.source_name = source_name
    m.source_id = source_id
    m.action_type = action_type.value if action_type else None
    m.created_at = datetime.now(timezone.utc)
    return m


@pytest.fixture
def service():
    db = AsyncMock()
    svc = WorkNoteService(db)
    svc.repo = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_add_note_returns_response(service):
    note = _make_note()
    service.repo.create.return_value = note

    with patch.object(service, "_get_incident_state_and_number", return_value=("on_hold", "INC0000001")), \
         patch.object(service, "_publish_work_note_event", new=AsyncMock()):
        result = await service.add_note(
            incident_id="inc-1",
            message="Assigned to Alice",
            source_type=WorkNoteSourceType.TRIAGE_AGENT,
            source_name="TriageAgent",
            action_type=WorkNoteActionType.ASSIGN_ENGINEER,
            auto_activate=False,  # unit test — isolation only
        )

    assert result.incident_id == "inc-1"
    assert result.source_type == WorkNoteSourceType.TRIAGE_AGENT.value
    assert result.source_name == "TriageAgent"
    assert result.action_type == WorkNoteActionType.ASSIGN_ENGINEER.value
    service.repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_add_note_passes_correct_payload(service):
    note = _make_note(source_id="eng-42")
    service.repo.create.return_value = note

    with patch.object(service, "_get_incident_state_and_number", return_value=("on_hold", "INC0000001")), \
         patch.object(service, "_publish_work_note_event", new=AsyncMock()):
        await service.add_note(
            incident_id="inc-1",
            message="Test",
            source_type=WorkNoteSourceType.ENGINEER,
            source_name="Alice",
            source_id="eng-42",
            action_type=WorkNoteActionType.MANUAL_NOTE,
            auto_activate=False,  # unit test — isolation only
        )

    call_kwargs = service.repo.create.call_args[0][0]
    assert call_kwargs["incident_id"] == "inc-1"
    assert call_kwargs["source_type"] == WorkNoteSourceType.ENGINEER.value
    assert call_kwargs["source_id"] == "eng-42"


@pytest.mark.asyncio
async def test_get_notes_returns_list(service):
    notes = [_make_note(), _make_note()]
    service.repo.get_by_incident.return_value = notes

    result = await service.get_notes("inc-1")

    assert len(result) == 2
    service.repo.get_by_incident.assert_called_once_with("inc-1", limit=100)


@pytest.mark.asyncio
async def test_get_latest_returns_note(service):
    note = _make_note()
    service.repo.get_latest_by_incident.return_value = note

    result = await service.get_latest("inc-1")

    assert result is not None
    assert result.source_name == "TriageAgent"


@pytest.mark.asyncio
async def test_get_latest_returns_none_when_empty(service):
    service.repo.get_latest_by_incident.return_value = None

    result = await service.get_latest("inc-1")

    assert result is None


@pytest.mark.asyncio
async def test_get_by_source_type(service):
    notes = [_make_note(source_type=WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT, source_name="AckAgent")]
    service.repo.get_by_source_type.return_value = notes

    result = await service.get_by_source_type("inc-1", WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT)

    assert len(result) == 1
    assert result[0].source_type == WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT.value
    service.repo.get_by_source_type.assert_called_once_with(
        "inc-1", WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT.value
    )


@pytest.mark.asyncio
async def test_get_latest_by_source_type_returns_first(service):
    note1 = _make_note(message="latest")
    note2 = _make_note(message="older")
    service.repo.get_by_source_type.return_value = [note1, note2]

    result = await service.get_latest_by_source_type("inc-1", WorkNoteSourceType.TRIAGE_AGENT)

    assert result.message == "latest"


@pytest.mark.asyncio
async def test_get_latest_by_source_type_none_when_empty(service):
    service.repo.get_by_source_type.return_value = []

    result = await service.get_latest_by_source_type("inc-1", WorkNoteSourceType.SYSTEM)

    assert result is None


def test_build_legacy_text_formats_notes():
    db = AsyncMock()
    svc = WorkNoteService(db)

    note1 = MagicMock()
    note1.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    note1.source_type = "TRIAGE_AGENT"
    note1.source_name = "TriageAgent"
    note1.action_type = "ASSIGN_ENGINEER"
    note1.message = "Assigned to Alice"

    note2 = MagicMock()
    note2.created_at = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
    note2.source_type = "SYSTEM"
    note2.source_name = "System"
    note2.action_type = None
    note2.message = "Incident created"

    text = svc.build_legacy_text([note1, note2])

    assert "TriageAgent" in text
    assert "ASSIGN_ENGINEER" in text
    assert "Assigned to Alice" in text
    assert "Incident created" in text
    assert "─" * 40 in text


def test_build_legacy_text_empty_list():
    db = AsyncMock()
    svc = WorkNoteService(db)
    assert svc.build_legacy_text([]) == ""
