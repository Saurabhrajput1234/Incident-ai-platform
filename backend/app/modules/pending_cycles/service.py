"""
PendingCycle Service — business logic layer.

Coordinates lifecycle operations for pending cycles.
Ensures idempotency, enforces single-active-cycle invariant,
and prevents duplicate active cycles under concurrent requests.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pending_cycles.repository import PendingCycleRepository
from app.modules.pending_cycles.schemas import (
    PendingCycleCreate,
    PendingCycleResponse,
    PendingCycleListResponse,
)
from app.modules.pending_cycles.enums import PendingCycleStatus
from app.modules.incidents.repository import IncidentRepository
from app.common.exceptions.base import NotFoundError, BadRequestError

logger = logging.getLogger(__name__)


class PendingCycleService:
    """
    Business logic layer for pending reminder cycles.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PendingCycleRepository(db)
        self.incident_repo = IncidentRepository(db)

    async def _resolve_incident_id(self, incident_id_or_number: str) -> str:
        """
        Resolve incident UUID whether given an INC number (e.g. INC0000001) or UUID.
        Raises NotFoundError if incident does not exist.
        """
        if incident_id_or_number.upper().startswith("INC"):
            incident = await self.incident_repo.get_by_number(incident_id_or_number.upper())
        else:
            incident = await self.incident_repo.get_by_id(incident_id_or_number)

        if not incident:
            logger.warning(f"Incident not found for pending cycle operation: {incident_id_or_number}")
            raise NotFoundError(f"Incident '{incident_id_or_number}' not found")

        return incident.id

    async def get_active_cycle(self, incident_id: str) -> PendingCycleResponse | None:
        """
        Retrieve the currently ACTIVE pending cycle for an incident, if one exists.
        Accepts either incident UUID or INC number.
        """
        resolved_id = await self._resolve_incident_id(incident_id)
        cycle = await self.repo.get_active_by_incident_id(resolved_id)
        return PendingCycleResponse.model_validate(cycle) if cycle else None

    async def get_cycle_by_id(self, cycle_id: str) -> PendingCycleResponse:
        """
        Retrieve a pending cycle by its primary key ID.
        Raises NotFoundError if not found.
        """
        cycle = await self.repo.get_by_id(cycle_id)
        if not cycle:
            raise NotFoundError(f"Pending cycle '{cycle_id}' not found")
        return PendingCycleResponse.model_validate(cycle)

    async def list_cycles_for_incident(self, incident_id: str) -> list[PendingCycleResponse]:
        """
        List all pending cycles (ACTIVE, COMPLETED, CANCELLED) for an incident.
        Accepts either incident UUID or INC number.
        """
        resolved_id = await self._resolve_incident_id(incident_id)
        cycles = await self.repo.list_by_incident_id(resolved_id)
        return [PendingCycleResponse.model_validate(c) for c in cycles]

    async def create_cycle_if_not_exists(
        self,
        incident_id: str,
        max_reminders: int = 3,
        reminder_template: str | None = None,
        next_reminder_at: datetime | None = None,
    ) -> PendingCycleResponse:
        """
        Idempotently create an ACTIVE PendingCycle for an incident.

        Business Rules:
        - If an ACTIVE cycle already exists for this incident, return the existing cycle.
        - If no ACTIVE cycle exists (e.g. initial transition to pending, or a previous
          cycle completed/cancelled), create a NEW PendingCycle.
        - Concurrency-safe: handles database partial unique index violations gracefully.
        """
        resolved_id = await self._resolve_incident_id(incident_id)

        # 1. Fast path: check for an existing active cycle
        existing = await self.repo.get_active_by_incident_id(resolved_id)
        if existing:
            logger.info(
                f"[PendingCycle] Idempotent lookup: active cycle {existing.id} already exists for incident {resolved_id}"
            )
            return PendingCycleResponse.model_validate(existing)

        # 2. Create a new cycle with database-enforced unique constraint protection
        try:
            new_cycle = await self.repo.create({
                "incident_id": resolved_id,
                "status": PendingCycleStatus.ACTIVE.value,
                "reminder_count": 0,
                "max_reminders": max_reminders,
                "reminder_template": reminder_template,
                "next_reminder_at": next_reminder_at,
            })
            logger.info(
                f"[PendingCycle] Created new active cycle {new_cycle.id} for incident {resolved_id}"
            )
            return PendingCycleResponse.model_validate(new_cycle)
        except IntegrityError:
            # Concurrent insert race condition caught by uq_active_cycle_per_incident constraint
            await self.db.rollback()
            existing = await self.repo.get_active_by_incident_id(resolved_id)
            if existing:
                logger.info(
                    f"[PendingCycle] Concurrency resolved: active cycle {existing.id} retrieved after conflict"
                )
                return PendingCycleResponse.model_validate(existing)
            raise

    async def increment_reminder(
        self,
        cycle_id: str,
        next_reminder_at: datetime | None = None,
    ) -> PendingCycleResponse:
        """
        Increment reminder_count for an ACTIVE cycle and optionally set next_reminder_at.
        Raises NotFoundError if cycle does not exist.
        Raises BadRequestError if cycle is not ACTIVE.
        """
        cycle = await self.repo.get_by_id(cycle_id)
        if not cycle:
            raise NotFoundError(f"Pending cycle '{cycle_id}' not found")

        if cycle.status != PendingCycleStatus.ACTIVE.value:
            raise BadRequestError(
                f"Cannot increment reminders on pending cycle '{cycle_id}' in status '{cycle.status}'"
            )

        updated = await self.repo.increment_reminder_count(
            cycle_id=cycle_id,
            next_reminder_at=next_reminder_at,
        )
        logger.info(
            f"[PendingCycle] Incremented reminder for cycle {cycle_id} to count={updated.reminder_count}"
        )
        return PendingCycleResponse.model_validate(updated)

    async def complete_cycle(
        self,
        cycle_id: str,
        completed_at: datetime | None = None,
    ) -> PendingCycleResponse:
        """
        Mark a pending cycle as COMPLETED.
        Leaves historical audit record in database.
        Raises NotFoundError if cycle does not exist.
        """
        cycle = await self.repo.get_by_id(cycle_id)
        if not cycle:
            raise NotFoundError(f"Pending cycle '{cycle_id}' not found")

        updated = await self.repo.mark_completed(cycle_id, completed_at=completed_at)
        logger.info(f"[PendingCycle] Marked cycle {cycle_id} as COMPLETED")
        return PendingCycleResponse.model_validate(updated)

    async def cancel_cycle(
        self,
        cycle_id: str,
        cancelled_at: datetime | None = None,
    ) -> PendingCycleResponse:
        """
        Mark a pending cycle as CANCELLED.
        Leaves historical audit record in database.
        Raises NotFoundError if cycle does not exist.
        """
        cycle = await self.repo.get_by_id(cycle_id)
        if not cycle:
            raise NotFoundError(f"Pending cycle '{cycle_id}' not found")

        updated = await self.repo.mark_cancelled(cycle_id, cancelled_at=cancelled_at)
        logger.info(f"[PendingCycle] Marked cycle {cycle_id} as CANCELLED")
        return PendingCycleResponse.model_validate(updated)

    async def complete_active_cycle(
        self,
        incident_id: str,
        completed_at: datetime | None = None,
    ) -> PendingCycleResponse | None:
        """
        Convenience method: locate the active cycle for an incident and mark it COMPLETED.
        Returns the updated cycle response, or None if no active cycle existed.
        """
        resolved_id = await self._resolve_incident_id(incident_id)
        active = await self.repo.get_active_by_incident_id(resolved_id)
        if not active:
            return None
        return await self.complete_cycle(active.id, completed_at=completed_at)

    async def cancel_active_cycle(
        self,
        incident_id: str,
        cancelled_at: datetime | None = None,
    ) -> PendingCycleResponse | None:
        """
        Convenience method: locate the active cycle for an incident and mark it CANCELLED.
        Returns the updated cycle response, or None if no active cycle existed.
        """
        resolved_id = await self._resolve_incident_id(incident_id)
        active = await self.repo.get_active_by_incident_id(resolved_id)
        if not active:
            return None
        return await self.cancel_cycle(active.id, cancelled_at=cancelled_at)
