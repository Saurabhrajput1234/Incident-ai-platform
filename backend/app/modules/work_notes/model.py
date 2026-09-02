"""
IncidentWorkNote SQLAlchemy model.

One-to-many: one Incident → many IncidentWorkNotes.
Replaces the flat work_notes TEXT field for structured, queryable history.
"""
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.postgres.base import Base

if TYPE_CHECKING:
    from app.modules.incidents.model import Incident


class IncidentWorkNote(Base):
    __tablename__ = "incident_work_notes"

    __table_args__ = (
        Index("ix_work_notes_incident_id", "incident_id"),
        Index("ix_work_notes_source_type", "source_type"),
        Index("ix_work_notes_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    incident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )

    # The note content
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Who/what created this note
    source_type: Mapped[str] = mapped_column(
        String(40), nullable=False
    )  # WorkNoteSourceType value
    source_name: Mapped[str] = mapped_column(
        String(200), nullable=False
    )  # e.g. "TriageAgent", "Priya Sharma", "System"
    source_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # engineer_id, user_id, agent identifier — optional

    # What operation was performed
    action_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # WorkNoteActionType value

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Back-reference to the parent incident
    incident: Mapped["Incident"] = relationship(
        "Incident",
        back_populates="work_note_entries",
    )
