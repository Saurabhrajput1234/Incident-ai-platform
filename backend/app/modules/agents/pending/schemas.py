"""
Pydantic schemas for the Pending Agent domain.
"""
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from app.modules.agents.pending.models.pending_cycle import PendingCycleStatus


class PendingWorkNoteAnalysis(BaseModel):
    is_caller_action_required: bool
    reasoning: str
    confidence: float = 1.0


class PendingCycleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    incident_id: str
    incident_number: str
    status: PendingCycleStatus
    reminder_count: int
    max_reminders: int
    source_type: str
    next_reminder_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PendingResult(BaseModel):
    incident_id: str
    incident_number: str
    caller: str | None = None
    assigned_to: str | None = None
    assignment_group: str | None = None
    cycle_id: str | None = None
    cycle_status: PendingCycleStatus | None = None
    reminder_count: int = 0
    max_reminders: int = 3
    is_caller_action_required: bool = False
    action_taken: str  # "CYCLE_PRESERVED", "CYCLE_STARTED", "CYCLE_COMPLETED", "DISCARDED"
    email_sent: bool = False
    delivery_status: str | None = None
    work_notes_added: str | None = None
    next_reminder_at: datetime | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
