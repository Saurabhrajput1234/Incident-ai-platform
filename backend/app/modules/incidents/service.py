"""
Incident Service — business logic layer.

All incident state transitions publish IncidentStateChangedEvent to the event bus.
Agents are triggered by the orchestration layer — not by direct calls here.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.incidents.repository import IncidentRepository
from app.modules.incidents.schemas import (
    IncidentCreate, IncidentUpdate, IncidentResponse, IncidentListResponse
)
from app.modules.work_notes.service import WorkNoteService
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType
from app.modules.work_notes.model import IncidentWorkNote
from app.common.exceptions.base import NotFoundError, BadRequestError

logger = logging.getLogger(__name__)

_ON_HOLD_STATE = "on_hold"
_AUTO_ACTIVATE_STATE = "in_progress"
_ALREADY_ACTIVE_STATES = {"in_progress", "resolved", "closed", "cancelled"}
_RESOLUTION_CURRENT_STATE = "active"


class IncidentService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = IncidentRepository(db)
        self.work_note_svc = WorkNoteService(db)

    async def create_incident(self, payload: IncidentCreate) -> IncidentResponse:
        logger.info(f"Creating incident: {payload.short_description}")
        incident = await self.repo.create(payload.model_dump())
        logger.info(f"Incident created: {incident.incident_number}")

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
            auto_activate=False,
        )

        # Publish event — TriageHandler picks this up
        from app.orchestrator.bus import event_bus
        from app.orchestrator.events import IncidentCreatedEvent
        await event_bus.publish(IncidentCreatedEvent(
            incident_id=incident.id,
            incident_number=incident.incident_number,
            assignment_group=incident.assignment_group,
            priority=str(incident.priority),
            state=str(incident.state.value if hasattr(incident.state, "value") else incident.state),
            created_at=incident.created_at,
        ))

        return IncidentResponse.model_validate(incident)

    async def get_incident(self, incident_id: str) -> IncidentResponse:
        if incident_id.upper().startswith("INC"):
            incident = await self.repo.get_by_number(incident_id.upper())
        else:
            incident = await self.repo.get_by_id(incident_id)
        if not incident:
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
        offset = (page - 1) * page_size
        incidents, total = await self.repo.get_all(
            offset=offset, limit=page_size,
            priority=priority, state=state,
            category=category, assignment_group=assignment_group,
            sort_by=sort_by, sort_order=sort_order,
        )
        pages = -(-total // page_size)
        return IncidentListResponse(
            items=[IncidentResponse.model_validate(i) for i in incidents],
            total=total, page=page, page_size=page_size, pages=pages,
        )

    async def update_incident(
        self,
        incident_id: str,
        payload: IncidentUpdate,
    ) -> IncidentResponse:
        """Update by engineer / API — writes a work note."""
        if incident_id.upper().startswith("INC"):
            existing = await self.repo.get_by_number(incident_id.upper())
        else:
            existing = await self.repo.get_by_id(incident_id)
        if not existing:
            raise NotFoundError(f"Incident '{incident_id}' not found")

        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            return IncidentResponse.model_validate(existing)

        old_state: str = str(existing.state.value if hasattr(existing.state, "value") else existing.state)
        old_group: str | None = existing.assignment_group
        new_state: str | None = (
            str(update_data["state"].value if hasattr(update_data.get("state"), "value") else update_data["state"])
            if "state" in update_data else None
        )

        # Detect re-triage scenarios BEFORE saving
        group_changed = (
            "assignment_group" in update_data
            and update_data["assignment_group"]
            and update_data["assignment_group"] != old_group
        )
        engineer_removed = (
            "assigned_to" in update_data
            and not update_data["assigned_to"]  # cleared to null/empty
        )

        # Capture old values BEFORE the DB update — repo.update() refreshes the object
        old_assigned_to: str | None = existing.assigned_to

        # When group changes, also clear the engineer — wrong group = wrong engineer
        if group_changed and "assigned_to" not in update_data:
            update_data["assigned_to"] = None

        incident = await self.repo.update(existing.id, update_data)
        logger.info(f"Incident updated: {incident.incident_number}")

        # Write a separate work note for each meaningful change

        # 1. State change
        if "state" in update_data and new_state != old_state:
            await self.work_note_svc.add_note(
                incident_id=existing.id,
                message=f"State changed from {old_state} to {new_state}.",
                source_type=WorkNoteSourceType.ENGINEER,
                source_name=old_assigned_to or "Engineer",
                action_type=WorkNoteActionType.STATE_CHANGE,
                auto_activate=False,
            )

        # 2. Engineer removed
        if engineer_removed:
            await self.work_note_svc.add_note(
                incident_id=existing.id,
                message=(
                    f"Engineer removed: {old_assigned_to} has been unassigned from this incident.\n"
                    f"Triage Agent will automatically re-assign a new engineer."
                ),
                source_type=WorkNoteSourceType.ENGINEER,
                source_name=old_assigned_to or "Engineer",
                action_type=WorkNoteActionType.ASSIGN_ENGINEER,
                auto_activate=False,
            )

        # 3. Assignment group changed (also clears engineer)
        if group_changed:
            old_eng = old_assigned_to or "none"
            await self.work_note_svc.add_note(
                incident_id=existing.id,
                message=(
                    f"Assignment group changed from '{old_group or 'none'}' to '{update_data['assignment_group']}'.\n"
                    f"Previous engineer ({old_eng}) has been unassigned.\n"
                    f"Triage Agent will automatically assign a new engineer for the updated group."
                ),
                source_type=WorkNoteSourceType.ENGINEER,
                source_name=old_assigned_to or "Engineer",
                action_type=WorkNoteActionType.GROUP_RESOLVED,
                auto_activate=False,
            )

        # 4. Engineer manually assigned (not removed, not part of group change)
        if "assigned_to" in update_data and update_data["assigned_to"] and not group_changed:
            await self.work_note_svc.add_note(
                incident_id=existing.id,
                message=f"Manually assigned to: {update_data['assigned_to']}.",
                source_type=WorkNoteSourceType.ENGINEER,
                source_name=old_assigned_to or "Engineer",
                action_type=WorkNoteActionType.ASSIGN_ENGINEER,
                auto_activate=False,
            )

        # 5. General field update — only fields that are not triage/system fields
        _skip_fields = {"assigned_to", "assignment_group", "state", "updated_at", "work_notes"}
        other_fields = [k for k in update_data.keys() if k not in _skip_fields]
        if other_fields and not group_changed and not engineer_removed:
            await self.work_note_svc.add_note(
                incident_id=existing.id,
                message=f"Fields updated: {', '.join(other_fields)}.",
                source_type=WorkNoteSourceType.ENGINEER,
                source_name=old_assigned_to or "Engineer",
                action_type=WorkNoteActionType.INCIDENT_UPDATE,
                auto_activate=False,
            )

        # Publish state change event — handlers decide what to do
        if new_state is not None and new_state != old_state:
            await self._publish_state_change(
                incident_id=existing.id,
                incident_number=incident.incident_number,
                old_state=old_state,
                new_state=new_state,
                changed_by="ENGINEER",
            )

        # Re-triage: engineer removed
        if engineer_removed and not group_changed:
            current_state = new_state or old_state
            await self._publish_retriage(
                incident_id=existing.id,
                incident_number=incident.incident_number,
                reason="engineer_removed",
                current_state=current_state,
            )

        # Re-triage: assignment group changed (takes priority over engineer_removed)
        if group_changed:
            current_state = new_state or old_state
            await self._publish_retriage(
                incident_id=existing.id,
                incident_number=incident.incident_number,
                reason="group_changed",
                current_state=current_state,
            )

        return IncidentResponse.model_validate(incident)

    async def update_incident_internal(
        self,
        incident_id: str,
        payload: IncidentUpdate,
        changed_by: str = "system",
    ) -> IncidentResponse:
        """Agent-driven update — no work note written here (agents write their own)."""
        if incident_id.upper().startswith("INC"):
            existing = await self.repo.get_by_number(incident_id.upper())
        else:
            existing = await self.repo.get_by_id(incident_id)
        if not existing:
            raise NotFoundError(f"Incident '{incident_id}' not found")

        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            return IncidentResponse.model_validate(existing)

        old_state: str = str(existing.state.value if hasattr(existing.state, "value") else existing.state)
        new_state: str | None = (
            str(update_data["state"].value if hasattr(update_data.get("state"), "value") else update_data["state"])
            if "state" in update_data else None
        )

        incident = await self.repo.update(existing.id, update_data)
        logger.info(f"Incident updated (internal): {incident.incident_number}")

        # Publish state change event — handlers decide what to do
        if new_state is not None and new_state != old_state:
            await self._publish_state_change(
                incident_id=existing.id,
                incident_number=incident.incident_number,
                old_state=old_state,
                new_state=new_state,
                changed_by=changed_by,
            )

        return IncidentResponse.model_validate(incident)
# auto_activate when a worknote is added ( called by worknoteservice)
    async def activate_incident_from_work_note(
        self,
        incident_id: str,
        triggered_by: str,
        triggering_work_note_id: str | None = None,
        triggering_work_note_source: str | None = None,
    ) -> None:
        """Auto-activate when a work note is added (called by WorkNoteService)."""
        incident = await self.repo.get_by_id(incident_id)
        if incident is None:
            return

        old_state: str = str(incident.state.value if hasattr(incident.state, "value") else incident.state)
        if old_state in _ALREADY_ACTIVE_STATES:
            return

        await self.repo.update(incident_id, {"state": _AUTO_ACTIVATE_STATE})
        logger.info(
            "[IncidentService:AutoActivate] %s: %s → %s (triggered by %s, source=%s)",
            incident_id, old_state, _AUTO_ACTIVATE_STATE,
            triggered_by, triggering_work_note_source,
        )

        # Write STATE_CHANGE audit note directly (avoid recursive add_note)
        from app.modules.work_notes.repository import WorkNoteRepository
        wn_repo = WorkNoteRepository(self.db)
        await wn_repo.create({
            "incident_id": incident_id,
            "message": (
                f"Incident automatically moved to In Progress.\n"
                f"Reason: Work note added by {triggered_by}.\n"
                f"Previous state: {old_state}"
            ),
            "source_type": WorkNoteSourceType.SYSTEM.value,
            "source_name": "WorkNoteService",
            "source_id": None,
            "action_type": WorkNoteActionType.STATE_CHANGE.value,
        })

        # Publish state change — ResolutionHandler will pick this up if on_hold → active
        await self._publish_state_change(
            incident_id=incident_id,
            incident_number=incident.incident_number,
            old_state=old_state,
            new_state=_AUTO_ACTIVATE_STATE,
            changed_by=triggered_by,
            triggering_work_note_id=triggering_work_note_id,
            triggering_work_note_source=triggering_work_note_source,
        )

    async def delete_incident(self, incident_id: str) -> None:
        existing = await self.repo.get_by_id(incident_id)
        if not existing:
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
        if not query or len(query.strip()) < 2:
            raise BadRequestError("Search query must be at least 2 characters")
        offset = (page - 1) * page_size
        incidents, total = await self.repo.search(
            query=query.strip(), offset=offset, limit=page_size,
            priority=priority, state=state,
            category=category, assignment_group=assignment_group,
        )
        pages = -(-total // page_size) if total else 0
        return IncidentListResponse(
            items=[IncidentResponse.model_validate(i) for i in incidents],
            total=total, page=page, page_size=page_size, pages=pages,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _publish_retriage(
        self,
        incident_id: str,
        incident_number: str,
        reason: str,
        current_state: str,
    ) -> None:
        from app.orchestrator.bus import event_bus
        from app.orchestrator.events import ReTriageRequestedEvent
        await event_bus.publish(ReTriageRequestedEvent(
            incident_id=incident_id,
            incident_number=incident_number,
            reason=reason,
            current_state=current_state,
        ))
        logger.info(
            "[IncidentService] ReTriageRequestedEvent published for %s (reason=%s)",
            incident_number, reason,
        )

    async def _publish_state_change(
        self,
        incident_id: str,
        incident_number: str,
        old_state: str,
        new_state: str,
        changed_by: str,
        triggering_work_note_id: str | None = None,
        triggering_work_note_source: str | None = None,
    ) -> None:
        from app.orchestrator.bus import event_bus
        from app.orchestrator.events import IncidentStateChangedEvent
        await event_bus.publish(IncidentStateChangedEvent(
            incident_id=incident_id,
            incident_number=incident_number,
            previous_state=old_state,
            current_state=new_state,
            changed_by=changed_by,
            triggering_work_note_id=triggering_work_note_id,
            triggering_work_note_source=triggering_work_note_source,
        ))
