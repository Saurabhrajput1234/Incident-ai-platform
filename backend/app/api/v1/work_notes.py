"""
Work Notes API.

GET  /v1/incidents/{incident_id}/work-notes          — All work notes for an incident
POST /v1/incidents/{incident_id}/work-notes          — Add a manual work note (USER/ENGINEER)
GET  /v1/incidents/{incident_id}/work-notes/latest   — Latest work note
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database.postgres.session import get_db
from app.modules.work_notes.service import WorkNoteService
from app.modules.work_notes.schemas import WorkNoteResponse
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType

router = APIRouter(tags=["work-notes"])


def get_wn_service(db: AsyncSession = Depends(get_db)) -> WorkNoteService:
    return WorkNoteService(db)


class ManualNoteRequest(BaseModel):
    message: str = Field(..., min_length=1)
    source_type: WorkNoteSourceType = WorkNoteSourceType.USER
    source_name: str = Field(..., min_length=1, max_length=200)
    source_id: str | None = None


@router.get(
    "/incidents/{incident_id}/work-notes",
    response_model=list[WorkNoteResponse],
)
async def list_work_notes(
    incident_id: str,
    limit: int = 100,
    service: WorkNoteService = Depends(get_wn_service),
):
    return await service.get_notes(incident_id, limit=limit)


@router.post(
    "/incidents/{incident_id}/work-notes",
    response_model=WorkNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_work_note(
    incident_id: str,
    payload: ManualNoteRequest,
    service: WorkNoteService = Depends(get_wn_service),
):
    return await service.add_note(
        incident_id=incident_id,
        message=payload.message,
        source_type=payload.source_type,
        source_name=payload.source_name,
        source_id=payload.source_id,
        action_type=WorkNoteActionType.MANUAL_NOTE,
    )


@router.get(
    "/incidents/{incident_id}/work-notes/latest",
    response_model=WorkNoteResponse | None,
)
async def get_latest_work_note(
    incident_id: str,
    service: WorkNoteService = Depends(get_wn_service),
):
    return await service.get_latest(incident_id)
