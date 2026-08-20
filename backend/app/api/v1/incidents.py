

"""
Incident REST API endpoints.

All routes delegate to IncidentService — no business logic here.
Auto-triggers Triage Agent after incident creation (background task).
"""
import asyncio
import logging
from fastapi import APIRouter, Depends, Query, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.database.postgres.session import get_db
from app.modules.incidents.service import IncidentService
from app.modules.incidents.schemas import (
    IncidentCreate, IncidentUpdate, IncidentResponse, IncidentListResponse
)
from app.core.config import settings

router = APIRouter(prefix="/incidents", tags=["incidents"])
logger = logging.getLogger(__name__)


def get_service(db: AsyncSession = Depends(get_db)) -> IncidentService:
    return IncidentService(db)


async def _auto_triage(incident_id: str) -> None:
    """
    Background task: triggers triage agent after incident creation.
    Uses its own DB session since background tasks run outside the request session.
    """
    from app.modules.agents.triage.service import TriageService

    engine = create_async_engine(settings.DATABASE_URL, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as db:
            triage = TriageService(db)
            response = await triage.run_triage(incident_id=incident_id)
            if response.success:
                logger.info(f"[Auto-Triage] {incident_id} triaged successfully")
            else:
                logger.warning(f"[Auto-Triage] {incident_id} triage failed: {response.errors}")
    except Exception as e:
        logger.error(f"[Auto-Triage] {incident_id} error: {e}")
    finally:
        await engine.dispose()


async def _auto_triage_force(incident_id: str) -> None:
    """
    Background task: force re-triage after any incident update.
    Uses force=True so it re-assigns even if already assigned.
    """
    from app.modules.agents.triage.service import TriageService

    engine = create_async_engine(settings.DATABASE_URL, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as db:
            triage = TriageService(db)
            response = await triage.run_triage(incident_id=incident_id, force=True)
            if response.success:
                logger.info(f"[Auto-Triage-Force] {incident_id} re-triaged successfully")
            else:
                logger.warning(f"[Auto-Triage-Force] {incident_id} re-triage failed: {response.errors}")
    except Exception as e:
        logger.error(f"[Auto-Triage-Force] {incident_id} error: {e}")
    finally:
        await engine.dispose()


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: IncidentCreate,
    background_tasks: BackgroundTasks,
    service: IncidentService = Depends(get_service),
):
    """
    Create a new incident.
    Automatically triggers the Triage Agent in the background after creation.
    """
    incident = await service.create_incident(payload)
    # Auto-trigger triage for new unassigned incidents
    background_tasks.add_task(_auto_triage, incident.id)
    return incident


@router.get("", response_model=IncidentListResponse)
async def list_incidents(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page"),
    priority: str | None = Query(default=None, description="Filter by priority (1-4)"),
    state: str | None = Query(default=None, description="Filter by state"),
    category: str | None = Query(default=None, description="Filter by category"),
    assignment_group: str | None = Query(default=None, description="Filter by assignment group"),
    sort_by: str = Query(
        default="created_at",
        pattern="^(created_at|updated_at|priority|state)$",
    ),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    service: IncidentService = Depends(get_service),
):
    """List incidents with pagination, filtering and sorting."""
    return await service.list_incidents(
        page=page, page_size=page_size,
        priority=priority, state=state,
        category=category, assignment_group=assignment_group,
        sort_by=sort_by, sort_order=sort_order,
    )


@router.get("/search", response_model=IncidentListResponse)
async def search_incidents(
    q: str = Query(..., min_length=2, description="Keyword to search"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    priority: str | None = Query(default=None),
    state: str | None = Query(default=None),
    category: str | None = Query(default=None),
    assignment_group: str | None = Query(default=None),
    service: IncidentService = Depends(get_service),
):
    """Search incidents by keyword across key fields."""
    return await service.search_incidents(
        query=q, page=page, page_size=page_size,
        priority=priority, state=state,
        category=category, assignment_group=assignment_group,
    )


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: str,
    service: IncidentService = Depends(get_service),
):
    """Get a single incident by ID or incident number."""
    return await service.get_incident(incident_id)


@router.put("/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: str,
    payload: IncidentUpdate,
    background_tasks: BackgroundTasks,
    service: IncidentService = Depends(get_service),
):
    """
    Update an existing incident.
    Auto-triggers the Triage Agent (force re-assign) after every update
    on new/in_progress incidents so the assignment stays current.
    """
    updated = await service.update_incident(incident_id, payload)

    # Auto re-triage on every save for active tickets
    if updated.state in ('new', 'in_progress'):
        logger.info(f"Incident {incident_id} updated — triggering re-triage")
        background_tasks.add_task(_auto_triage_force, incident_id)

    return updated


@router.delete("/{incident_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_incident(
    incident_id: str,
    service: IncidentService = Depends(get_service),
):
    """Delete an incident permanently."""
    await service.delete_incident(incident_id)
