"""
Shift Roster REST API endpoints.

POST   /v1/shift-roster/upload                       Upload Excel or CSV
GET    /v1/shift-roster/uploads                      Upload history
GET    /v1/shift-roster/available                    Available engineers on a date (Triage Agent)
GET    /v1/shift-roster/search                       Search/filter engineers
PUT    /v1/shift-roster/roster/{roster_id}           Update single daily entry
GET    /v1/shift-roster/engineer/{email}             Engineer details
PUT    /v1/shift-roster/engineer/{email}             Update engineer master record
DELETE /v1/shift-roster/engineer/{email}             Mark engineer inactive
GET    /v1/shift-roster/engineer/{email}/roster      Engineer roster for date range
GET    /v1/shift-roster/engineer/{email}/history     Roster change history

Shift/leave code definitions are available as a constant:
    from app.modules.shift_roster.enums import SHIFT_DEFINITIONS
"""
from datetime import date
from fastapi import APIRouter, Depends, UploadFile, File, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres.session import get_db
from app.modules.shift_roster.service import ShiftRosterService
from app.modules.shift_roster.schemas import (
    UploadSummary, EngineerResponse, EngineerUpdate,
    ShiftRosterResponse, ShiftRosterUpdate,
    EngineerAvailability, RosterHistoryResponse,
)

router = APIRouter(prefix="/shift-roster", tags=["shift-roster"])


def get_service(db: AsyncSession = Depends(get_db)) -> ShiftRosterService:
    return ShiftRosterService(db)


# --- Upload ---

@router.post("/upload", response_model=UploadSummary, status_code=status.HTTP_201_CREATED)
async def upload_roster(
    file: UploadFile = File(..., description="Shift roster .xlsx or .csv file"),
    uploaded_by: str | None = Query(default=None),
    service: ShiftRosterService = Depends(get_service),
):
    """Upload monthly/weekly shift roster Excel or CSV file."""
    if not (file.filename.endswith(".xlsx") or file.filename.endswith(".csv")):
        raise HTTPException(status_code=400, detail="Only .xlsx and .csv files are supported")
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    return await service.upload_roster(file_bytes, file.filename, uploaded_by)


@router.get("/uploads", response_model=list[UploadSummary])
async def get_upload_history(service: ShiftRosterService = Depends(get_service)):
    """View all upload history."""
    uploads = await service.get_upload_history()
    return [UploadSummary(
        upload_id=u.id,
        file_name=u.file_name,
        roster_start_date=u.roster_start_date,
        roster_end_date=u.roster_end_date,
        total_records=u.total_records,
        imported_records=u.imported_records,
        failed_records=u.failed_records,
        upload_status=u.upload_status,
    ) for u in uploads]


# --- Triage Agent availability endpoint ---

@router.get("/available", response_model=list[EngineerAvailability])
async def get_available_engineers(
    roster_date: date = Query(..., description="Date to check availability (YYYY-MM-DD)"),
    shift_code: str | None = Query(default=None, description="Filter by shift e.g. Shift1, WO, PL"),
    assignment_group: str | None = Query(default=None),
    level: str | None = Query(default=None, description="L1, L2, L3"),
    service: ShiftRosterService = Depends(get_service),
):
    """
    Find engineers available on a specific date.
    Primary endpoint for the Triage Agent to identify who is working.
    """
    return await service.get_available_engineers(
        roster_date=roster_date,
        shift_code=shift_code,
        assignment_group=assignment_group,
        level=level,
    )


# --- Search engineers ---

@router.get("/search", response_model=list[EngineerAvailability])
async def search_engineers(
    assignment_group: str | None = Query(default=None),
    level: str | None = Query(default=None),
    name: str | None = Query(default=None),
    email: str | None = Query(default=None),
    status: str | None = Query(default="active"),
    roster_date: date | None = Query(default=None, description="Optional: filter by date to include shift on that day"),
    shift_code: str | None = Query(default=None, description="Optional: filter by shift code e.g. Shift1, WO, PL"),
    service: ShiftRosterService = Depends(get_service),
):
    """
    Search and filter engineers.
    When roster_date is provided, each result includes the engineer's shift on that date.
    """
    return await service.search_engineers(
        assignment_group=assignment_group,
        level=level,
        name=name,
        email=email,
        status=status,
        roster_date=roster_date,
        shift_code=shift_code,
    )


# --- Update single roster entry ---

@router.put("/roster/{roster_id}", response_model=ShiftRosterResponse)
async def update_roster_entry(
    roster_id: str,
    payload: ShiftRosterUpdate,
    service: ShiftRosterService = Depends(get_service),
):
    """Update a single daily roster entry. Change is recorded in history."""
    return await service.update_roster_entry(roster_id, payload)


# --- Engineer CRUD ---

@router.get("/engineer/{email}", response_model=list[EngineerResponse])
async def get_engineer(
    email: str,
    assignment_group: str | None = Query(default=None, description="Filter by assignment group"),
    service: ShiftRosterService = Depends(get_service),
):
    """Get engineer records by email. Returns all groups unless assignment_group is specified."""
    return await service.get_engineers_by_email(email, assignment_group)


@router.put("/engineer/{email}", response_model=EngineerResponse)
async def update_engineer(
    email: str,
    payload: EngineerUpdate,
    assignment_group: str = Query(..., description="Assignment group to identify which record to update"),
    service: ShiftRosterService = Depends(get_service),
):
    """Update engineer master record for a specific (email, assignment_group) pair."""
    return await service.update_engineer(email, assignment_group, payload)


@router.delete("/engineer/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_engineer(
    email: str,
    assignment_group: str | None = Query(default=None, description="If omitted, marks all records for this email inactive"),
    service: ShiftRosterService = Depends(get_service),
):
    """Mark engineer as inactive. If assignment_group is provided, only that record is affected."""
    await service.delete_engineer(email, assignment_group)


@router.get("/engineer/{email}/roster", response_model=list[ShiftRosterResponse])
async def get_engineer_roster(
    email: str,
    start: date = Query(..., description="Start date YYYY-MM-DD"),
    end: date = Query(..., description="End date YYYY-MM-DD"),
    assignment_group: str | None = Query(default=None, description="Filter by assignment group"),
    service: ShiftRosterService = Depends(get_service),
):
    """Get an engineer's complete roster for a date range."""
    return await service.get_engineer_roster(email, start, end, assignment_group)


@router.get("/engineer/{email}/history", response_model=list[RosterHistoryResponse])
async def get_engineer_history(
    email: str,
    assignment_group: str | None = Query(default=None, description="Filter by assignment group"),
    service: ShiftRosterService = Depends(get_service),
):
    """View all roster change history for an engineer."""
    return await service.get_engineer_change_history(email, assignment_group)
