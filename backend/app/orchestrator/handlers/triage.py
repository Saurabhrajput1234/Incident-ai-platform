"""
TriageHandler — handles IncidentCreatedEvent and ReTriageRequestedEvent.

handle()          → original creation triage (untouched)
handle_retriage() → re-triage when engineer removed or group changed manually
"""
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.orchestrator.events import IncidentCreatedEvent, ReTriageRequestedEvent

logger = logging.getLogger(__name__)


class TriageHandler:
    async def handle(self, event: IncidentCreatedEvent) -> None:
        """Original triage — fires on incident creation. Unchanged."""
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

    async def handle_retriage(self, event: ReTriageRequestedEvent) -> None:
        """
        Re-triage handler — fires when engineer is removed or group is changed manually.

        Key behaviours:
          - force=True       → bypasses "already assigned" guard
          - preserve_state=True → does NOT change incident state after assigning engineer
          - State remains exactly what it was (on_hold stays on_hold, in_progress stays in_progress)
        """
        from app.modules.agents.triage.service import TriageService

        logger.info(
            "[ReTriageHandler] %s re-triage requested (reason=%s, state=%s)",
            event.incident_number, event.reason, event.current_state,
        )

        engine = create_async_engine(settings.DATABASE_URL, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as db:
                response = await TriageService(db).run_triage(
                    incident_id=event.incident_id,
                    force=True,
                    preserve_state=True,
                    retriage_reason=event.reason,
                )
                if response.success:
                    logger.info("[ReTriageHandler] %s re-assigned successfully", event.incident_number)
                else:
                    logger.warning("[ReTriageHandler] %s re-triage failed: %s", event.incident_number, response.errors)
        except Exception as exc:
            logger.error("[ReTriageHandler] %s error: %s", event.incident_id, exc, exc_info=True)
        finally:
            await engine.dispose()
