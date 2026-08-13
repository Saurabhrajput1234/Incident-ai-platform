"""
AI Context schemas.

These are the data structures passed to AI agents.
Agents receive only these objects — never raw DB models or repositories.
"""
from datetime import datetime, date
from pydantic import BaseModel


class IncidentContext(BaseModel):
    """Incident information extracted for AI reasoning."""
    incident_id: str
    incident_number: str
    short_description: str
    description: str | None
    priority: str
    state: str
    category: str | None
    subcategory: str | None
    assignment_group: str | None
    caller: str | None
    created_at: datetime


class EngineerContext(BaseModel):
    """
    Engineer information for AI reasoning.
    Combines master record + current shift availability.
    """
    engineer_id: str
    name: str
    email: str
    assignment_group: str
    level: str | None          # L1 / L2 / L3
    default_shift: str | None
    current_shift: str | None  # shift code on the context date (Shift1/WO/PL etc.)
    is_available: bool         # True if on a working shift
    is_shift_active: bool      # True if the working shift is currently active (time window)
    roster_date: date | None


class AIContext(BaseModel):
    """
    Complete AI context object passed to the Triage Agent.
    Built by the Context Builder from multiple data sources.
    The agent never receives anything other than this object.
    """
    # Incident being triaged
    incident: IncidentContext

    # Engineers available in the assignment group
    engineers: list[EngineerContext]

    # Metadata
    context_date: date          # date used for shift lookup
    created_at: datetime        # when this context was built
    context_version: str = "1.0"
