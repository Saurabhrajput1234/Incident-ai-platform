"""
Integration tests for PendingCycle model, repository, and service against real database session.
Validates all 12 required business scenarios.
"""
import pytest
import uuid
from datetime import datetime, timezone
import sqlalchemy as sa

from app.modules.incidents.model import Incident
from app.modules.incidents.enums import IncidentPriority, IncidentState
from app.modules.pending_cycles.model import PendingCycle
from app.modules.pending_cycles.enums import PendingCycleStatus
from app.modules.pending_cycles.service import PendingCycleService
from app.modules.pending_cycles.repository import PendingCycleRepository
from app.common.exceptions.base import NotFoundError, BadRequestError


async def _create_test_incident(db, number=None) -> Incident:
    inc_num = number or f"INC{uuid.uuid4().hex[:7].upper()}"
    inc = Incident(
        id=str(uuid.uuid4()),
        incident_number=inc_num,
        short_description="Pending cycle test incident",
        priority=IncidentPriority.MEDIUM,
        state=IncidentState.IN_PROGRESS,
    )
    db.add(inc)
    await db.commit()
    await db.refresh(inc)
    return inc


@pytest.mark.anyio
async def test_scenario_1_and_2_create_cycle_and_initial_reminder_count_zero(db_session):
    """
    Scenario 1: Create PendingCycle.
    Scenario 2: Initial reminder_count = 0.
    """
    inc = await _create_test_incident(db_session)
    service = PendingCycleService(db_session)

    cycle = await service.create_cycle_if_not_exists(
        incident_id=inc.id,
        max_reminders=3,
        reminder_template="standard_pending.html",
    )

    assert cycle.id is not None
    assert cycle.incident_id == inc.id
    assert cycle.status == PendingCycleStatus.ACTIVE.value
    assert cycle.reminder_count == 0
    assert cycle.max_reminders == 3
    assert cycle.reminder_template == "standard_pending.html"
    assert cycle.completed_at is None
    assert cycle.cancelled_at is None


