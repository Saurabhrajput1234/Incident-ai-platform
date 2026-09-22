

"""
Incident REST API endpoints.

All routes delegate to IncidentService.
Agent triggering is handled by the event-driven orchestration layer — not here.
"""
import csv
import io
import logging
from fastapi import APIRouter, Depends, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.postgres.session import get_db
from app.modules.incidents.service import IncidentService
from app.modules.incidents.schemas import (
    IncidentCreate, IncidentUpdate, IncidentResponse, IncidentListResponse
)

router = APIRouter(prefix="/incidents", tags=["incidents"])
logger = logging.getLogger(__name__)


def get_service(db: AsyncSession = Depends(get_db)) -> IncidentService:
    return IncidentService(db)


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: IncidentCreate,
    service: IncidentService = Depends(get_service),
):
    """
    Create a new incident.
    The orchestration layer automatically triggers the Triage Agent via event bus.
    """
    return await service.create_incident(payload)


@router.post("/bulk-import", status_code=status.HTTP_200_OK)
async def bulk_import_incidents(
    file: UploadFile = File(..., description="CSV file with incident rows"),
    service: IncidentService = Depends(get_service),
):
    """
    Bulk import incidents from a CSV file.
    Each row creates one incident and the event bus queues triage automatically.
    """
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    created = []
    failed = []

    def _get(row: dict, *keys) -> str | None:
        for k in keys:
            v = row.get(k) or row.get(k.lower()) or row.get(k.replace("_", " ").title())
            if v and str(v).strip():
                return str(v).strip()
        return None

    for i, row in enumerate(reader, start=2):
        try:
            payload = IncidentCreate(
                short_description=_get(row, "short_description", "Short Description") or "",
                description=_get(row, "description", "Description"),
                priority=_get(row, "priority", "Priority") or "3",
                state=_get(row, "state", "State") or "new",
                category=_get(row, "category", "Category"),
                subcategory=_get(row, "subcategory", "Subcategory"),
                impact=_get(row, "impact", "Impact") or "2",
                urgency=_get(row, "urgency", "Urgency") or "2",
                assignment_group=_get(row, "assignment_group", "Assignment Group"),
                assigned_to=_get(row, "assigned_to", "Assigned To"),
                caller=_get(row, "caller", "Caller"),
                configuration_item=_get(row, "configuration_item", "Configuration Item"),
                business_service=_get(row, "business_service", "Business Service"),
                environment=_get(row, "environment", "Environment"),
                source=_get(row, "source", "Source") or "api",
                work_notes=_get(row, "work_notes", "Work Notes"),
            )
            incident = await service.create_incident(payload)
            created.append({
                "row": i,
                "incident_number": incident.incident_number,
                "id": incident.id,
                "short_description": incident.short_description,
            })
        except Exception as e:
            failed.append({"row": i, "error": str(e)})

    return {
        "total_rows": len(created) + len(failed),
        "created": len(created),
        "failed": len(failed),
        "incidents": created,
        "errors": failed,
    }

    return {
        "total_rows": len(created) + len(failed),
        "created": len(created),
        "failed": len(failed),
        "incidents": created,
        "errors": failed,
    }


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
    service: IncidentService = Depends(get_service),
):
    """
    Update an existing incident.
    """
    return await service.update_incident(incident_id, payload)


@router.delete("/{incident_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_incident(
    incident_id: str,
    service: IncidentService = Depends(get_service),
):
    """Delete an incident permanently."""
    await service.delete_incident(incident_id)
