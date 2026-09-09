"""
Repository layer for PendingCycle persistence using SQLAlchemy.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.agents.pending.models.pending_cycle import PendingCycle, PendingCycleStatus


class PendingCycleRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_due_active_cycles(self) -> list[PendingCycle]:
        """Finds all active cycles whose next_reminder_at timestamp has passed."""
        now = datetime.now(timezone.utc)
        query = select(PendingCycle).where(
            PendingCycle.status == PendingCycleStatus.ACTIVE,
            PendingCycle.next_reminder_at.is_not(None),
            PendingCycle.next_reminder_at <= now,
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_active_cycle(self, incident_id: str) -> PendingCycle | None:
        """Finds any currently ACTIVE cycle for an incident."""
        query = select(PendingCycle).where(
            PendingCycle.incident_id == incident_id,
            PendingCycle.status == PendingCycleStatus.ACTIVE,
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_latest_cycle(self, incident_id: str) -> PendingCycle | None:
        """Finds the most recently created cycle for an incident."""
        query = (
            select(PendingCycle)
            .where(PendingCycle.incident_id == incident_id)
            .order_by(PendingCycle.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create_cycle(
        self,
        incident_id: str,
        incident_number: str,
        source_type: str,
        reminder_count: int = 1,
        max_reminders: int = 3,
    ) -> PendingCycle:
        """Creates and persists a new active pending cycle with 1-minute interval."""
        now = datetime.now(timezone.utc)
        cycle = PendingCycle(
            incident_id=incident_id,
            incident_number=incident_number,
            status=PendingCycleStatus.ACTIVE,
            reminder_count=reminder_count,
            max_reminders=max_reminders,
            source_type=source_type,
            next_reminder_at=now + timedelta(minutes=1),
            created_at=now,
            updated_at=now,
        )
        self.db.add(cycle)
        await self.db.commit()
        await self.db.refresh(cycle)
        return cycle

    async def increment_reminder(self, cycle: PendingCycle) -> PendingCycle:
        """Increments reminder count and advances next_reminder_at by 1 minute."""
        now = datetime.now(timezone.utc)
        cycle.reminder_count += 1
        cycle.updated_at = now
        if cycle.reminder_count >= cycle.max_reminders:
            cycle.status = PendingCycleStatus.COMPLETED
            cycle.next_reminder_at = None
        else:
            cycle.next_reminder_at = now + timedelta(minutes=1)
        await self.db.commit()
        await self.db.refresh(cycle)
        return cycle

    async def complete_cycle(self, cycle: PendingCycle) -> PendingCycle:
        """Marks cycle as COMPLETED."""
        cycle.status = PendingCycleStatus.COMPLETED
        cycle.next_reminder_at = None
        cycle.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(cycle)
        return cycle

    async def cancel_cycle(self, cycle: PendingCycle) -> PendingCycle:
        """Marks cycle as CANCELLED."""
        cycle.status = PendingCycleStatus.CANCELLED
        cycle.next_reminder_at = None
        cycle.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(cycle)
        return cycle

