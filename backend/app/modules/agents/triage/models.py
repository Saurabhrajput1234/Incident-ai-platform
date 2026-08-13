"""
Database models for the Assignment Service.

assignment_group_rr_state  — persists round-robin position per group
assignment_history         — records every engineer assignment
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.postgres.base import Base


class AssignmentGroupRRState(Base):
    """
    Persists the round-robin index per assignment group.
    Used by the Assignment Service to ensure deterministic rotation.
    """
    __tablename__ = "assignment_group_rr_state"

    assignment_group: Mapped[str] = mapped_column(String(200), primary_key=True)
    last_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AssignmentHistory(Base):
    """
    Records every engineer assignment made by the Assignment Service.
    Full audit trail — one row per assignment.
    """
    __tablename__ = "assignment_history"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    incident_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    incident_number: Mapped[str] = mapped_column(String(20), nullable=False)
    assignment_group: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    engineer_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    engineer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    engineer_email: Mapped[str] = mapped_column(String(150), nullable=False)
    shift_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    roster_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    llm_resolved_group: Mapped[bool] = mapped_column(default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
