"""
Pydantic schemas for the Incident module.

Schemas are separated by use case to keep each one minimal
and avoid exposing internal fields to API consumers.

  IncidentCreate   — inbound payload for POST
  IncidentUpdate   — inbound payload for PUT (all fields optional)
  IncidentResponse — outbound response (single incident)
  IncidentListResponse — outbound response (paginated list)
"""
from datetime import datetime
from pydantic import BaseModel, Field
from app.modules.incidents.enums import (
    IncidentPriority, IncidentState, IncidentCategory,
    IncidentImpact, IncidentUrgency, IncidentEnvironment, IncidentSource
)


class IncidentCreate(BaseModel):
    """
    Schema for creating a new incident.
    Only required field is short_description.
    All other fields default to sensible values.
    """
    short_description: str = Field(..., min_length=5, max_length=255)
    description: str | None = None

    # Classification — defaults to MEDIUM/NEW if not provided
    priority: IncidentPriority = IncidentPriority.MEDIUM
    state: IncidentState = IncidentState.NEW
    category: IncidentCategory | None = None
    subcategory: str | None = Field(None, max_length=100)

    # Severity calculation inputs
    impact: IncidentImpact = IncidentImpact.MEDIUM
    urgency: IncidentUrgency = IncidentUrgency.MEDIUM

    # Assignment
    assignment_group: str | None = Field(None, max_length=100)
    assigned_to: str | None = Field(None, max_length=100)
    caller: str | None = Field(None, max_length=100)

    # CMDB references
    configuration_item: str | None = Field(None, max_length=100)
    business_service: str | None = Field(None, max_length=100)

    # Context
    environment: IncidentEnvironment | None = None
    source: IncidentSource = IncidentSource.MANUAL

    # Notes
    work_notes: str | None = None
    comments: str | None = None

    # Serialize enum fields as their string values
    model_config = {"use_enum_values": True}


class IncidentUpdate(BaseModel):
    """
    Schema for partial update of an incident.
    All fields are optional — only provided fields will be updated.
    """
    short_description: str | None = Field(None, min_length=5, max_length=255)
    description: str | None = None
    priority: IncidentPriority | None = None
    state: IncidentState | None = None
    category: IncidentCategory | None = None
    subcategory: str | None = Field(None, max_length=100)
    impact: IncidentImpact | None = None
    urgency: IncidentUrgency | None = None
    assignment_group: str | None = Field(None, max_length=100)
    assigned_to: str | None = Field(None, max_length=100)
    caller: str | None = Field(None, max_length=100)
    configuration_item: str | None = Field(None, max_length=100)
    business_service: str | None = Field(None, max_length=100)
    environment: IncidentEnvironment | None = None
    source: IncidentSource | None = None
    work_notes: str | None = None
    comments: str | None = None

    model_config = {"use_enum_values": True}


class IncidentResponse(BaseModel):
    """
    Schema for incident API response.
    
    Returns all public fields. Internal database metadata
    (like raw FK ids) is not exposed here.
    from_attributes=True allows building from SQLAlchemy model instances.
    """
    id: str
    incident_number: str
    short_description: str
    description: str | None
    priority: str
    state: str
    category: str | None
    subcategory: str | None
    impact: str
    urgency: str
    assignment_group: str | None
    assigned_to: str | None
    caller: str | None
    configuration_item: str | None
    business_service: str | None
    environment: str | None
    source: str
    work_notes: str | None
    comments: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IncidentListResponse(BaseModel):
    """
    Schema for paginated list of incidents.
    Wraps a list of IncidentResponse with pagination metadata.
    """
    items: list[IncidentResponse]
    total: int       # total matching records in DB
    page: int        # current page number
    page_size: int   # records per page
    pages: int       # total number of pages
