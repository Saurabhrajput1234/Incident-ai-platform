"""
TriageHandler — handles IncidentCreatedEvent.
Triggers TriageService for every new incident.
"""
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.orchestrator.events import IncidentCreatedEvent

logger = logging.getLogger(__name__)


class TriageHandler:
    async def handle(self, event: IncidentCreatedEvent) -> None:
        if event.state != "new":
            return

        from app.modules.agents.triage.service import TriageService

        engine = create_async_engine(settings.DATABASE_URL, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as db:
                response = await TriageService(db).run_triage(incident_id=event.incident_id)
                if response.success:
                    logger.info("[TriageHandler] %s triaged successfully", event.incident_number)
                else:
                    logger.warning("[TriageHandler] %s triage failed: %s", event.incident_number, response.errors)
        except Exception as exc:
            logger.error("[TriageHandler] %s error: %s", event.incident_id, exc, exc_info=True)
        finally:
            await engine.dispose()
