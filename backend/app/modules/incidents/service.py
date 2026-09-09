"""
Incident Service — business logic layer.

This is the only place business rules and decisions live.
No SQL queries here — all DB access goes through IncidentRepository.
No HTTP concerns here — all HTTP handling stays in the API layer.

Flow: API -> Service -> Repository -> Database
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.incidents.repository import IncidentRepository
from app.modules.incidents.schemas import (
    IncidentCreate, IncidentUpdate, IncidentResponse, IncidentListResponse
)
from app.modules.work_notes.service import WorkNoteService
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType
from app.common.exceptions.base import NotFoundError, BadRequestError

logger = logging.getLogger(__name__)


class IncidentService:
    """
    Business logic layer for incidents.
    Validates inputs, calls repository, handles exceptions,
    and prepares response objects.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = IncidentRepository(db)
        self.work_note_svc = WorkNoteService(db)

    async def create_incident(self, payload: IncidentCreate) -> IncidentResponse:
        """
        Create a new incident and write an INCIDENT_CREATE work note immediately.
        """
        logger.info(f"Creating incident: {payload.short_description}")
        incident = await self.repo.create(payload.model_dump())
        logger.info(f"Incident created: {incident.incident_number}")

        # Record creation as the first work note
        caller_info = f" by {incident.caller}" if incident.caller else ""
        await self.work_note_svc.add_note(
            incident_id=incident.id,
            message=(
                f"Incident {incident.incident_number} created{caller_info}.\n"
                f"Description: {incident.short_description}\n"
                f"Priority: {incident.priority} | State: {incident.state} | "
                f"Source: {incident.source}"
            ),
            source_type=WorkNoteSourceType.SYSTEM,
            source_name="System",
            action_type=WorkNoteActionType.INCIDENT_CREATE,
        )

        return IncidentResponse.model_validate(incident)

    async def get_incident(self, incident_id: str) -> IncidentResponse:
        """
        Fetch a single incident by ID or incident number (INC0000001).
        Raises NotFoundError if the incident does not exist.
        """
        # Detect if input is an incident number (INCxxxxxxx) or UUID
        if incident_id.upper().startswith("INC"):
            incident = await self.repo.get_by_number(incident_id.upper())
        else:
            incident = await self.repo.get_by_id(incident_id)

        if not incident:
            logger.warning(f"Incident not found: {incident_id}")
            raise NotFoundError(f"Incident '{incident_id}' not found")
        return IncidentResponse.model_validate(incident)

    async def list_incidents(
        self,
        page: int = 1,
        page_size: int = 20,
        priority: str | None = None,
        state: str | None = None,
        category: str | None = None,
        assignment_group: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> IncidentListResponse:
        """
        Return a paginated list of incidents.
        Supports filtering by priority, state, category, assignment_group.
        Supports sorting by any column in asc/desc order.
        """
        # Convert page number to SQL offset
        offset = (page - 1) * page_size

        incidents, total = await self.repo.get_all(
            offset=offset,
            limit=page_size,
            priority=priority,
            state=state,
            category=category,
            assignment_group=assignment_group,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # Ceiling division for total pages
        pages = -(-total // page_size)

        return IncidentListResponse(
            items=[IncidentResponse.model_validate(i) for i in incidents],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def update_incident(self, incident_id: str, payload: IncidentUpdate) -> IncidentResponse:
        """
        Update an existing incident.
        Only fields explicitly provided in the payload are updated.
        Returns the existing record unchanged if no fields provided.
        Raises NotFoundError if the incident does not exist.
        """
        if incident_id.upper().startswith("INC"):
            existing = await self.repo.get_by_number(incident_id.upper())
        else:
            existing = await self.repo.get_by_id(incident_id)

        if not existing:
            logger.warning(f"Update failed — incident not found: {incident_id}")
            raise NotFoundError(f"Incident '{incident_id}' not found")

        # exclude_unset=True ensures only fields explicitly set in the payload are updated,
        # but preserves None values (unlike exclude_none which silently drops them)
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            # Nothing to update — return as is
            logger.warning(f"Update called with no fields: {incident_id}")
            return IncidentResponse.model_validate(existing)

        incident = await self.repo.update(existing.id, update_data)
        logger.info(f"Incident updated: {incident.incident_number}")

        # Determine action type based on what changed
        if "state" in update_data:
            action = WorkNoteActionType.STATE_CHANGE
            msg = f"State changed to: {update_data['state']}"
            if len(update_data) > 1:
                other = {k: v for k, v in update_data.items() if k != "state"}
                msg += f". Other fields updated: {', '.join(other.keys())}"
        elif "assigned_to" in update_data:
            action = WorkNoteActionType.ASSIGN_ENGINEER
            msg = f"Assigned to: {update_data['assigned_to']}"
        else:
            action = WorkNoteActionType.INCIDENT_UPDATE
            msg = f"Fields updated: {', '.join(update_data.keys())}"

        await self.work_note_svc.add_note(
            incident_id=existing.id,
            message=msg,
            source_type=WorkNoteSourceType.ENGINEER,
            source_name=existing.assigned_to or "Engineer",
            action_type=action,
        )

        # State change transitions
        if "state" in update_data:
            if update_data["state"] in ("pending", "on_hold"):
                try:
                    from app.modules.agents.pending.service import PendingService
                    pending_svc = PendingService(self.db)
                    await pending_svc.process_pending_transition(incident_id=existing.id)
                except Exception as e:
                    logger.error(f"[IncidentService] Auto-trigger for PendingAgent failed: {e}")
            else:
                # State moved away from pending (e.g. to in_progress/active, resolved, closed) -> cancel active pending cycle
                try:
                    from app.modules.agents.pending.repository import PendingCycleRepository
                    cycle_repo = PendingCycleRepository(self.db)
                    active_cycle = await cycle_repo.get_active_cycle(existing.id)
                    if active_cycle:
                        await cycle_repo.cancel_cycle(active_cycle)
                        logger.info(f"[IncidentService] Active pending cycle {active_cycle.id} cancelled because state moved to {update_data['state']}")
                except Exception as e:
                    logger.error(f"[IncidentService] Failed to cancel active pending cycle: {e}")

        return IncidentResponse.model_validate(incident)

    async def update_incident_internal(self, incident_id: str, payload: IncidentUpdate) -> IncidentResponse:
        """
        Update an incident without writing a work note.
        For use by agent services that write their own work notes.
        """
        if incident_id.upper().startswith("INC"):
            existing = await self.repo.get_by_number(incident_id.upper())
        else:
            existing = await self.repo.get_by_id(incident_id)

        if not existing:
            raise NotFoundError(f"Incident '{incident_id}' not found")

        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            return IncidentResponse.model_validate(existing)

        incident = await self.repo.update(existing.id, update_data)
        logger.info(f"Incident updated (internal): {incident.incident_number}")
        return IncidentResponse.model_validate(incident)

    async def delete_incident(self, incident_id: str) -> None:
        """
        Delete an incident permanently.
        Raises NotFoundError if the incident does not exist.
        """
        existing = await self.repo.get_by_id(incident_id)
        if not existing:
            logger.warning(f"Delete failed — incident not found: {incident_id}")
            raise NotFoundError(f"Incident '{incident_id}' not found")

        await self.repo.delete(incident_id)
        logger.info(f"Incident deleted: {existing.incident_number}")

    async def search_incidents(
        self,
        query: str,
        page: int = 1,
        page_size: int = 20,
        priority: str | None = None,
        state: str | None = None,
        category: str | None = None,
        assignment_group: str | None = None,
    ) -> IncidentListResponse:
        """
        Search incidents by keyword with optional filters.
        Searches across: incident_number, short_description,
        description, caller, assigned_to.
        Minimum query length is 2 characters.
        """
        if not query or len(query.strip()) < 2:
            raise BadRequestError("Search query must be at least 2 characters")

        offset = (page - 1) * page_size
        incidents, total = await self.repo.search(
            query=query.strip(),
            offset=offset,
            limit=page_size,
            priority=priority,
            state=state,
            category=category,
            assignment_group=assignment_group,
        )

        # Handle case where search returns 0 results
        pages = -(-total // page_size) if total else 0

        return IncidentListResponse(
            items=[IncidentResponse.model_validate(i) for i in incidents],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )
