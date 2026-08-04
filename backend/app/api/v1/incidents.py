"""
Incident REST API endpoints.

All routes delegate to IncidentService — no business logic here.
Route ordering matters: /search must be declared before /{incident_id}
to avoid FastAPI matching "search" as a path parameter.
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.postgres.session import get_db
from app.modules.incidents.service import IncidentService
from app.modules.incidents.schemas import (
    IncidentCreate, IncidentUpdate, IncidentResponse, IncidentListResponse
)

router = APIRouter(prefix="/incidents", tags=["incidents"])


def get_service(db: AsyncSession = Depends(get_db)) -> IncidentService:
    """Dependency that provides an IncidentService with a DB session."""
    return IncidentService(db)


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: IncidentCreate,
    service: IncidentService = Depends(get_service),
):
    """Create a new incident."""
    return await service.create_incident(payload)


@router.get("", response_model=IncidentListResponse)
async def list_incidents(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page"),
    # Optional filters
    priority: str | None = Query(default=None, description="Filter by priority (1-4)"),
    state: str | None = Query(default=None, description="Filter by state"),
    category: str | None = Query(default=None, description="Filter by category"),
    assignment_group: str | None = Query(default=None, description="Filter by assignment group"),
    # Sorting
    sort_by: str = Query(
        default="created_at",
        pattern="^(created_at|updated_at|priority|state)$",
        description="Field to sort by"
    ),
    sort_order: str = Query(
        default="desc",
        pattern="^(asc|desc)$",
        description="Sort direction"
    ),
    service: IncidentService = Depends(get_service),
):
    """List incidents with pagination, filtering and sorting."""
    return await service.list_incidents(
        page=page,
        page_size=page_size,
        priority=priority,
        state=state,
        category=category,
        assignment_group=assignment_group,
        sort_by=sort_by,
        sort_order=sort_order,
    )


# NOTE: /search must be declared before /{incident_id}
# Otherwise FastAPI will match "search" as the incident_id path param
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
        query=q,
        page=page,
        page_size=page_size,
        priority=priority,
        state=state,
        category=category,
        assignment_group=assignment_group,
    )


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: str,
    service: IncidentService = Depends(get_service),
):
    """Get a single incident by ID."""
    return await service.get_incident(incident_id)


@router.put("/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: str,
    payload: IncidentUpdate,
    service: IncidentService = Depends(get_service),
):
    """Update an existing incident. Only provided fields are updated."""
    return await service.update_incident(incident_id, payload)


@router.delete("/{incident_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_incident(
    incident_id: str,
    service: IncidentService = Depends(get_service),
):
    """Delete an incident permanently."""
    await service.delete_incident(incident_id)
