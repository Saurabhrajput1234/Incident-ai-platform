"""
Pydantic schemas for the PendingCycle module.
"""
from datetime import datetime
from pydantic import BaseModel, Field
from app.modules.pending_cycles.enums import PendingCycleStatus


class PendingCycleCreate(BaseModel):
    """Schema for initializing a new pending reminder cycle."""
    incident_id: str = Field(..., min_length=1, description="Incident ID (UUID or INC number)")
    max_reminders: int = Field(default=3, ge=1, description="Maximum reminders to send before cycle completion/escalation")
    reminder_template: str | None = Field(default=None, max_length=100, description="Template identifier for reminder emails")
    next_reminder_at: datetime | None = Field(default=None, description="Scheduled time for next reminder")

    model_config = {"use_enum_values": True}


class PendingCycleUpdate(BaseModel):
    """Schema for partial update of a pending cycle."""
    status: PendingCycleStatus | None = None
    reminder_count: int | None = Field(default=None, ge=0)
    max_reminders: int | None = Field(default=None, ge=1)
    reminder_template: str | None = Field(default=None, max_length=100)
    next_reminder_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None

    model_config = {"use_enum_values": True}


class PendingCycleResponse(BaseModel):
    """Schema for pending cycle API/service response."""
    id: str
    incident_id: str
    status: str
    reminder_count: int
    max_reminders: int
    reminder_template: str | None = None
    next_reminder_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None

    model_config = {"from_attributes": True}


class PendingCycleListResponse(BaseModel):
    """Schema for list of pending cycles."""
    items: list[PendingCycleResponse]
    total: int
