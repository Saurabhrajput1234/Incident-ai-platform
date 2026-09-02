"""
WorkNote Service — centralized work note creation for all agents and users.

All agents, services, and API handlers must use this service to add work notes.
Never directly modify Incident.work_notes — use add_note() instead.
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.work_notes.repository import WorkNoteRepository
from app.modules.work_notes.schemas import WorkNoteCreate, WorkNoteResponse
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType
from app.modules.work_notes.model import IncidentWorkNote

logger = logging.getLogger(__name__)


class WorkNoteService:

    def __init__(self, db: AsyncSession):
        self.repo = WorkNoteRepository(db)

    async def add_note(
        self,
        incident_id: str,
        message: str,
        source_type: WorkNoteSourceType,
        source_name: str,
        source_id: str | None = None,
        action_type: WorkNoteActionType | None = None,
    ) -> WorkNoteResponse:
        """Create a structured work note. Use this from all agents and services."""
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
            f"[WorkNote] {incident_id} | {source_type} | {source_name} | {action_type}"
        )
        return WorkNoteResponse.model_validate(note)

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
