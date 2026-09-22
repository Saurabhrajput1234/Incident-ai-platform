"""
PendingHandler — handles IncidentStateChangedEvent.

Triggers PendingService when a REAL active → pending/on_hold transition occurs.

Conditions (ALL must be true):
    1. previous_state in {"in_progress", "active"}   — must have been active before
    2. current_state  in {"on_hold", "pending"}       — transitioning to pending
    3. changed_by != PENDING_AGENT                    — skip PendingAgent's own restore

Condition 1 is the key addition: prevents triggering on state changes that weren't
preceded by an active state (e.g. new → on_hold, or a second on_hold write).

Loop prevention:
    PendingAgent sends a reminder, auto-activates (on_hold → in_progress),
    then restores on_hold using changed_by=PENDING_AGENT.
    This handler skips that restore — no new cycle is created.
"""
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.orchestrator.events import IncidentStateChangedEvent
from app.orchestrator.constants import AgentSource

logger = logging.getLogger(__name__)

_ACTIVE_STATES = {"in_progress", "active"}
_PENDING_STATES = {"on_hold", "pending"}


class PendingHandler:
    async def handle(self, event: IncidentStateChangedEvent) -> None:
        # Condition 1: must be transitioning INTO on_hold/pending
        if event.current_state not in _PENDING_STATES:
            return

        # Condition 2: must have come FROM an active state
        # This prevents triggering on: new → on_hold, or repeated on_hold writes
        if event.previous_state not in _ACTIVE_STATES:
            return

        # Condition 3: skip if PendingAgent itself caused the state change
        # (avoids infinite loop: reminder → auto-activate → restore on_hold → new cycle)
        if event.changed_by == AgentSource.PENDING_AGENT:
            return

        from app.modules.agents.pending.service import PendingService

        engine = create_async_engine(settings.DATABASE_URL, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as db:
                response = await PendingService(db).process_pending_transition(
                    incident_id=event.incident_id,
                    changed_by=event.changed_by,
                )
                logger.info(
                    "[PendingHandler] %s — success=%s",
                    event.incident_number, response.success,
                )
        except Exception as exc:
            logger.error("[PendingHandler] %s error: %s", event.incident_id, exc, exc_info=True)
        finally:
            await engine.dispose()
