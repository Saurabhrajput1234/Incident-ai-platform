"""
AI Context Builder.

Collects data from Incident Service and Shift Roster Service,
then assembles a single AIContext object for the Triage Agent.

Rules:
  - Never performs AI reasoning
  - Never updates the database
  - Never contains business rules
  - Only aggregates data from existing services
"""
import logging
from datetime import date, datetime, timezone

from app.modules.context.schemas import AIContext, IncidentContext, EngineerContext
from app.modules.context.exceptions import ContextBuildError
from app.modules.incidents.schemas import IncidentResponse
from app.modules.shift_roster.schemas import EngineerAvailability
from app.modules.shift_roster.enums import WORKING_SHIFTS
from app.modules.shift_roster.shift_time_checker import is_shift_active_now

logger = logging.getLogger(__name__)


def build_engineer_context(eng: EngineerAvailability) -> EngineerContext:
    """Convert an EngineerAvailability record into an EngineerContext."""
    is_available = eng.shift_code in WORKING_SHIFTS if eng.shift_code else False
    is_active = is_shift_active_now(eng.shift_code) if is_available else False
    return EngineerContext(
        engineer_id=eng.engineer_id,
        name=eng.assigned_to,
        email=eng.email,
        assignment_group=eng.assignment_group,
        level=eng.level,
        default_shift=eng.default_shift,
        current_shift=eng.shift_code,
        is_available=is_available,
        is_shift_active=is_active,
        roster_date=eng.roster_date,
    )


def build_incident_context(incident: IncidentResponse) -> IncidentContext:
    """Convert an IncidentResponse into an IncidentContext."""
    return IncidentContext(
        incident_id=incident.id,
        incident_number=incident.incident_number,
        short_description=incident.short_description,
        description=incident.description,
        priority=incident.priority,
        state=incident.state,
        category=incident.category,
        subcategory=incident.subcategory,
        assignment_group=incident.assignment_group,
        assigned_to=incident.assigned_to,
        caller=incident.caller,
        created_at=incident.created_at,
    )


def build_context(
    incident: IncidentResponse,
    engineers: list[EngineerAvailability],
    context_date: date,
) -> AIContext:
    """
    Assemble a complete AIContext from incident and engineer data.
    Raises ContextBuildError if required data is missing.
    """
    if not incident:
        raise ContextBuildError("Incident is required to build context")

    logger.info(
        f"Building AI context for incident {incident.incident_number} "
        f"with {len(engineers)} engineers on {context_date}"
    )

    return AIContext(
        incident=build_incident_context(incident),
        engineers=[build_engineer_context(e) for e in engineers],
        context_date=context_date,
        created_at=datetime.now(timezone.utc),
        context_version="1.0",
    )
