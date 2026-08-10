"""
Context Service.

Orchestrates the Context Builder by fetching data
from Incident Service and Shift Roster Service,
then calling the builder to produce the AIContext.
"""
import logging
from datetime import date, datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.context.builder import build_context
from app.modules.context.schemas import AIContext
from app.modules.context.exceptions import ContextBuildError
from app.modules.incidents.service import IncidentService
from app.modules.shift_roster.service import ShiftRosterService

logger = logging.getLogger(__name__)


class ContextService:
    """
    Builds AI context by aggregating data from business modules.
    No AI logic here — only data collection and assembly.
    """

    def __init__(self, db: AsyncSession):
        self.incident_service = IncidentService(db)
        self.roster_service = ShiftRosterService(db)

    async def build_for_incident(
        self,
        incident_id: str,
        context_date: date | None = None,
    ) -> AIContext:
        """
        Build a complete AIContext for a given incident.

        Steps:
          1. Fetch incident from Incident Service
          2. Fetch available engineers from Shift Roster Service
          3. Pass both to the Context Builder
        """
        if context_date is None:
            context_date = datetime.now(timezone.utc).date()

        # Step 1: Get incident
        incident = await self.incident_service.get_incident(incident_id)

        if not incident.assignment_group:
            raise ContextBuildError(
                f"Incident {incident.incident_number} has no assignment group — cannot build context"
            )

        # Step 2: Get engineers for this assignment group on the context date
        engineers = await self.roster_service.get_available_engineers(
            roster_date=context_date,
            assignment_group=incident.assignment_group,
        )

        logger.info(
            f"Context for {incident.incident_number}: "
            f"{len(engineers)} engineers in '{incident.assignment_group}' on {context_date}"
        )

        # Step 3: Build and return the context object
        return build_context(
            incident=incident,
            engineers=engineers,
            context_date=context_date,
        )
