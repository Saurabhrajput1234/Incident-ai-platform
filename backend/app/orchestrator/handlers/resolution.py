"""
ResolutionHandler — handles IncidentStateChangedEvent.

Trigger condition:
    on_hold/pending → in_progress/active transition caused by a USER work note.

Fires AFTER the state is already in_progress (correct audit order):
    1. User adds work note
    2. WorkNoteService auto-activates: on_hold → in_progress
    3. IncidentStateChangedEvent published → ResolutionHandler fires
    4. Resolution Agent analyses the response

Non-user sources that are explicitly skipped:
    PENDING_AGENT, ACKNOWLEDGEMENT_AGENT, TRIAGE_AGENT, RESOLUTION_AGENT, ENGINEER, SYSTEM
    A None source (manual engineer state change) is passed through to ResolutionService
    which performs its own source check on the latest work note.
"""
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.orchestrator.events import IncidentStateChangedEvent
from app.orchestrator.constants import NON_USER_SOURCES

logger = logging.getLogger(__name__)

_PENDING_STATES = {"on_hold", "pending"}
_ACTIVE_STATES = {"in_progress", "active"}


class ResolutionHandler:
    """
    Triggers ResolutionService when a USER work note causes
    an on_hold/pending → in_progress state transition.
    """

    async def handle(self, event: IncidentStateChangedEvent) -> None:
        # Only act on on_hold/pending → in_progress/active transitions
        if event.previous_state not in _PENDING_STATES:
            return
        if event.current_state not in _ACTIVE_STATES:
            return

        # Skip all non-USER triggered activations.
        # PENDING_AGENT reminder → auto-activates → MUST be skipped.
        # ENGINEER note → skip (not a user/caller response).
        # None source = manual engineer state change → pass to ResolutionService to evaluate.
        if event.triggering_work_note_source in NON_USER_SOURCES:
            logger.debug(
                "[ResolutionHandler] Skipped: source=%s",
                event.triggering_work_note_source,
            )
            return

        from app.modules.agents.resolution.service import ResolutionService
        from app.modules.agents.resolution.schemas import ResolutionTrigger

        engine = create_async_engine(settings.DATABASE_URL, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as db:
                trigger = ResolutionTrigger(
                    incident_id=event.incident_id,
                    previous_state=event.previous_state,
                    current_state="active",  # ResolutionService contract
                    triggering_work_note_id=event.triggering_work_note_id,
                    triggering_work_note_source=event.triggering_work_note_source,
                )
                response = await ResolutionService(db).process(trigger)
                action = response.result.get("action", "unknown") if isinstance(response.result, dict) else "unknown"
                logger.info(
                    "[ResolutionHandler] %s — success=%s action=%s",
                    event.incident_number, response.success, action,
                )
        except Exception as exc:
            logger.error(
                "[ResolutionHandler] %s error: %s",
                event.incident_id, exc, exc_info=True,
            )
        finally:
            await engine.dispose()
