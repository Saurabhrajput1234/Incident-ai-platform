"""
WorkNote Service — centralized work note creation for all agents and users.

All agents, services, and API handlers must use this service to add work notes.
Never directly modify Incident.work_notes — use add_note() instead.

Auto-Activate Behaviour
-----------------------
When add_note() is called with auto_activate=True (the default), the incident
is automatically moved to IN_PROGRESS ("in_progress") if its current state is
not already "in_progress".  This supports the business rule:

    "Any work note added by a user or engineer resumes the incident."

Callers that perform an intentional state transition before writing their
work note (e.g. agents that set ON_HOLD then record an acknowledgement note)
MUST pass auto_activate=False to prevent the note from undoing the
intentional state change.

State Change and Resolution Alert Trigger
------------------------------------------
The actual state transition is performed by
IncidentService.activate_incident_from_work_note(), imported locally at
call-time inside _maybe_activate_incident().  IncidentService owns all
incident state transitions, including the Resolution Alert Agent trigger.

This means:
  - WorkNoteService has NO knowledge of ResolutionService.
  - The Resolution Alert Agent fires only when an actual ON_HOLD → ACTIVE
    state transition is persisted — regardless of whether that transition
    was triggered by a work note, a manual engineer update, or an agent.
  - The local import (inside _maybe_activate_incident) avoids the circular
    module-level dependency:
        IncidentService → WorkNoteService  (module level)
        WorkNoteService → IncidentService  (call-time only — safe)

To keep the audit trail clear, IncidentService.activate_incident_from_work_note()
writes a STATE_CHANGE work note when a transition occurs.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.work_notes.repository import WorkNoteRepository
from app.modules.work_notes.schemas import WorkNoteCreate, WorkNoteResponse
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType
from app.modules.work_notes.model import IncidentWorkNote

logger = logging.getLogger(__name__)

# The target state written during auto-activation.
# Matches IncidentState.IN_PROGRESS = "in_progress".
_AUTO_ACTIVATE_STATE = "in_progress"

# States that already represent "active/resumed" — no auto-activation needed.
_ALREADY_ACTIVE_STATES = {"in_progress", "resolved", "closed", "cancelled"}


class WorkNoteService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = WorkNoteRepository(db)

    async def add_note(
        self,
        incident_id: str,
        message: str,
        source_type: WorkNoteSourceType,
        source_name: str,
        source_id: str | None = None,
        action_type: WorkNoteActionType | None = None,
        auto_activate: bool = True,
    ) -> WorkNoteResponse:
        """
        Create a structured work note.

        Parameters
        ----------
        incident_id   : UUID of the incident.
        message       : The work note body.
        source_type   : Who created the note (ENGINEER, USER, TRIAGE_AGENT, etc.).
        source_name   : Human-readable name of the source.
        source_id     : Optional opaque identifier for the originating entity.
        action_type   : What operation this note records.
        auto_activate : When True (default), automatically transitions the
                        incident to IN_PROGRESS if it is not already in an
                        active/terminal state via IncidentService.
                        Pass False for agent work notes that accompany an
                        intentional state transition so the note does not
                        undo the intended state.
        """
        # --- Step 1: Persist the work note FIRST ---
        # The note must exist in the DB before activation fires the Resolution
        # Agent, so that ResolutionService can fetch it by ID.
        payload = WorkNoteCreate(
            incident_id=incident_id,
            message=message,
            source_type=source_type,
            source_name=source_name,
            source_id=source_id,
            action_type=action_type,
        )
        note = await self.repo.create(payload.model_dump())
        logger.info(
            "[WorkNote] id=%s incident=%s source=%s/%s action=%s",
            note.id, incident_id, source_type, source_name, action_type,
        )

        # --- Step 2: Optional auto-activate via IncidentService ---
        # Passes the triggering note ID and source so ResolutionService can:
        #   (a) load the exact note by ID (not the SYSTEM audit note that follows)
        #   (b) gate eligibility on source type BEFORE running the LLM
        # WorkNoteService itself has NO resolution trigger logic.
        if auto_activate:
            await self._maybe_activate_incident(
                incident_id=incident_id,
                triggered_by=source_name,
                triggering_work_note_id=note.id,
                triggering_work_note_source=(
                    source_type.value if hasattr(source_type, "value") else str(source_type)
                ),
            )

        return WorkNoteResponse.model_validate(note)

    # ------------------------------------------------------------------
    # Private: auto-activate helper
    # ------------------------------------------------------------------

    async def _maybe_activate_incident(
        self,
        incident_id: str,
        triggered_by: str,
        triggering_work_note_id: str | None = None,
        triggering_work_note_source: str | None = None,
    ) -> None:
        """
        Delegate the state transition to IncidentService.activate_incident_from_work_note().

        Parameters
        ----------
        triggering_work_note_id
            ID of the work note that triggered this activation (already persisted).
        triggering_work_note_source
            WorkNoteSourceType value of the triggering note (e.g. "USER",
            "PENDING_AGENT").  Passed through to ResolutionService so it can
            gate eligibility on source type BEFORE running the LLM.
        """
        from app.modules.incidents.service import IncidentService  # local import — safe

        incident_svc = IncidentService(self.db)
        await incident_svc.activate_incident_from_work_note(
            incident_id=incident_id,
            triggered_by=triggered_by,
            triggering_work_note_id=triggering_work_note_id,
            triggering_work_note_source=triggering_work_note_source,
        )

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    async def get_note_by_id(self, note_id: str) -> WorkNoteResponse | None:
        """Fetch a single work note by its primary-key ID."""
        note = await self.repo.get_by_id(note_id)
        return WorkNoteResponse.model_validate(note) if note else None

    async def get_notes(
        self,
        incident_id: str,
        limit: int = 100,
    ) -> list[WorkNoteResponse]:
        notes = await self.repo.get_by_incident(incident_id, limit=limit)
        return [WorkNoteResponse.model_validate(n) for n in notes]

    async def get_latest(self, incident_id: str) -> WorkNoteResponse | None:
        note = await self.repo.get_latest_by_incident(incident_id)
        return WorkNoteResponse.model_validate(note) if note else None

    async def get_by_source_type(
        self,
        incident_id: str,
        source_type: WorkNoteSourceType,
    ) -> list[WorkNoteResponse]:
        notes = await self.repo.get_by_source_type(incident_id, source_type.value)
        return [WorkNoteResponse.model_validate(n) for n in notes]

    async def get_latest_by_source_type(
        self,
        incident_id: str,
        source_type: WorkNoteSourceType,
    ) -> WorkNoteResponse | None:
        notes = await self.repo.get_by_source_type(incident_id, source_type.value)
        return WorkNoteResponse.model_validate(notes[0]) if notes else None

    def build_legacy_text(self, notes: list[IncidentWorkNote]) -> str:
        """
        Render structured notes back to the flat text format used by legacy incident.work_notes.
        Keeps the incident detail page working without frontend changes.
        """
        sep = "─" * 40
        blocks = []
        for n in notes:
            header = f"[{n.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}] [{n.source_type}] {n.source_name}"
            if n.action_type:
                header += f" | {n.action_type}"
            blocks.append(f"{header}\n{n.message}")
        return f"\n\n{sep}\n\n".join(blocks) if blocks else ""
