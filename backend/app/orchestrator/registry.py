"""
Wires event handlers to the event bus.
Called once at application startup from lifecycle.py.
"""
import logging
from app.orchestrator.bus import EventBus
from app.orchestrator.events import IncidentCreatedEvent, IncidentStateChangedEvent, ReTriageRequestedEvent
from app.orchestrator.handlers.triage import TriageHandler
from app.orchestrator.handlers.acknowledgement import AcknowledgementHandler
from app.orchestrator.handlers.pending import PendingHandler
from app.orchestrator.handlers.resolution import ResolutionHandler

logger = logging.getLogger(__name__)


def register_all_handlers(bus: EventBus) -> None:
    triage_handler = TriageHandler()

    # IncidentCreatedEvent → original creation triage (unchanged)
    bus.subscribe(IncidentCreatedEvent, triage_handler.handle)

    # ReTriageRequestedEvent → re-triage when engineer removed or group changed
    bus.subscribe(ReTriageRequestedEvent, triage_handler.handle_retriage)

    # IncidentStateChangedEvent → ACK, Pending, Resolution handlers
    bus.subscribe(IncidentStateChangedEvent, AcknowledgementHandler().handle)
    bus.subscribe(IncidentStateChangedEvent, PendingHandler().handle)
    bus.subscribe(IncidentStateChangedEvent, ResolutionHandler().handle)

    logger.info("[Orchestrator] All event handlers registered.")
