"""
Wires event handlers to the event bus.
Called once at application startup from lifecycle.py.
"""
import logging
from app.orchestrator.bus import EventBus
from app.orchestrator.events import IncidentCreatedEvent, IncidentStateChangedEvent
from app.orchestrator.handlers.triage import TriageHandler
from app.orchestrator.handlers.acknowledgement import AcknowledgementHandler
from app.orchestrator.handlers.pending import PendingHandler
from app.orchestrator.handlers.resolution import ResolutionHandler

logger = logging.getLogger(__name__)


def register_all_handlers(bus: EventBus) -> None:
    # IncidentCreatedEvent → TriageHandler
    bus.subscribe(IncidentCreatedEvent, TriageHandler().handle)

    # IncidentStateChangedEvent → ACK, Pending, Resolution handlers
    # All three listen to state changes; each has its own condition filter inside.
    bus.subscribe(IncidentStateChangedEvent, AcknowledgementHandler().handle)
    bus.subscribe(IncidentStateChangedEvent, PendingHandler().handle)
    bus.subscribe(IncidentStateChangedEvent, ResolutionHandler().handle)

    logger.info("[Orchestrator] All event handlers registered.")
