"""
Unit tests for PendingCycleService using mocked repository and incident repository.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.modules.pending_cycles.service import PendingCycleService
from app.modules.pending_cycles.enums import PendingCycleStatus
from app.common.exceptions.base import NotFoundError, BadRequestError


def make_mock_incident(incident_id="inc-1", number="INC0000001"):
    m = MagicMock()
    m.id = incident_id
    m.incident_number = number
    return m


def make_mock_cycle(
    cycle_id="cycle-1",
    incident_id="inc-1",
    status=PendingCycleStatus.ACTIVE.value,
    reminder_count=0,
    max_reminders=3,
    reminder_template=None,
    next_reminder_at=None,
):
    m = MagicMock()
    m.id = cycle_id
    m.incident_id = incident_id
    m.status = status
    m.reminder_count = reminder_count
    m.max_reminders = max_reminders
    m.reminder_template = reminder_template
    m.next_reminder_at = next_reminder_at
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = datetime.now(timezone.utc)
    m.completed_at = None
    m.cancelled_at = None
    return m


@pytest.fixture
def service():
    db = AsyncMock()
    svc = PendingCycleService(db)
    svc.repo = AsyncMock()
    svc.incident_repo = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_resolve_incident_id_by_uuid(service):
    service.incident_repo.get_by_id.return_value = make_mock_incident("uuid-123", "INC0000001")
    resolved = await service._resolve_incident_id("uuid-123")
    assert resolved == "uuid-123"
    service.incident_repo.get_by_id.assert_called_once_with("uuid-123")


@pytest.mark.asyncio
async def test_resolve_incident_id_by_inc_number(service):
    service.incident_repo.get_by_number.return_value = make_mock_incident("uuid-456", "INC0000042")
    resolved = await service._resolve_incident_id("INC0000042")
    assert resolved == "uuid-456"
    service.incident_repo.get_by_number.assert_called_once_with("INC0000042")


@pytest.mark.asyncio
async def test_resolve_incident_id_not_found(service):
    service.incident_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundError):
        await service._resolve_incident_id("non-existent")


@pytest.mark.asyncio
async def test_get_active_cycle_found(service):
    service.incident_repo.get_by_id.return_value = make_mock_incident("inc-1")
    service.repo.get_active_by_incident_id.return_value = make_mock_cycle("cycle-1", "inc-1")

    res = await service.get_active_cycle("inc-1")
    assert res is not None
    assert res.id == "cycle-1"
    assert res.status == PendingCycleStatus.ACTIVE.value
    assert res.reminder_count == 0


@pytest.mark.asyncio
async def test_get_active_cycle_none(service):
    service.incident_repo.get_by_id.return_value = make_mock_incident("inc-1")
    service.repo.get_active_by_incident_id.return_value = None

    res = await service.get_active_cycle("inc-1")
    assert res is None


@pytest.mark.asyncio
async def test_create_cycle_if_not_exists_returns_existing_when_active(service):
    service.incident_repo.get_by_id.return_value = make_mock_incident("inc-1")
    existing_cycle = make_mock_cycle("cycle-existing", "inc-1")
    service.repo.get_active_by_incident_id.return_value = existing_cycle

    res = await service.create_cycle_if_not_exists("inc-1")
    assert res.id == "cycle-existing"
    service.repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_create_cycle_if_not_exists_creates_when_no_active(service):
    service.incident_repo.get_by_id.return_value = make_mock_incident("inc-1")
    service.repo.get_active_by_incident_id.return_value = None

    new_cycle = make_mock_cycle("cycle-new", "inc-1", reminder_count=0, max_reminders=3)
    service.repo.create.return_value = new_cycle

    res = await service.create_cycle_if_not_exists("inc-1", max_reminders=3)
    assert res.id == "cycle-new"
    assert res.reminder_count == 0
    assert res.status == PendingCycleStatus.ACTIVE.value
    service.repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_increment_reminder_success(service):
    active_cycle = make_mock_cycle("cycle-1", reminder_count=0)
    service.repo.get_by_id.return_value = active_cycle

    updated_cycle = make_mock_cycle("cycle-1", reminder_count=1)
    service.repo.increment_reminder_count.return_value = updated_cycle

    res = await service.increment_reminder("cycle-1")
    assert res.reminder_count == 1
    service.repo.increment_reminder_count.assert_called_once()


@pytest.mark.asyncio
async def test_increment_reminder_not_active_raises_bad_request(service):
    completed_cycle = make_mock_cycle("cycle-1", status=PendingCycleStatus.COMPLETED.value)
    service.repo.get_by_id.return_value = completed_cycle

    with pytest.raises(BadRequestError):
        await service.increment_reminder("cycle-1")


@pytest.mark.asyncio
async def test_complete_cycle(service):
    cycle = make_mock_cycle("cycle-1")
    service.repo.get_by_id.return_value = cycle

    completed = make_mock_cycle("cycle-1", status=PendingCycleStatus.COMPLETED.value)
    completed.completed_at = datetime.now(timezone.utc)
    service.repo.mark_completed.return_value = completed

    res = await service.complete_cycle("cycle-1")
    assert res.status == PendingCycleStatus.COMPLETED.value
    service.repo.mark_completed.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_cycle(service):
    cycle = make_mock_cycle("cycle-1")
    service.repo.get_by_id.return_value = cycle

    cancelled = make_mock_cycle("cycle-1", status=PendingCycleStatus.CANCELLED.value)
    cancelled.cancelled_at = datetime.now(timezone.utc)
    service.repo.mark_cancelled.return_value = cancelled

    res = await service.cancel_cycle("cycle-1")
    assert res.status == PendingCycleStatus.CANCELLED.value
    service.repo.mark_cancelled.assert_called_once()
