"""
Domain events for the orchestration layer.

Only the events actually needed by the current four agents.
No ServiceNow, no email, no external integrations.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class IncidentCreatedEvent:
    """
    Published by IncidentService.create_incident() after the row is persisted.
    Triggers: TriageHandler
    """
    incident_id: str
    incident_number: str
    assignment_group: str | None
    priority: str
    state: str
    created_at: datetime = field(default_factory=_now)


@dataclass
class IncidentStateChangedEvent:
    """
    Published by IncidentService whenever an incident state transition is persisted.
    Triggers: AcknowledgementHandler, PendingHandler, ResolutionHandler
    """
    incident_id: str
    incident_number: str
    previous_state: str
    current_state: str
    # Who triggered the change: "system", "engineer", or an agent name
    changed_by: str
    # The work note that caused the transition (if work-note driven)
    triggering_work_note_id: str | None = None
    triggering_work_note_source: str | None = None
    changed_at: datetime = field(default_factory=_now)


@dataclass
class WorkNoteAddedEvent:
    """
    Published by WorkNoteService.add_note() after the note is persisted.
    Triggers: ResolutionHandler (when source_type=USER and incident is on_hold)

    This event carries enough context for handlers to filter without a DB lookup:
    - source_type lets the ResolutionHandler gate on USER only
    - incident_state lets the ResolutionHandler gate on on_hold only
    - work_note_id is the primary key of the persisted note
    """
    incident_id: str
    incident_number: str
    work_note_id: str
    source_type: str          # WorkNoteSourceType value: USER, ENGINEER, TRIAGE_AGENT, etc.
    source_name: str
    action_type: str          # WorkNoteActionType value
    incident_state: str       # current incident state at the time the note was added
    added_at: datetime = field(default_factory=_now)
