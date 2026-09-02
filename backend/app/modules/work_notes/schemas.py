"""
Pydantic schemas for IncidentWorkNote.
"""
from datetime import datetime
from pydantic import BaseModel, Field
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType


class WorkNoteCreate(BaseModel):
    """Input for creating a work note."""
    incident_id: str
    message: str = Field(..., min_length=1)
    source_type: WorkNoteSourceType
    source_name: str = Field(..., min_length=1, max_length=200)
    source_id: str | None = None
    action_type: WorkNoteActionType | None = None

    model_config = {"use_enum_values": True}


class WorkNoteResponse(BaseModel):
    """API response for a single work note."""
    id: str
    incident_id: str
    message: str
    source_type: str
    source_name: str
    source_id: str | None
    action_type: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
