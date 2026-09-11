"""
WorkNote Repository — all DB operations for incident_work_notes.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.work_notes.model import IncidentWorkNote


class WorkNoteRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> IncidentWorkNote:
        note = IncidentWorkNote(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            **data,
        )
        self.db.add(note)
        await self.db.commit()
        await self.db.refresh(note)
        return note

    async def get_by_incident(
        self,
        incident_id: str,
        limit: int = 100,
    ) -> list[IncidentWorkNote]:
        result = await self.db.execute(
            select(IncidentWorkNote)
            .where(IncidentWorkNote.incident_id == incident_id)
            .order_by(IncidentWorkNote.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_id(self, note_id: str) -> IncidentWorkNote | None:
        """Fetch a single work note by primary key. Returns None if not found."""
        result = await self.db.execute(
            select(IncidentWorkNote).where(IncidentWorkNote.id == note_id)
        )
        return result.scalar_one_or_none()

    async def get_latest_by_incident(self, incident_id: str) -> IncidentWorkNote | None:
        result = await self.db.execute(
            select(IncidentWorkNote)
            .where(IncidentWorkNote.incident_id == incident_id)
            .order_by(IncidentWorkNote.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_source_type(
        self,
        incident_id: str,
        source_type: str,
    ) -> list[IncidentWorkNote]:
        result = await self.db.execute(
            select(IncidentWorkNote)
            .where(
                IncidentWorkNote.incident_id == incident_id,
                IncidentWorkNote.source_type == source_type,
            )
            .order_by(IncidentWorkNote.created_at.desc())
        )
        return result.scalars().all()
