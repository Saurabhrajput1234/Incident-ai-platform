"""
Pending Agent API.

POST /v1/pending/{incident_id}       — Process pending reminder transition
GET  /v1/pending/{incident_id}/cycle — Retrieve active or latest cycle
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.postgres.session import get_db
from app.modules.agents.base.response import AgentResponse
from app.modules.agents.pending.service import PendingService

router = APIRouter(prefix="/pending", tags=["pending"])


def get_pending_service(db: AsyncSession = Depends(get_db)) -> PendingService:
    return PendingService(db)


@router.post("/{incident_id}", response_model=AgentResponse, status_code=status.HTTP_200_OK)
async def process_pending(
    incident_id: str,
    force_reminder: bool = Query(
        default=False,
        description="If True, advances the reminder count even if cycle is already active.",
    ),
    service: PendingService = Depends(get_pending_service),
):
    """
    Trigger the Pending Agent for an incident.
    Verifies active cycle, inspects latest work note, generates reminder, and resets state to Pending.
    """
    return await service.process_pending_transition(
        incident_id=incident_id,
        force_reminder=force_reminder,
    )


@router.get("/{incident_id}/cycle", status_code=status.HTTP_200_OK)
async def get_cycle(
    incident_id: str,
    service: PendingService = Depends(get_pending_service),
):
    """
    Returns active or latest pending cycle for this incident.
    """
    cycle = await service.get_cycle_status(incident_id)
    return {"status": "success", "cycle": cycle}
