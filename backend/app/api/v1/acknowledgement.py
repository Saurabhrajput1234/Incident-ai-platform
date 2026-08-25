"""
Acknowledgement Agent API.

POST /v1/acknowledgement/{incident_id}  — Process incident acknowledgement
GET  /v1/acknowledgement/logs           — Retrieve audit logs
"""
import json
from pathlib import Path
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres.session import get_db
from app.modules.agents.base.response import AgentResponse
from app.modules.agents.acknowledgement.service import AcknowledgementService

router = APIRouter(prefix="/acknowledgement", tags=["acknowledgement"])

LOGS_FILE = Path(__file__).parent.parent.parent / "modules" / "agents" / "acknowledgement" / "dummy_data" / "ack_logs.json"


def get_acknowledgement_service(db: AsyncSession = Depends(get_db)) -> AcknowledgementService:
    return AcknowledgementService(db)


@router.post("/{incident_id}", response_model=AgentResponse, status_code=status.HTTP_200_OK)
async def process_acknowledgement(
    incident_id: str,
    service: AcknowledgementService = Depends(get_acknowledgement_service),
):
    """
    Run the Acknowledgement Agent for an incident.

    Flow:
    1. Ingestion: Reads incident context from PostgreSQL
    2. Intent Classification: Fast rule path ➔ Groq LLM fallback
    3. Template & Delivery: Renders Jinja2 HTML and delivers notification
    4. Work Notes Update: Appends acknowledgement audit notes to incident
    """
    return await service.process_acknowledgement(incident_id=incident_id)


@router.get("/logs", status_code=status.HTTP_200_OK)
async def list_delivery_logs():
    """
    Returns audit delivery log records.
    """
    logs = []
    if LOGS_FILE.exists() and LOGS_FILE.stat().st_size > 0:
        try:
            with open(LOGS_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
    return {"status": "success", "count": len(logs), "items": logs}
