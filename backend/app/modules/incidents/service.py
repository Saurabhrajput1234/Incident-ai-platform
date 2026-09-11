"""
Incident Service — business logic layer.

This is the only place business rules and decisions live.
No SQL queries here — all DB access goes through IncidentRepository.
No HTTP concerns here — all HTTP handling stays in the API layer.

Flow: API -> Service -> Repository -> Database

Resolution Alert Agent Trigger
--------------------------------
The Resolution Alert Agent has exactly ONE trigger condition:

    previous_state == "on_hold"  AND  new_state == "in_progress"

This service is the authoritative owner of every incident state transition.
The trigger fires in THREE places, all inside this file:

  1. update_incident()               — engineer/API manual state change
  2. update_incident_internal()      — agent-driven state change (no work note)
  3. activate_incident_from_work_note() — work-note-driven auto-activation
                                          (called by WorkNoteService via local import)

In every case the sequence is:
    1. Capture old_state BEFORE the DB update.
    2. Persist the new state via repo.update().
    3. If old_state == "on_hold" and new_state is an active value:
           call _fire_resolution_agent().

WorkNoteService has NO knowledge of ResolutionService.
ResolutionService is imported locally inside _fire_resolution_agent() to
avoid a circular module-level import (IncidentService → ResolutionService
→ WorkNoteService → IncidentService).
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

# ---------------------------------------------------------------------------
# State constants used by the Resolution trigger
# ---------------------------------------------------------------------------

# The previous state that qualifies a transition for Resolution Agent.
_ON_HOLD_STATE = "on_hold"

# The state that is written by auto-activation (IN_PROGRESS).
_AUTO_ACTIVATE_STATE = "in_progress"

# States that already represent "active/resumed" — no auto-activation needed.
_ALREADY_ACTIVE_STATES = {"in_progress", "resolved", "closed", "cancelled"}

# The contract string ResolutionService expects for "current_state".
# ResolutionService._is_eligible_transition() compares against "active".
_RESOLUTION_CURRENT_STATE = "active"


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

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

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
            auto_activate=False,  # new incident — no auto-activation needed
        )

        return IncidentResponse.model_validate(incident)

    async def get_incident(self, incident_id: str) -> IncidentResponse:
        """
        Fetch a single incident by ID or incident number (INC0000001).
        Raises NotFoundError if the incident does not exist.
        """
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

        pages = -(-total // page_size)

        return IncidentListResponse(
            items=[IncidentResponse.model_validate(i) for i in incidents],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def update_incident(
        self,
        incident_id: str,
        payload: IncidentUpdate,
    ) -> IncidentResponse:
        """
        Update an existing incident (engineer / API path).

        Only fields explicitly provided in the payload are updated.
        Returns the existing record unchanged if no fields provided.
        Raises NotFoundError if the incident does not exist.

        If the update changes the state from ON_HOLD to IN_PROGRESS/ACTIVE,
        the Resolution Alert Agent is automatically triggered after the
        state has been persisted.
        """
        if incident_id.upper().startswith("INC"):
            existing = await self.repo.get_by_number(incident_id.upper())
        else:
            existing = await self.repo.get_by_id(incident_id)

        if not existing:
            logger.warning(f"Update failed — incident not found: {incident_id}")
            raise NotFoundError(f"Incident '{incident_id}' not found")

        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            logger.warning(f"Update called with no fields: {incident_id}")
            return IncidentResponse.model_validate(existing)

        # Capture old state BEFORE the DB write so we can detect the transition.
        old_state: str = str(existing.state.value if hasattr(existing.state, "value") else existing.state)
        new_state: str | None = str(update_data["state"].value if hasattr(update_data.get("state"), "value") else update_data["state"]) if "state" in update_data else None

        incident = await self.repo.update(existing.id, update_data)
        logger.info(f"Incident updated: {incident.incident_number}")

        # Determine action type based on what changed
        if "state" in update_data:
            action = WorkNoteActionType.STATE_CHANGE
            msg = f"State changed to: {new_state}"
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
            auto_activate=False,  # state already set by repo.update above
        )

        # Fire Resolution Agent if this update caused ON_HOLD → ACTIVE.
        if new_state is not None and self._is_on_hold_to_active(old_state, new_state):
            await self._fire_resolution_agent(incident_id=existing.id)

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

    async def update_incident_internal(
        self,
        incident_id: str,
        payload: IncidentUpdate,
    ) -> IncidentResponse:
        """
        Update an incident without writing a work note.
        For use by agent services that write their own work notes.

        If the update changes the state from ON_HOLD to IN_PROGRESS/ACTIVE,
        the Resolution Alert Agent is automatically triggered after the
        state has been persisted.
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

        # Capture old state BEFORE the DB write.
        old_state: str = str(existing.state.value if hasattr(existing.state, "value") else existing.state)
        new_state: str | None = str(update_data["state"].value if hasattr(update_data.get("state"), "value") else update_data["state"]) if "state" in update_data else None

        incident = await self.repo.update(existing.id, update_data)
        logger.info(f"Incident updated (internal): {incident.incident_number}")

        # Fire Resolution Agent if this update caused ON_HOLD → ACTIVE.
        if new_state is not None and self._is_on_hold_to_active(old_state, new_state):
            await self._fire_resolution_agent(incident_id=existing.id)

        return IncidentResponse.model_validate(incident)

    async def activate_incident_from_work_note(
        self,
        incident_id: str,
        triggered_by: str,
        triggering_work_note_id: str | None = None,
        triggering_work_note_source: str | None = None,
    ) -> None:
        """
        Auto-activate an incident when a work note is added (work-note path).

        Called by WorkNoteService._maybe_activate_incident() via a local import.
        The triggering work note is ALREADY persisted in the DB by the time this
        method is called — WorkNoteService.add_note() creates the note first, then
        calls here.

        Parameters
        ----------
        triggering_work_note_id
            ID of the work note that caused this activation.
        triggering_work_note_source
            WorkNoteSourceType value (e.g. "USER", "PENDING_AGENT").
            Passed through to ResolutionService to gate eligibility before
            running the LLM.  Only "USER" source triggers Resolution analysis.
        """
        incident = await self.repo.get_by_id(incident_id)

        if incident is None:
            logger.warning(
                "[IncidentService:AutoActivate] Incident %s not found — "
                "skipping activation.",
                incident_id,
            )
            return

        old_state: str = str(incident.state.value if hasattr(incident.state, "value") else incident.state)

        if old_state in _ALREADY_ACTIVE_STATES:
            # Already active/terminal — no transition needed.
            return

        # Persist the transition.
        await self.repo.update(incident_id, {"state": _AUTO_ACTIVATE_STATE})
        logger.info(
            "[IncidentService:AutoActivate] %s: %s → %s "
            "(triggered by work note from %s, source=%s)",
            incident_id, old_state, _AUTO_ACTIVATE_STATE,
            triggered_by, triggering_work_note_source,
        )

        # Write a STATE_CHANGE audit note directly via the work-note repository
        # (not via add_note()) to prevent recursive activation.
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

        # Fire Resolution Alert Agent if transition was ON_HOLD → ACTIVE.
        if self._is_on_hold_to_active(old_state, _AUTO_ACTIVATE_STATE):
            await self._fire_resolution_agent(
                incident_id=incident_id,
                triggering_work_note_id=triggering_work_note_id,
                triggering_work_note_source=triggering_work_note_source,
            )

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

        pages = -(-total // page_size) if total else 0

        return IncidentListResponse(
            items=[IncidentResponse.model_validate(i) for i in incidents],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_on_hold_to_active(old_state: str, new_state: str) -> bool:
        """
        Return True only when the transition is exactly ON_HOLD → IN_PROGRESS.

        Normalises to lowercase strings to handle enum repr vs. raw string.
        Only fires for:
            previous = "on_hold"
            new      = "in_progress"   (the value _AUTO_ACTIVATE_STATE)

        All other transitions — including PENDING → ACTIVE, NEW → ACTIVE,
        ACTIVE → ON_HOLD, field-only updates — return False.
        """
        prev = old_state.lower().strip()
        curr = new_state.lower().strip()
        return prev == _ON_HOLD_STATE and curr == _AUTO_ACTIVATE_STATE

    async def _fire_resolution_agent(
        self,
        incident_id: str,
        triggering_work_note_id: str | None = None,
        triggering_work_note_source: str | None = None,
    ) -> None:
        """
        Invoke ResolutionService.process() for an ON_HOLD → ACTIVE transition.

        Parameters
        ----------
        triggering_work_note_id
            ID of the work note that caused the activation.
        triggering_work_note_source
            WorkNoteSourceType value of the triggering note.
            ResolutionService uses this to gate eligibility — only "USER"
            source triggers Resolution analysis.  None for manual state changes.
        """
        logger.info(
            "[IncidentService:ResolutionTrigger] ON_HOLD → ACTIVE detected — "
            "triggering Resolution Alert Agent. incident=%s triggering_wn=%s source=%s",
            incident_id,
            triggering_work_note_id,
            triggering_work_note_source,
        )
        try:
            from app.modules.agents.resolution.service import ResolutionService
            from app.modules.agents.resolution.schemas import ResolutionTrigger

            trigger = ResolutionTrigger(
                incident_id=incident_id,
                previous_state=_ON_HOLD_STATE,
                current_state=_RESOLUTION_CURRENT_STATE,  # "active"
                triggering_work_note_id=triggering_work_note_id,
                triggering_work_note_source=triggering_work_note_source,
            )
            resolution_svc = ResolutionService(self.db)
            response = await resolution_svc.process(trigger)

            action = (
                response.result.get("action", "unknown")
                if isinstance(response.result, dict)
                else "unknown"
            )
            logger.info(
                "[IncidentService:ResolutionTrigger] Resolution Agent completed. "
                "incident=%s success=%s action=%s",
                incident_id,
                response.success,
                action,
            )
        except Exception as exc:
            logger.error(
                "[IncidentService:ResolutionTrigger] Resolution Agent failed "
                "for incident %s: %s",
                incident_id,
                exc,
                exc_info=True,
            )
