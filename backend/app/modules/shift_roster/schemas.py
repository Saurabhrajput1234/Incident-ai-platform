"""Pydantic schemas for the Shift Roster module."""
from datetime import datetime, date
from pydantic import BaseModel, EmailStr
from app.modules.shift_roster.enums import ShiftCode, EngineerLevel, EngineerStatus, UploadStatus


# --- Upload ---

class UploadSummary(BaseModel):
    """Returned after every Excel/CSV upload."""
    upload_id: str
    file_name: str
    roster_start_date: date
    roster_end_date: date
    total_records: int
    imported_records: int
    failed_records: int
    upload_status: str
    errors: list[str] = []

    model_config = {"from_attributes": True}


# --- Engineer ---

class EngineerResponse(BaseModel):
    """Public engineer record."""
    id: str
    assignment_group: str
    assigned_to: str
    email: str
    default_shift: str | None
    level: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EngineerUpdate(BaseModel):
    """Manually update an engineer's master record."""
    assignment_group: str | None = None
    default_shift: ShiftCode | None = None
    level: EngineerLevel | None = None
    status: EngineerStatus | None = None

    model_config = {"use_enum_values": True}


# --- Shift Roster ---

class ShiftRosterResponse(BaseModel):
    """Single daily roster record."""
    id: str
    engineer_id: str
    upload_id: str
    roster_date: date
    shift_code: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShiftRosterUpdate(BaseModel):
    """Update a single daily roster record (triggers history entry)."""
    shift_code: ShiftCode
    changed_by: str | None = None
    reason: str | None = None

    model_config = {"use_enum_values": True}


# --- Availability / Triage Agent queries ---

class EngineerAvailability(BaseModel):
    """Engineer with their shift on a specific date — used by Triage Agent and search."""
    engineer_id: str
    assigned_to: str
    email: str
    assignment_group: str
    level: str | None
    default_shift: str | None
    roster_date: date | None = None
    shift_code: str | None = None


# --- History ---

class RosterHistoryResponse(BaseModel):
    """Audit trail entry."""
    id: str
    roster_id: str
    engineer_id: str
    roster_date: date
    previous_shift: str
    new_shift: str
    changed_by: str | None
    changed_at: datetime
    reason: str | None

    model_config = {"from_attributes": True}
