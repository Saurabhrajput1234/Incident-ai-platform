"""
Triage API.

POST /v1/triage/{incident_id}         — Run full triage (LLM + agent + update)
GET  /v1/triage/{incident_id}/context — Preview AIContext (debug, no agent)
"""
from datetime import date
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres.session import get_db
from app.modules.agents.triage.service import TriageService
from app.modules.agents.base.response import AgentResponse
from app.modules.context.service import ContextService
from app.modules.context.schemas import AIContext

router = APIRouter(prefix="/triage", tags=["triage"])


def get_triage_service(db: AsyncSession = Depends(get_db)) -> TriageService:
    return TriageService(db)


def get_context_service(db: AsyncSession = Depends(get_db)) -> ContextService:
    return ContextService(db)


@router.post("/{incident_id}", response_model=AgentResponse, status_code=status.HTTP_200_OK)
async def run_triage(
    incident_id: str,
    context_date: date | None = Query(
        default=None,
        description="Date for shift lookup. Defaults to today."
    ),
    apply_recommendation: bool = Query(
        default=True,
        description="If True, updates the incident with the recommended engineer."
    ),
    service: TriageService = Depends(get_triage_service),
):
    """
    Run the Triage Agent for an incident.

    Flow:
    1. If incident has no assignment_group → LLM determines it from description
    2. Build AIContext (incident + available engineers)
    3. Triage Agent scores engineers and picks the best one
    4. Update incident with recommended engineer and state=in_progress
    """
    return await service.run_triage(
        incident_id=incident_id,
        context_date=context_date,
        apply_recommendation=apply_recommendation,
    )


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
    Preview the AIContext for an incident without running the agent.
    Useful for debugging — does not update anything.
    """
    return await service.build_for_incident(
        incident_id=incident_id,
        context_date=context_date,
    )
