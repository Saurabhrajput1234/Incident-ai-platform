"""Unit tests for IncidentService using mocked repository."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.modules.incidents.service import IncidentService
from app.modules.incidents.schemas import IncidentCreate, IncidentUpdate
from app.modules.incidents.enums import IncidentPriority, IncidentState, IncidentCategory
from app.common.exceptions.base import NotFoundError, BadRequestError


def make_mock_incident(incident_id="test-id", number="INC0000001"):
    m = MagicMock()
    m.id = incident_id
    m.incident_number = number
    m.short_description = "Test incident"
    m.description = None
    m.priority = IncidentPriority.MEDIUM.value
    m.state = IncidentState.NEW.value
    m.category = IncidentCategory.SOFTWARE.value
    m.subcategory = None
    m.impact = "2"
    m.urgency = "2"
    m.assignment_group = "IT Team"
    m.assigned_to = "john.doe"
    m.caller = "jane.doe"
    m.configuration_item = None
    m.business_service = None
    m.environment = "production"
    m.source = "manual"
    m.work_notes = None
    m.comments = None
    from datetime import datetime, timezone
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = datetime.now(timezone.utc)
    return m


@pytest.fixture
def service_with_mock():
    db = AsyncMock()
    service = IncidentService(db)
    service.repo = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_create_incident(service_with_mock):
    svc = service_with_mock
    mock_incident = make_mock_incident()
    svc.repo.create.return_value = mock_incident

    payload = IncidentCreate(short_description="Test incident")
    # Patch event-related methods — this is a unit test for IncidentService, not events
    with patch(
        "app.modules.work_notes.service.WorkNoteService._get_incident_state_and_number",
        return_value=("new", "INC0000001"),
    ), patch(
        "app.modules.work_notes.service.WorkNoteService._publish_work_note_event",
        new_callable=AsyncMock,
    ), patch(
        "app.orchestrator.bus.EventBus.publish",
        new_callable=AsyncMock,
    ):
        result = await svc.create_incident(payload)

    assert result.incident_number == "INC0000001"
    svc.repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_get_incident_not_found(service_with_mock):
    svc = service_with_mock
    svc.repo.get_by_id.return_value = None

    with pytest.raises(NotFoundError):
        await svc.get_incident("nonexistent-id")


@pytest.mark.asyncio
async def test_get_incident_found(service_with_mock):
    svc = service_with_mock
    mock_incident = make_mock_incident()
    svc.repo.get_by_id.return_value = mock_incident

    result = await svc.get_incident("test-id")
    assert result.id == "test-id"


@pytest.mark.asyncio
async def test_update_incident_not_found(service_with_mock):
    svc = service_with_mock
    svc.repo.get_by_id.return_value = None

    with pytest.raises(NotFoundError):
        await svc.update_incident("nonexistent-id", IncidentUpdate(state=IncidentState.RESOLVED))


@pytest.mark.asyncio
async def test_update_incident_success(service_with_mock):
    svc = service_with_mock
    mock_incident = make_mock_incident()
    updated = make_mock_incident()
    updated.state = IncidentState.RESOLVED.value
    svc.repo.get_by_id.return_value = mock_incident
    svc.repo.update.return_value = updated

    with patch(
        "app.modules.work_notes.service.WorkNoteService._get_incident_state_and_number",
        return_value=("new", "INC0000001"),
    ), patch(
        "app.modules.work_notes.service.WorkNoteService._publish_work_note_event",
        new_callable=AsyncMock,
    ), patch(
        "app.orchestrator.bus.EventBus.publish",
        new_callable=AsyncMock,
    ):
        result = await svc.update_incident("test-id", IncidentUpdate(state=IncidentState.RESOLVED))

    assert result.state == IncidentState.RESOLVED.value


@pytest.mark.asyncio
async def test_delete_incident_not_found(service_with_mock):
    svc = service_with_mock
    svc.repo.get_by_id.return_value = None

    with pytest.raises(NotFoundError):
        await svc.delete_incident("nonexistent-id")


@pytest.mark.asyncio
async def test_delete_incident_success(service_with_mock):
    svc = service_with_mock
    svc.repo.get_by_id.return_value = make_mock_incident()
    svc.repo.delete.return_value = True

    await svc.delete_incident("test-id")
    svc.repo.delete.assert_called_once_with("test-id")


@pytest.mark.asyncio
async def test_search_short_query(service_with_mock):
    svc = service_with_mock
    with pytest.raises(BadRequestError):
        await svc.search_incidents(query="a")


@pytest.mark.asyncio
async def test_list_incidents(service_with_mock):
    svc = service_with_mock
    svc.repo.get_all.return_value = ([make_mock_incident()], 1)

    result = await svc.list_incidents(page=1, page_size=20)
    assert result.total == 1
    assert result.pages == 1
