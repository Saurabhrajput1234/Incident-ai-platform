"""
Resolution Agent API.

POST /v1/resolution/{incident_id}  — Trigger Resolution Agent for a
                                     PENDING → ACTIVE state transition.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres.session import get_db
from app.modules.agents.base.response import AgentResponse
from app.modules.agents.resolution.schemas import ResolutionTrigger
from app.modules.agents.resolution.service import ResolutionService

router = APIRouter(prefix="/resolution", tags=["resolution"])


def get_resolution_service(db: AsyncSession = Depends(get_db)) -> ResolutionService:
    return ResolutionService(db)


@router.post("/{incident_id}", response_model=AgentResponse, status_code=status.HTTP_200_OK)
async def process_resolution(
    incident_id: str,
    trigger: ResolutionTrigger,
    service: ResolutionService = Depends(get_resolution_service),
):
    """
    Run the Resolution Agent for an incident state transition.

    Expected body:
        {
            "incident_id": "<uuid or INC number>",
            "previous_state": "pending",
            "current_state": "active"
        }

    Flow:
    1.  Validate that the transition is pending → active.
    2.  Confirm latest work note is from USER.
    3.  Cancel active PendingCycle.
    4.  Analyse user response via LLM.
    5.  Notify assigned engineer (Teams) and/or assignment group (Email).
    6.  Auto-resolve incident if provenance and positive resolution confirmed.
    7.  Return structured AgentResponse.
    """
    # Allow incident_id from the path to override the body field for convenience
    if not trigger.incident_id or trigger.incident_id == "string":
        trigger = ResolutionTrigger(
            incident_id=incident_id,
            previous_state=trigger.previous_state,
            current_state=trigger.current_state,
        )
    return await service.process(trigger)
