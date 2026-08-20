"""
Normalized 4-table database design for Shift Roster.

All enum-like fields use String columns to avoid PostgreSQL enum type
migration issues. Values are validated at the Pydantic/service layer.
"""
import uuid
from datetime import datetime, date, timezone
from sqlalchemy import String, DateTime, Date, ForeignKey, Text, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.postgres.base import Base


class ShiftRosterUpload(Base):
    __tablename__ = "shift_roster_uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    roster_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    roster_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    imported_records: Mapped[int] = mapped_column(Integer, default=0)
    failed_records: Mapped[int] = mapped_column(Integer, default=0)
    # "success" | "partial" | "failed"
    upload_status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")

    roster_entries: Mapped[list["ShiftRoster"]] = relationship("ShiftRoster", back_populates="upload")


class Engineer(Base):
    __tablename__ = "engineers"
    __table_args__ = (
        UniqueConstraint("email", "assignment_group", name="uq_engineer_email_group"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assignment_group: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    assigned_to: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(150), nullable=False, index=True)  # no longer unique alone
    default_shift: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # "L1" | "L2" | "L3"
    level: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    # "active" | "inactive"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    roster_entries: Mapped[list["ShiftRoster"]] = relationship("ShiftRoster", back_populates="engineer")
    history_entries: Mapped[list["ShiftRosterHistory"]] = relationship("ShiftRosterHistory", back_populates="engineer")


class ShiftRoster(Base):
    __tablename__ = "shift_roster"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id: Mapped[str] = mapped_column(String(36), ForeignKey("shift_roster_uploads.id"), nullable=False, index=True)
    engineer_id: Mapped[str] = mapped_column(String(36), ForeignKey("engineers.id"), nullable=False, index=True)
    roster_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # "Shift1" | "Shift2" | "Shift3" | "WO" | "PL" | "CH" | "RH"
    shift_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    upload: Mapped["ShiftRosterUpload"] = relationship("ShiftRosterUpload", back_populates="roster_entries")
    engineer: Mapped["Engineer"] = relationship("Engineer", back_populates="roster_entries")
    history: Mapped[list["ShiftRosterHistory"]] = relationship("ShiftRosterHistory", back_populates="roster_entry")


class ShiftRosterHistory(Base):
    __tablename__ = "shift_roster_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    roster_id: Mapped[str] = mapped_column(String(36), ForeignKey("shift_roster.id"), nullable=False, index=True)
    engineer_id: Mapped[str] = mapped_column(String(36), ForeignKey("engineers.id"), nullable=False, index=True)
    roster_date: Mapped[date] = mapped_column(Date, nullable=False)
    previous_shift: Mapped[str] = mapped_column(String(20), nullable=False)
    new_shift: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    roster_entry: Mapped["ShiftRoster"] = relationship("ShiftRoster", back_populates="history")
    engineer: Mapped["Engineer"] = relationship("Engineer", back_populates="history_entries")
