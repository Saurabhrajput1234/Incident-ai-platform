"""
Triage Context API.

Exposes the AI Context Builder — collects incident and shift roster
data and returns a structured AIContext object.

The Triage Agent (which consumes this context) is not yet implemented.

GET /v1/triage/{incident_id}/context  — Build and return AI context for an incident
"""
from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres.session import get_db
from app.modules.context.service import ContextService
from app.modules.context.schemas import AIContext

router = APIRouter(prefix="/triage", tags=["triage"])


def get_context_service(db: AsyncSession = Depends(get_db)) -> ContextService:
    return ContextService(db)


@router.get("/{incident_id}/context", response_model=AIContext)
async def get_context(
    incident_id: str,
    context_date: date | None = Query(
        default=None,
        description="Date for shift lookup. Defaults to today."
    ),
    service: ContextService = Depends(get_context_service),
):
    """
    Build and return the AI context for a specific incident.

    Collects:
    - Incident details from the Incident Module
    - Available engineers from the Shift Roster Module

    Returns a structured AIContext object ready to be consumed
    by the Triage Agent (future phase).
    """
    return await service.build_for_incident(
        incident_id=incident_id,
        context_date=context_date,
    )
