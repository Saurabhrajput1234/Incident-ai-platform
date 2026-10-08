"""
ResolutionHandler — handles IncidentStateChangedEvent.

Trigger condition:
    on_hold/pending → in_progress/active transition caused by a USER work note.

Also handles ENGINEER-triggered activations:
    on_hold → in_progress caused by an ENGINEER note or manual state change.
    In this case, only the active PendingCycle is cancelled — no LLM analysis,
    no notifications, no auto-resolve.

Fires AFTER the state is already in_progress (correct audit order):
    1. User/Engineer adds work note or changes state
    2. WorkNoteService auto-activates: on_hold → in_progress
    3. IncidentStateChangedEvent published → ResolutionHandler fires
    4. Resolution Agent analyses the response (USER only)
       OR PendingCycle is cancelled silently (ENGINEER only)

Non-user sources that are explicitly skipped:
    PENDING_AGENT, ACKNOWLEDGEMENT_AGENT, TRIAGE_AGENT, RESOLUTION_AGENT, SYSTEM
    ENGINEER source → cycle cancelled only, no Resolution Agent run.
    A None source (manual engineer state change) is passed through to ResolutionService
    which performs its own source check on the latest work note.
"""
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.orchestrator.events import IncidentStateChangedEvent
from app.orchestrator.constants import NON_USER_SOURCES, AgentSource

logger = logging.getLogger(__name__)

_PENDING_STATES = {"on_hold", "pending"}
_ACTIVE_STATES = {"in_progress", "active"}

# Sources that skip Resolution Agent entirely but should still cancel the cycle
_ENGINEER_SOURCES = {AgentSource.ENGINEER}

# Sources that skip everything (no cycle cancel, no agent)
_SKIP_ALL_SOURCES = NON_USER_SOURCES - _ENGINEER_SOURCES


class ResolutionHandler:
    """
    Triggers ResolutionService when a USER work note causes
    an on_hold/pending → in_progress state transition.

    When an ENGINEER note causes the same transition, only cancels
    the active PendingCycle without running the Resolution Agent.
    """

    async def handle(self, event: IncidentStateChangedEvent) -> None:
        # Only act on on_hold/pending → in_progress/active transitions
        if event.previous_state not in _PENDING_STATES:
            return
        if event.current_state not in _ACTIVE_STATES:
            return

        source = event.triggering_work_note_source
        changed_by = event.changed_by

        # Skip agents/system entirely — no cycle cancel, no agent
        if source in _SKIP_ALL_SOURCES:
            logger.debug("[ResolutionHandler] Skipped: source=%s", source)
            return

        # Engineer added a note OR manually changed state (changed_by=ENGINEER, source=None)
        # → cancel cycle only, no Resolution Agent
        if source in _ENGINEER_SOURCES or changed_by == AgentSource.ENGINEER:
            await self._cancel_cycle_only(event)
            return

        # USER source (or None = manual state change) → run full Resolution Agent
        from app.modules.agents.resolution.service import ResolutionService
        from app.modules.agents.resolution.schemas import ResolutionTrigger
        from app.modules.agent_executions.logger import agent_execution_log

        engine = create_async_engine(settings.DATABASE_URL, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with agent_execution_log(
                agent_name="ResolutionAgent",
                incident_id=event.incident_id,
                triggering_event_type="IncidentStateChangedEvent",
                triggering_event_id=event.incident_id,
                correlation_id=event.incident_number,
            ) as log:
                async with session_factory() as db:
                    trigger = ResolutionTrigger(
                        incident_id=event.incident_id,
                        previous_state=event.previous_state,
                        current_state="active",
                        triggering_work_note_id=event.triggering_work_note_id,
                        triggering_work_note_source=event.triggering_work_note_source,
                    )
                    response = await ResolutionService(db).process(trigger)
                    action = response.result.get("action", "unknown") if isinstance(response.result, dict) else "unknown"
                    if not response.success:
                        log.set_result("failed", error="; ".join(response.errors) if response.errors else "resolution failed")
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

    async def _cancel_cycle_only(self, event: IncidentStateChangedEvent) -> None:
        """
        Cancel the active PendingCycle when an engineer activates an on_hold incident.
        No LLM, no notifications, no auto-resolve.
        """
        engine = create_async_engine(settings.DATABASE_URL, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as db:
                from app.modules.pending_cycles.service import PendingCycleService
                from app.modules.work_notes.service import WorkNoteService
                from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType

                cycle_svc = PendingCycleService(db)
                cancelled = await cycle_svc.cancel_active_cycle(event.incident_id)

                if cancelled:
                    # Write a work note so the audit trail shows the cycle was stopped
                    wn_svc = WorkNoteService(db)
                    await wn_svc.add_note(
                        incident_id=event.incident_id,
                        message=(
                            f"Pending reminder cycle cancelled.\n"
                            f"Reason: Engineer has taken action on this incident "
                            f"(state changed from {event.previous_state} to {event.current_state}).\n"
                            f"No further reminders will be sent."
                        ),
                        source_type=WorkNoteSourceType.SYSTEM,
                        source_name="System",
                        action_type=WorkNoteActionType.SYSTEM_NOTE,
                        auto_activate=False,
                    )
                    logger.info(
                        "[ResolutionHandler] PendingCycle cancelled for %s — engineer took action.",
                        event.incident_number,
                    )
                else:
                    logger.debug(
                        "[ResolutionHandler] No active PendingCycle to cancel for %s.",
                        event.incident_number,
                    )
        except Exception as exc:
            logger.error(
                "[ResolutionHandler] Cycle cancel failed for %s: %s",
                event.incident_id, exc, exc_info=True,
            )
        finally:
            await engine.dispose()
