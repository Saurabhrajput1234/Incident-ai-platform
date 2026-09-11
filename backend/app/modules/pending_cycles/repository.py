"""
PendingCycle Repository — database access layer.

All SQL queries for pending_cycles live here.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.pending_cycles.model import PendingCycle
from app.modules.pending_cycles.enums import PendingCycleStatus


class PendingCycleRepository:
    """
    Data access layer for the pending_cycles table.
    All methods are async and return SQLAlchemy model instances.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> PendingCycle:
        """
        Insert a new pending cycle record and return the persisted instance.
        """
        cycle = PendingCycle(
            id=data.get("id") or str(uuid.uuid4()),
            incident_id=data["incident_id"],
            status=data.get("status", PendingCycleStatus.ACTIVE.value),
            reminder_count=data.get("reminder_count", 0),
            max_reminders=data.get("max_reminders", 3),
            reminder_template=data.get("reminder_template"),
            next_reminder_at=data.get("next_reminder_at"),
            created_at=data.get("created_at") or datetime.now(timezone.utc),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc),
            completed_at=data.get("completed_at"),
            cancelled_at=data.get("cancelled_at"),
        )
        self.db.add(cycle)
        await self.db.commit()
        await self.db.refresh(cycle)
        return cycle

    async def get_by_id(self, cycle_id: str) -> PendingCycle | None:
        """Fetch a single pending cycle by its primary key UUID."""
        result = await self.db.execute(
            select(PendingCycle).where(PendingCycle.id == cycle_id)
        )
        return result.scalar_one_or_none()

    async def get_due_active_cycles(self) -> list[PendingCycle]:
        """
        Find all ACTIVE cycles whose next_reminder_at has passed (due for next reminder).
        Used by the background scheduler.
        """
        from datetime import datetime, timezone as tz
        now = datetime.now(tz.utc)
        result = await self.db.execute(
            select(PendingCycle).where(
                PendingCycle.status == PendingCycleStatus.ACTIVE.value,
                PendingCycle.next_reminder_at.is_not(None),
                PendingCycle.next_reminder_at <= now,
            )
        )
        return list(result.scalars().all())

    async def get_active_by_incident_id(self, incident_id: str) -> PendingCycle | None:
        """
        Fast lookup of the single active cycle for an incident.
        Leverages the partial unique index uq_active_cycle_per_incident.
        """
        result = await self.db.execute(
            select(PendingCycle).where(
                PendingCycle.incident_id == incident_id,
                PendingCycle.status == PendingCycleStatus.ACTIVE.value,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_incident_id(self, incident_id: str) -> list[PendingCycle]:
        """
        List all pending cycles for an incident in descending chronological order.
        Includes historical COMPLETED, CANCELLED, and currently ACTIVE cycles.
        """
        result = await self.db.execute(
            select(PendingCycle)
            .where(PendingCycle.incident_id == incident_id)
            .order_by(PendingCycle.created_at.desc())
        )
        return list(result.scalars().all())

    async def increment_reminder_count(
        self,
        cycle_id: str,
        next_reminder_at: datetime | None = None,
    ) -> PendingCycle | None:
        """
        Increment the reminder count by 1 and optionally update next_reminder_at.
        Returns the updated PendingCycle or None if not found.
        """
        cycle = await self.get_by_id(cycle_id)
        if not cycle:
            return None

        cycle.reminder_count += 1
        if next_reminder_at is not None:
            cycle.next_reminder_at = next_reminder_at
        cycle.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(cycle)
        return cycle

    async def update_next_reminder_at(
        self,
        cycle_id: str,
        next_reminder_at: datetime | None,
    ) -> PendingCycle | None:
        """
        Update the next_reminder_at timestamp.
        Returns the updated PendingCycle or None if not found.
        """
        cycle = await self.get_by_id(cycle_id)
        if not cycle:
            return None

        cycle.next_reminder_at = next_reminder_at
        cycle.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(cycle)
        return cycle

    async def mark_completed(
        self,
        cycle_id: str,
        completed_at: datetime | None = None,
    ) -> PendingCycle | None:
        """
        Mark a pending cycle as COMPLETED.
        Sets completed_at timestamp (defaults to current UTC time).
        """
        cycle = await self.get_by_id(cycle_id)
        if not cycle:
            return None

        cycle.status = PendingCycleStatus.COMPLETED.value
        cycle.completed_at = completed_at or datetime.now(timezone.utc)
        cycle.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(cycle)
        return cycle

    async def mark_cancelled(
        self,
        cycle_id: str,
        cancelled_at: datetime | None = None,
    ) -> PendingCycle | None:
        """
        Mark a pending cycle as CANCELLED.
        Sets cancelled_at timestamp (defaults to current UTC time).
        """
        cycle = await self.get_by_id(cycle_id)
        if not cycle:
            return None

        cycle.status = PendingCycleStatus.CANCELLED.value
        cycle.cancelled_at = cancelled_at or datetime.now(timezone.utc)
        cycle.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(cycle)
        return cycle
