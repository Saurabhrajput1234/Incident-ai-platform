"""
PendingCycle SQLAlchemy model.
Tracks the lifecycle of reminder cycles for incidents in pending / on_hold state.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.postgres.base import Base


class PendingCycleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# Postgres enum mapped to existing pending_cycle_status type
pending_cycle_status_enum = PGEnum(
    PendingCycleStatus,
    name="pending_cycle_status",
    create_type=False,
)


class PendingCycle(Base):
    __tablename__ = "pending_cycles"

    __table_args__ = (
        Index("ix_pending_cycles_incident_id", "incident_id"),
        Index("ix_pending_cycles_status", "status"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    incident_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    incident_number: Mapped[str] = mapped_column(String(20), nullable=False)

    status: Mapped[PendingCycleStatus] = mapped_column(
        pending_cycle_status_enum,
        default=PendingCycleStatus.ACTIVE,
        nullable=False,
    )

    reminder_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_reminders: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)

    next_reminder_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

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
