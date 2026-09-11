"""
PendingCycle SQLAlchemy model.

Represents a first-class lifecycle entity that tracks an ACTIVE -> PENDING
reminder sequence independently from the Incident entity.

An incident may have multiple sequential PendingCycles over its lifetime,
but at most ONE PendingCycle may be ACTIVE at any given time.
"""
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.postgres.base import Base
from app.modules.pending_cycles.enums import PendingCycleStatus

if TYPE_CHECKING:
    from app.modules.incidents.model import Incident


class PendingCycle(Base):
    """
    PendingCycle database model.

    Tracks reminders sent to callers while a ticket is on hold / pending.
    """
    __tablename__ = "pending_cycles"

    __table_args__ = (
        Index("ix_pending_cycles_incident_id", "incident_id"),
        Index("ix_pending_cycles_status", "status"),
        Index(
            "uq_active_cycle_per_incident",
            "incident_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    # Primary identifier
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Foreign key to Incident
    incident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )

    # Lifecycle status: ACTIVE, COMPLETED, CANCELLED
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PendingCycleStatus.ACTIVE.value
    )

    # Reminder counters
    reminder_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    max_reminders: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3
    )

    # Reminder configuration & scheduling
    reminder_template: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    next_reminder_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationship to parent Incident
    incident: Mapped["Incident"] = relationship(
        "Incident",
        lazy="select",
    )
