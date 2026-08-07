"""
Normalized 4-table database design for Shift Roster.

Tables:
  shift_roster_uploads  — metadata for each uploaded file
  engineers             — master engineer records (upsert on upload)
  shift_roster          — one record per engineer per day (normalized daily schedule)
  shift_roster_history  — audit trail for any post-upload roster changes
"""
import uuid
from datetime import datetime, date, timezone
from sqlalchemy import String, DateTime, Date, ForeignKey, Text, Enum as SAEnum, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.postgres.base import Base
from app.modules.shift_roster.enums import ShiftCode, EngineerLevel, EngineerStatus, UploadStatus


# ---------------------------------------------------------------------------
# Table 1: shift_roster_uploads
# Stores metadata for every uploaded Excel/CSV file
# ---------------------------------------------------------------------------
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
    upload_status: Mapped[str] = mapped_column(
        SAEnum(UploadStatus), nullable=False, default=UploadStatus.SUCCESS
    )

    # Relationships
    roster_entries: Mapped[list["ShiftRoster"]] = relationship("ShiftRoster", back_populates="upload")


# ---------------------------------------------------------------------------
# Table 2: engineers
# Master engineer table — upserted on every upload
# Email is unique — used as the deduplication key
# ---------------------------------------------------------------------------
class Engineer(Base):
    __tablename__ = "engineers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # From Excel columns
    assignment_group: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    assigned_to: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(150), nullable=False, unique=True, index=True)
    default_shift: Mapped[str | None] = mapped_column(String(20), nullable=True)
    level: Mapped[str | None] = mapped_column(SAEnum(EngineerLevel), nullable=True, index=True)

    # Status — set to inactive when engineer is removed; historical data is preserved
    status: Mapped[str] = mapped_column(
        SAEnum(EngineerStatus), nullable=False, default=EngineerStatus.ACTIVE, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    roster_entries: Mapped[list["ShiftRoster"]] = relationship("ShiftRoster", back_populates="engineer")
    history_entries: Mapped[list["ShiftRosterHistory"]] = relationship("ShiftRosterHistory", back_populates="engineer")


# ---------------------------------------------------------------------------
# Table 3: shift_roster
# One record per engineer per day — normalized from Day1..Day31 columns
# This is the core query table for the Triage Agent
# ---------------------------------------------------------------------------
class ShiftRoster(Base):
    __tablename__ = "shift_roster"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # FK to upload — links each daily record back to its source upload
    upload_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shift_roster_uploads.id"), nullable=False, index=True
    )

    # FK to engineer master
    engineer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("engineers.id"), nullable=False, index=True
    )

    # The specific date and shift for this record
    roster_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    shift_code: Mapped[str] = mapped_column(SAEnum(ShiftCode), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    upload: Mapped["ShiftRosterUpload"] = relationship("ShiftRosterUpload", back_populates="roster_entries")
    engineer: Mapped["Engineer"] = relationship("Engineer", back_populates="roster_entries")
    history: Mapped[list["ShiftRosterHistory"]] = relationship("ShiftRosterHistory", back_populates="roster_entry")


# ---------------------------------------------------------------------------
# Table 4: shift_roster_history
# Audit trail — records every modification made after original upload
# ---------------------------------------------------------------------------
class ShiftRosterHistory(Base):
    __tablename__ = "shift_roster_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # FK to the roster record that was changed
    roster_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shift_roster.id"), nullable=False, index=True
    )

    # FK to engineer (denormalized for easy audit queries without join)
    engineer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("engineers.id"), nullable=False, index=True
    )

    roster_date: Mapped[date] = mapped_column(Date, nullable=False)
    previous_shift: Mapped[str] = mapped_column(SAEnum(ShiftCode), nullable=False)
    new_shift: Mapped[str] = mapped_column(SAEnum(ShiftCode), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    roster_entry: Mapped["ShiftRoster"] = relationship("ShiftRoster", back_populates="history")
    engineer: Mapped["Engineer"] = relationship("Engineer", back_populates="history_entries")
