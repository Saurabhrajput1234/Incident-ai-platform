"""
AcknowledgementHandler — handles IncidentStateChangedEvent.

Triggers AcknowledgementService ONCE per incident when Triage assigns an engineer
and moves the incident to in_progress.

Once-per-incident guarantee (DB-backed):
    Before running, query the work_notes table for an existing
    ACKNOWLEDGEMENT_AGENT / SEND_ACKNOWLEDGEMENT note for this incident.
    If one already exists, skip — prevents duplicate acknowledgements on re-triage
    (e.g. engineer removed → triage re-runs → new engineer assigned → ACK must NOT fire again).

Condition:
    current_state == "in_progress"
    AND changed_by == "TRIAGE_AGENT"
    AND no prior SEND_ACKNOWLEDGEMENT work note exists for this incident (DB check)
"""
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.orchestrator.events import IncidentStateChangedEvent
from app.orchestrator.constants import AgentSource

logger = logging.getLogger(__name__)


class AcknowledgementHandler:
    async def handle(self, event: IncidentStateChangedEvent) -> None:
        # Condition 1: only fire when TriageAgent moves the incident to in_progress
        if event.current_state != "in_progress":
            return
        if event.changed_by != AgentSource.TRIAGE_AGENT:
            return

        engine = create_async_engine(settings.DATABASE_URL, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as db:
                # Condition 2 (DB-backed): skip if acknowledgement already sent for this incident.
                # Uses the existing work_notes table — no new infrastructure needed.
                already_acked = await self._already_acknowledged(db, event.incident_id)
                if already_acked:
                    logger.info(
                        "[AckHandler] %s — skipping, acknowledgement already sent (once-per-incident guard)",
                        event.incident_number,
                    )
                    return

                from app.modules.agents.acknowledgement.service import AcknowledgementService
                response = await AcknowledgementService(db).process_acknowledgement(
                    incident_id=event.incident_id
                )
                logger.info(
                    "[AckHandler] %s — success=%s",
                    event.incident_number, response.success,
                )
        except Exception as exc:
            logger.error("[AckHandler] %s error: %s", event.incident_id, exc, exc_info=True)
        finally:
            await engine.dispose()

    @staticmethod
    async def _already_acknowledged(db, incident_id: str) -> bool:
        """
        Returns True if a SEND_ACKNOWLEDGEMENT work note already exists for this incident.
        Uses the existing incident_work_notes table — DB-backed, no new table required.
        """
        from sqlalchemy import select
        from app.modules.work_notes.model import IncidentWorkNote
        from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType

        result = await db.execute(
            select(IncidentWorkNote.id)
            .where(
                IncidentWorkNote.incident_id == incident_id,
                IncidentWorkNote.source_type == WorkNoteSourceType.ACKNOWLEDGEMENT_AGENT.value,
                IncidentWorkNote.action_type == WorkNoteActionType.SEND_ACKNOWLEDGEMENT.value,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