@pytest.mark.anyio
async def test_scenario_3_retrieve_active_cycle_by_incident(db_session):
    """
    Scenario 3: Retrieve active cycle by incident.
    """
    inc = await _create_test_incident(db_session)
    service = PendingCycleService(db_session)

    created = await service.create_cycle_if_not_exists(inc.id)
    retrieved = await service.get_active_cycle(inc.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.status == PendingCycleStatus.ACTIVE.value

    # Also test retrieve using INC incident number
    retrieved_by_number = await service.get_active_cycle(inc.incident_number)
    assert retrieved_by_number is not None
    assert retrieved_by_number.id == created.id


@pytest.mark.anyio
async def test_scenario_4_and_5_idempotent_creation(db_session):
    """
    Scenario 4: create_cycle_if_not_exists() creates exactly one cycle.
    Scenario 5: Calling create_cycle_if_not_exists() again returns the same active cycle.
    """
    inc = await _create_test_incident(db_session)
    service = PendingCycleService(db_session)

    first = await service.create_cycle_if_not_exists(inc.id)
    second = await service.create_cycle_if_not_exists(inc.id)
    third = await service.create_cycle_if_not_exists(inc.incident_number)

    assert first.id == second.id
    assert first.id == third.id

    # Verify in DB there is strictly 1 cycle
    cycles = await service.list_cycles_for_incident(inc.id)
    assert len(cycles) == 1


@pytest.mark.anyio
async def test_scenario_6_increment_reminder_count(db_session):
    """
    Scenario 6: Increment reminder count.
    """
    inc = await _create_test_incident(db_session)
    service = PendingCycleService(db_session)

    cycle = await service.create_cycle_if_not_exists(inc.id)
    assert cycle.reminder_count == 0

    next_time = datetime.now(timezone.utc)
    updated1 = await service.increment_reminder(cycle.id, next_reminder_at=next_time)
    assert updated1.reminder_count == 1
    assert updated1.next_reminder_at is not None

    updated2 = await service.increment_reminder(cycle.id)
    assert updated2.reminder_count == 2


@pytest.mark.anyio
async def test_scenario_7_complete_cycle(db_session):
    """
    Scenario 7: Complete cycle.
    """
    inc = await _create_test_incident(db_session)
    service = PendingCycleService(db_session)

    cycle = await service.create_cycle_if_not_exists(inc.id)
    assert cycle.status == PendingCycleStatus.ACTIVE.value

    completed = await service.complete_cycle(cycle.id)
    assert completed.status == PendingCycleStatus.COMPLETED.value
    assert completed.completed_at is not None

    # Active cycle lookup should now return None
    active = await service.get_active_cycle(inc.id)
    assert active is None

    # Trying to increment reminders on a completed cycle must fail
    with pytest.raises(BadRequestError):
        await service.increment_reminder(cycle.id)


@pytest.mark.anyio
async def test_scenario_8_cancel_cycle(db_session):
    """
    Scenario 8: Cancel cycle.
    """
    inc = await _create_test_incident(db_session)
    service = PendingCycleService(db_session)

    cycle = await service.create_cycle_if_not_exists(inc.id)
    assert cycle.status == PendingCycleStatus.ACTIVE.value

    cancelled = await service.cancel_cycle(cycle.id)
    assert cancelled.status == PendingCycleStatus.CANCELLED.value
    assert cancelled.cancelled_at is not None

    # Active cycle lookup should now return None
    active = await service.get_active_cycle(inc.id)
    assert active is None

    # Trying to increment reminders on a cancelled cycle must fail
    with pytest.raises(BadRequestError):
        await service.increment_reminder(cycle.id)


@pytest.mark.anyio
async def test_scenario_9_after_completed_creates_new_cycle(db_session):
    """
    Scenario 9: After COMPLETED cycle, create_cycle_if_not_exists() creates a NEW cycle.
    """
    inc = await _create_test_incident(db_session)
    service = PendingCycleService(db_session)

    cycle1 = await service.create_cycle_if_not_exists(inc.id)
    await service.increment_reminder(cycle1.id)
    await service.complete_cycle(cycle1.id)

    # Later: ACTIVE -> PENDING transition
    cycle2 = await service.create_cycle_if_not_exists(inc.id)
    assert cycle2.id != cycle1.id
    assert cycle2.status == PendingCycleStatus.ACTIVE.value
    assert cycle2.reminder_count == 0  # reset for new cycle

    # Both cycles exist in history
    history = await service.list_cycles_for_incident(inc.id)
    assert len(history) == 2
    statuses = {c.status for c in history}
    assert statuses == {PendingCycleStatus.COMPLETED.value, PendingCycleStatus.ACTIVE.value}


@pytest.mark.anyio
async def test_scenario_10_after_cancelled_creates_new_cycle(db_session):
    """
    Scenario 10: After CANCELLED cycle, create_cycle_if_not_exists() creates a NEW cycle.
    """
    inc = await _create_test_incident(db_session)
    service = PendingCycleService(db_session)

    cycle1 = await service.create_cycle_if_not_exists(inc.id)
    await service.cancel_cycle(cycle1.id)

    # Later: ACTIVE -> PENDING transition
    cycle2 = await service.create_cycle_if_not_exists(inc.id)
    assert cycle2.id != cycle1.id
    assert cycle2.status == PendingCycleStatus.ACTIVE.value
    assert cycle2.reminder_count == 0

    history = await service.list_cycles_for_incident(inc.id)
    assert len(history) == 2
    statuses = {c.status for c in history}
    assert statuses == {PendingCycleStatus.CANCELLED.value, PendingCycleStatus.ACTIVE.value}


@pytest.mark.anyio
async def test_scenario_11_database_level_protection_against_duplicate_active(db_session):
    """
    Scenario 11: Database/service protection prevents two ACTIVE cycles for the same incident.
    Tests that a direct SQL insert bypassing the service triggers the database constraint.
    """
    inc = await _create_test_incident(db_session)
    repo = PendingCycleRepository(db_session)

    # Create first ACTIVE cycle
    await repo.create({"incident_id": inc.id, "status": PendingCycleStatus.ACTIVE.value})

    # Attempt to insert a second ACTIVE cycle directly via repository/SQL
    with pytest.raises(sa.exc.IntegrityError):
        c2 = PendingCycle(
            id=str(uuid.uuid4()),
            incident_id=inc.id,
            status=PendingCycleStatus.ACTIVE.value,
        )
        db_session.add(c2)
        await db_session.commit()

    await db_session.rollback()


@pytest.mark.anyio
async def test_scenario_12_multiple_incidents_each_have_own_active_cycle(db_session):
    """
    Scenario 12: Multiple incidents can each have their own ACTIVE cycle.
    """
    inc1 = await _create_test_incident(db_session)
    inc2 = await _create_test_incident(db_session)
    service = PendingCycleService(db_session)

    cycle1 = await service.create_cycle_if_not_exists(inc1.id)
    cycle2 = await service.create_cycle_if_not_exists(inc2.id)

    assert cycle1.id != cycle2.id
    assert cycle1.incident_id == inc1.id
    assert cycle2.incident_id == inc2.id
    assert cycle1.status == PendingCycleStatus.ACTIVE.value
    assert cycle2.status == PendingCycleStatus.ACTIVE.value

    # Active lookups return correct cycle per incident
    assert (await service.get_active_cycle(inc1.id)).id == cycle1.id
    assert (await service.get_active_cycle(inc2.id)).id == cycle2.id


@pytest.mark.anyio
async def test_convenience_complete_and_cancel_active_cycle(db_session):
    """Test convenience methods complete_active_cycle and cancel_active_cycle."""
    inc = await _create_test_incident(db_session)
    service = PendingCycleService(db_session)

    # Complete active cycle
    await service.create_cycle_if_not_exists(inc.id)
    res1 = await service.complete_active_cycle(inc.id)
    assert res1 is not None
    assert res1.status == PendingCycleStatus.COMPLETED.value
    assert await service.get_active_cycle(inc.id) is None

    # Cancel active cycle
    await service.create_cycle_if_not_exists(inc.id)
    res2 = await service.cancel_active_cycle(inc.id)
    assert res2 is not None
    assert res2.status == PendingCycleStatus.CANCELLED.value
    assert await service.get_active_cycle(inc.id) is None
