"""
Pydantic schemas for the Pending Agent domain.
"""
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from app.modules.pending_cycles.enums import PendingCycleStatus


class PendingWorkNoteAnalysis(BaseModel):
    is_caller_action_required: bool
    reasoning: str
    confidence: float = 1.0


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
