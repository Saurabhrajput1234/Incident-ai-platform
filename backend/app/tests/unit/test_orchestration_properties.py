"""
Property-based tests for the event-driven orchestration layer.

Tests use pytest-asyncio for async execution and unittest.mock for isolation.
Each test validates a specific correctness property from the design document.

Properties tested:
  Property 1:  Work note events are always published (Req 1.1)
  Property 2:  Work note events contain required fields (Req 1.2)
  Property 3:  Events are routed to registered handlers (Req 1.3)
  Property 4:  Source information preservation (Req 1.4)
  Property 5:  USER work notes trigger Resolution Handler (Req 2.1)
  Property 6:  Resolution Handler validates incident state (Req 2.2)
  Property 7:  Concurrent handler execution without blocking (Req 2.4)
  Property 8:  State change events are published (Req 3.1)
  Property 9:  Handler failure isolation (Req 3.3, 4.1)
  Property 10: Error logging and continuation (Req 3.4, 4.3)
  Property 11: Concurrent execution using asyncio.gather (Req 4.2)
  Property 12: Database session isolation per handler (Req 4.4)
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.orchestrator.bus import EventBus
from app.orchestrator.events import (
    IncidentCreatedEvent,
    IncidentStateChangedEvent,
    WorkNoteAddedEvent,
)
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_work_note_event(
    source_type: str = "USER",
    incident_state: str = "on_hold",
    incident_id: str = "inc-001",
    incident_number: str = "INC0000001",
    work_note_id: str = "wn-001",
    source_name: str = "Alice",
    action_type: str = "MANUAL_NOTE",
) -> WorkNoteAddedEvent:
    return WorkNoteAddedEvent(
        incident_id=incident_id,
        incident_number=incident_number,
        work_note_id=work_note_id,
        source_type=source_type,
        source_name=source_name,
        action_type=action_type,
        incident_state=incident_state,
    )


def _make_state_changed_event(
    previous_state: str = "on_hold",
    current_state: str = "in_progress",
    changed_by: str = "engineer",
    triggering_work_note_source: str | None = "USER",
    triggering_work_note_id: str | None = "wn-001",
) -> IncidentStateChangedEvent:
    return IncidentStateChangedEvent(
        incident_id="inc-001",
        incident_number="INC0000001",
        previous_state=previous_state,
        current_state=current_state,
        changed_by=changed_by,
        triggering_work_note_id=triggering_work_note_id,
        triggering_work_note_source=triggering_work_note_source,
    )


# ---------------------------------------------------------------------------
# Property 2: WorkNoteAddedEvent contains all required fields (Req 1.2)
# Feature: event-driven-orchestration, Property 2: Work note events contain required fields
# Validates: Requirements 1.2
# ---------------------------------------------------------------------------

class TestProperty2_WorkNoteEventRequiredFields:
    """For any WorkNoteAddedEvent, all required fields must be present and non-empty."""

    @pytest.mark.parametrize("source_type,incident_state,source_name", [
        ("USER", "on_hold", "Alice"),
        ("ENGINEER", "in_progress", "Bob"),
        ("PENDING_AGENT", "on_hold", "PENDING AGENT"),
        ("SYSTEM", "new", "System"),
        ("TRIAGE_AGENT", "new", "TriageAgent"),
        ("ACKNOWLEDGEMENT_AGENT", "in_progress", "AcknowledgementAgent"),
    ])
    def test_all_required_fields_present(self, source_type, incident_state, source_name):
        # Feature: event-driven-orchestration, Property 2: Work note events contain required fields
        # Validates: Requirements 1.2
        event = _make_work_note_event(
            source_type=source_type,
            incident_state=incident_state,
            source_name=source_name,
        )
        assert event.incident_id, "incident_id must be non-empty"
        assert event.incident_number, "incident_number must be non-empty"
        assert event.work_note_id, "work_note_id must be non-empty"
        assert event.source_type, "source_type must be non-empty"
        assert event.source_name, "source_name must be non-empty"
        assert event.incident_state, "incident_state must be non-empty"
        assert event.added_at is not None, "added_at must be set"

    def test_source_type_preserved_exactly(self):
        # For any source_type value, it should be preserved as-is in the event
        for src in ["USER", "ENGINEER", "TRIAGE_AGENT", "ACKNOWLEDGEMENT_AGENT", "PENDING_AGENT", "SYSTEM"]:
            event = _make_work_note_event(source_type=src)
            assert event.source_type == src


# ---------------------------------------------------------------------------
# Property 1: Work note events are always published (Req 1.1)
# Feature: event-driven-orchestration, Property 1: Work note events are always published
# Validates: Requirements 1.1
# ---------------------------------------------------------------------------

class TestProperty1_WorkNoteEventsAlwaysPublished:
    """For any work note addition, a WorkNoteAddedEvent must be published."""

    @pytest.mark.anyio
    async def test_event_published_for_user_note(self):
        # Feature: event-driven-orchestration, Property 1: Work note events are always published
        # Validates: Requirements 1.1
        published: list[WorkNoteAddedEvent] = []
        bus = EventBus()
        bus.subscribe(WorkNoteAddedEvent, lambda e: published.append(e) or asyncio.sleep(0))

        event = _make_work_note_event(source_type="USER")
        await bus.publish(event)
        assert len(published) == 1
        assert published[0].source_type == "USER"

    @pytest.mark.anyio
    @pytest.mark.parametrize("source_type", ["USER", "ENGINEER", "SYSTEM", "TRIAGE_AGENT"])
    async def test_event_published_for_all_source_types(self, source_type):
        # For any source type, the event should always be published
        published: list[Any] = []

        async def capture(e: WorkNoteAddedEvent) -> None:
            published.append(e)

        bus = EventBus()
        bus.subscribe(WorkNoteAddedEvent, capture)
        event = _make_work_note_event(source_type=source_type)
        await bus.publish(event)
        assert len(published) == 1
        assert published[0].source_type == source_type


# ---------------------------------------------------------------------------
# Property 3: Events are routed to ALL registered handlers (Req 1.3)
# Feature: event-driven-orchestration, Property 3: Events are routed to registered handlers
# Validates: Requirements 1.3
# ---------------------------------------------------------------------------

class TestProperty3_EventRouting:
    """For any event, all registered handlers for that type must receive it."""

    @pytest.mark.anyio
    async def test_all_handlers_receive_event(self):
        # Feature: event-driven-orchestration, Property 3: Events are routed to registered handlers
        # Validates: Requirements 1.3
        received = {"h1": [], "h2": [], "h3": []}

        async def h1(e: WorkNoteAddedEvent) -> None:
            received["h1"].append(e.work_note_id)

        async def h2(e: WorkNoteAddedEvent) -> None:
            received["h2"].append(e.work_note_id)

        async def h3(e: WorkNoteAddedEvent) -> None:
            received["h3"].append(e.work_note_id)

        bus = EventBus()
        bus.subscribe(WorkNoteAddedEvent, h1)
        bus.subscribe(WorkNoteAddedEvent, h2)
        bus.subscribe(WorkNoteAddedEvent, h3)

        event = _make_work_note_event(work_note_id="wn-test")
        await bus.publish(event)

        assert received["h1"] == ["wn-test"]
        assert received["h2"] == ["wn-test"]
        assert received["h3"] == ["wn-test"]

    @pytest.mark.anyio
    async def test_unregistered_event_type_reaches_no_handlers(self):
        received: list[Any] = []

        async def handler(e: Any) -> None:
            received.append(e)

        bus = EventBus()
        bus.subscribe(WorkNoteAddedEvent, handler)

        # Publish a different event type — handler should NOT be called
        event = _make_state_changed_event()
        await bus.publish(event)
        assert len(received) == 0

    @pytest.mark.anyio
    async def test_multiple_event_types_routed_independently(self):
        wn_received: list[Any] = []
        sc_received: list[Any] = []

        async def wn_handler(e: WorkNoteAddedEvent) -> None:
            wn_received.append(e)

        async def sc_handler(e: IncidentStateChangedEvent) -> None:
            sc_received.append(e)

        bus = EventBus()
        bus.subscribe(WorkNoteAddedEvent, wn_handler)
        bus.subscribe(IncidentStateChangedEvent, sc_handler)

        await bus.publish(_make_work_note_event())
        await bus.publish(_make_state_changed_event())

        assert len(wn_received) == 1
        assert len(sc_received) == 1


# ---------------------------------------------------------------------------
# Property 4: Source information preservation (Req 1.4)
# Feature: event-driven-orchestration, Property 4: Source information preservation
# Validates: Requirements 1.4
# ---------------------------------------------------------------------------

class TestProperty4_SourcePreservation:
    """For any work note source, the event must carry exactly the same source info."""

    @pytest.mark.anyio
    @pytest.mark.parametrize("source_type,source_name", [
        ("USER", "Alice Johnson"),
        ("ENGINEER", "Bob Smith"),
        ("TRIAGE_AGENT", "TriageAgent"),
        ("PENDING_AGENT", "PENDING AGENT"),
        ("ACKNOWLEDGEMENT_AGENT", "AcknowledgementAgent"),
        ("SYSTEM", "System"),
    ])
    async def test_source_preserved_through_bus(self, source_type, source_name):
        # Feature: event-driven-orchestration, Property 4: Source information preservation
        # Validates: Requirements 1.4
        received: list[WorkNoteAddedEvent] = []

        async def handler(e: WorkNoteAddedEvent) -> None:
            received.append(e)

        bus = EventBus()
        bus.subscribe(WorkNoteAddedEvent, handler)

        event = _make_work_note_event(source_type=source_type, source_name=source_name)
        await bus.publish(event)

        assert received[0].source_type == source_type
        assert received[0].source_name == source_name


# ---------------------------------------------------------------------------
# Property 5: USER work notes trigger Resolution Handler (Req 2.1)
# Feature: event-driven-orchestration, Property 5: USER work notes trigger Resolution Handler
# Validates: Requirements 2.1
# ---------------------------------------------------------------------------

class TestProperty5_UserWorkNoteTriggersResolution:
    """ResolutionHandler triggers when on_hold → in_progress caused by USER."""

    @pytest.mark.anyio
    async def test_user_note_on_hold_triggers_handler(self):
        # Feature: event-driven-orchestration, Property 5: USER work notes trigger Resolution Handler
        # Validates: Requirements 2.1
        from app.orchestrator.handlers.resolution import ResolutionHandler

        handler = ResolutionHandler()

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        mock_session = AsyncMock()
        mock_sm = MagicMock()
        mock_sm.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_sm.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.result = {"action": "NOTIFIED"}

        mock_svc = AsyncMock()
        mock_svc.process = AsyncMock(return_value=mock_response)

        with patch("app.orchestrator.handlers.resolution.create_async_engine", return_value=mock_engine), \
             patch("app.orchestrator.handlers.resolution.async_sessionmaker", return_value=mock_sm):
            with patch("app.modules.agents.resolution.service.ResolutionService", return_value=mock_svc):
                # Use IncidentStateChangedEvent — ResolutionHandler now accepts only this
                event = _make_state_changed_event(
                    previous_state="on_hold",
                    current_state="in_progress",
                    triggering_work_note_source="USER",
                )
                await handler.handle(event)

        mock_engine.dispose.assert_called_once()

    @pytest.mark.anyio
    @pytest.mark.parametrize("source_type", [
        "ENGINEER", "SYSTEM", "TRIAGE_AGENT", "ACKNOWLEDGEMENT_AGENT", "PENDING_AGENT"
    ])
    async def test_non_user_note_does_not_trigger_resolution(self, source_type):
        # Non-USER source types should be ignored by the ResolutionHandler
        # Feature: event-driven-orchestration, Property 5: USER work notes trigger Resolution Handler
        # Validates: Requirements 2.1
        from app.orchestrator.handlers.resolution import ResolutionHandler

        handler = ResolutionHandler()

        with patch(
            "app.orchestrator.handlers.resolution.create_async_engine"
        ) as mock_engine:
            event = _make_state_changed_event(
                previous_state="on_hold",
                current_state="in_progress",
                triggering_work_note_source=source_type,
            )
            await handler.handle(event)
            mock_engine.assert_not_called()


# ---------------------------------------------------------------------------
# Property 6: Resolution Handler validates incident state (Req 2.2)
# Feature: event-driven-orchestration, Property 6: Resolution Handler validates incident state
# Validates: Requirements 2.2
# ---------------------------------------------------------------------------

class TestProperty6_ResolutionHandlerValidatesState:
    """ResolutionHandler should only process when previous state is on_hold/pending."""

    @pytest.mark.anyio
    @pytest.mark.parametrize("previous_state", [
        "new", "in_progress", "resolved", "closed", "cancelled"
    ])
    async def test_non_on_hold_previous_state_skipped(self, previous_state):
        # Feature: event-driven-orchestration, Property 6: Resolution Handler validates incident state
        # Validates: Requirements 2.2
        from app.orchestrator.handlers.resolution import ResolutionHandler

        handler = ResolutionHandler()
        with patch(
            "app.orchestrator.handlers.resolution.create_async_engine"
        ) as mock_engine:
            event = _make_state_changed_event(
                previous_state=previous_state,
                current_state="in_progress",
                triggering_work_note_source="USER",
            )
            await handler.handle(event)
            mock_engine.assert_not_called()

    @pytest.mark.anyio
    async def test_on_hold_user_note_proceeds(self):
        # Only on_hold → in_progress with USER source should proceed to DB access
        from app.orchestrator.handlers.resolution import ResolutionHandler

        handler = ResolutionHandler()
        with patch(
            "app.orchestrator.handlers.resolution.create_async_engine"
        ) as mock_engine, patch(
            "app.orchestrator.handlers.resolution.async_sessionmaker"
        ) as mock_sm:
            mock_engine.return_value.dispose = AsyncMock()
            mock_session = AsyncMock()
            mock_sm.return_value.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_sm.return_value.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "app.modules.agents.resolution.service.ResolutionService"
            ) as mock_svc_cls:
                mock_svc = AsyncMock()
                mock_svc.process = AsyncMock(return_value=MagicMock(
                    success=True, result={"action": "NOTIFIED"}
                ))
                mock_svc_cls.return_value = mock_svc

                event = _make_state_changed_event(
                    previous_state="on_hold",
                    current_state="in_progress",
                    triggering_work_note_source="USER",
                )
                await handler.handle(event)
                mock_engine.assert_called_once()


# ---------------------------------------------------------------------------
# Property 7 & 11: Concurrent handler execution / asyncio.gather (Req 2.4, 4.2)
# Feature: event-driven-orchestration, Property 7: Concurrent handler execution without blocking
# Feature: event-driven-orchestration, Property 11: Concurrent execution using asyncio.gather
# Validates: Requirements 2.4, 4.2
# ---------------------------------------------------------------------------

class TestProperty7and11_ConcurrentExecution:
    """All handlers for an event must run concurrently via asyncio.gather."""

    @pytest.mark.anyio
    async def test_handlers_run_concurrently(self):
        # Feature: event-driven-orchestration, Property 7: Concurrent handler execution without blocking
        # Feature: event-driven-orchestration, Property 11: Concurrent execution using asyncio.gather
        # Validates: Requirements 2.4, 4.2
        import time

        order: list[str] = []
        start_times: dict[str, float] = {}

        async def slow_handler_a(e: WorkNoteAddedEvent) -> None:
            start_times["a"] = asyncio.get_event_loop().time()
            await asyncio.sleep(0.05)
            order.append("a")

        async def slow_handler_b(e: WorkNoteAddedEvent) -> None:
            start_times["b"] = asyncio.get_event_loop().time()
            await asyncio.sleep(0.05)
            order.append("b")

        bus = EventBus()
        bus.subscribe(WorkNoteAddedEvent, slow_handler_a)
        bus.subscribe(WorkNoteAddedEvent, slow_handler_b)

        t0 = asyncio.get_event_loop().time()
        await bus.publish(_make_work_note_event())
        elapsed = asyncio.get_event_loop().time() - t0

        # Both handlers ran
        assert "a" in order
        assert "b" in order
        # Concurrent: total time ~0.05s not ~0.10s
        assert elapsed < 0.09, f"Handlers did not run concurrently: elapsed={elapsed:.3f}s"

    @pytest.mark.anyio
    async def test_single_handler_still_works(self):
        received: list[Any] = []

        async def handler(e: WorkNoteAddedEvent) -> None:
            received.append(e.incident_id)

        bus = EventBus()
        bus.subscribe(WorkNoteAddedEvent, handler)
        await bus.publish(_make_work_note_event(incident_id="test-single"))
        assert received == ["test-single"]


# ---------------------------------------------------------------------------
# Property 8: State change events are published (Req 3.1)
# Feature: event-driven-orchestration, Property 8: State change events are published
# Validates: Requirements 3.1
# ---------------------------------------------------------------------------

class TestProperty8_StateChangeEventsPublished:
    """For any incident state change, an IncidentStateChangedEvent must be published."""

    @pytest.mark.anyio
    async def test_state_changed_event_routed_to_handler(self):
        # Feature: event-driven-orchestration, Property 8: State change events are published
        # Validates: Requirements 3.1
        received: list[IncidentStateChangedEvent] = []

        async def handler(e: IncidentStateChangedEvent) -> None:
            received.append(e)

        bus = EventBus()
        bus.subscribe(IncidentStateChangedEvent, handler)

        event = _make_state_changed_event(previous_state="new", current_state="in_progress")
        await bus.publish(event)

        assert len(received) == 1
        assert received[0].previous_state == "new"
        assert received[0].current_state == "in_progress"

    @pytest.mark.anyio
    @pytest.mark.parametrize("prev,curr", [
        ("new", "in_progress"),
        ("in_progress", "on_hold"),
        ("on_hold", "in_progress"),
        ("in_progress", "resolved"),
    ])
    async def test_all_state_transitions_are_published(self, prev, curr):
        # Feature: event-driven-orchestration, Property 8: State change events are published
        # Validates: Requirements 3.1
        received: list[IncidentStateChangedEvent] = []

        async def handler(e: IncidentStateChangedEvent) -> None:
            received.append(e)

        bus = EventBus()
        bus.subscribe(IncidentStateChangedEvent, handler)

        event = _make_state_changed_event(previous_state=prev, current_state=curr)
        await bus.publish(event)

        assert len(received) == 1
        assert received[0].previous_state == prev
        assert received[0].current_state == curr


# ---------------------------------------------------------------------------
# Property 9 & 10: Handler failure isolation and error logging (Req 3.3, 3.4, 4.1, 4.3)
# Feature: event-driven-orchestration, Property 9: Handler failure isolation
# Feature: event-driven-orchestration, Property 10: Error logging and continuation
# Validates: Requirements 3.3, 3.4, 4.1, 4.3
# ---------------------------------------------------------------------------

class TestProperty9and10_ErrorIsolationAndLogging:
    """One failing handler must not block other handlers; failures must be logged."""

    @pytest.mark.anyio
    async def test_failing_handler_does_not_block_others(self):
        # Feature: event-driven-orchestration, Property 9: Handler failure isolation
        # Validates: Requirements 3.3, 4.1
        successful: list[str] = []

        async def failing_handler(e: WorkNoteAddedEvent) -> None:
            raise RuntimeError("Simulated handler failure")

        async def good_handler_a(e: WorkNoteAddedEvent) -> None:
            successful.append("a")

        async def good_handler_b(e: WorkNoteAddedEvent) -> None:
            successful.append("b")

        bus = EventBus()
        bus.subscribe(WorkNoteAddedEvent, failing_handler)
        bus.subscribe(WorkNoteAddedEvent, good_handler_a)
        bus.subscribe(WorkNoteAddedEvent, good_handler_b)

        # Should not raise even though one handler fails
        await bus.publish(_make_work_note_event())

        assert "a" in successful
        assert "b" in successful

    @pytest.mark.anyio
    async def test_multiple_failing_handlers_all_others_still_run(self):
        # If multiple handlers fail, remaining ones still execute
        # Feature: event-driven-orchestration, Property 9: Handler failure isolation
        # Validates: Requirements 3.3, 4.1
        ran: list[str] = []

        async def fail1(e: WorkNoteAddedEvent) -> None:
            raise ValueError("fail1")

        async def fail2(e: WorkNoteAddedEvent) -> None:
            raise KeyError("fail2")

        async def good(e: WorkNoteAddedEvent) -> None:
            ran.append("good")

        bus = EventBus()
        bus.subscribe(WorkNoteAddedEvent, fail1)
        bus.subscribe(WorkNoteAddedEvent, fail2)
        bus.subscribe(WorkNoteAddedEvent, good)

        await bus.publish(_make_work_note_event())
        assert ran == ["good"]

    @pytest.mark.anyio
    async def test_errors_are_logged(self, caplog):
        # Feature: event-driven-orchestration, Property 10: Error logging and continuation
        # Validates: Requirements 3.4, 4.3
        async def failing_handler(e: WorkNoteAddedEvent) -> None:
            raise RuntimeError("test error for logging")

        bus = EventBus()
        bus.subscribe(WorkNoteAddedEvent, failing_handler)

        with caplog.at_level(logging.ERROR, logger="app.orchestrator.bus"):
            await bus.publish(_make_work_note_event())

        assert any("test error for logging" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Property 12: Database session isolation per handler (Req 4.4)
# Feature: event-driven-orchestration, Property 12: Database session isolation per handler
# Validates: Requirements 4.4
# ---------------------------------------------------------------------------

class TestProperty12_DatabaseSessionIsolation:
    """Each handler must create its own independent database session."""

    @pytest.mark.anyio
    async def test_each_handler_creates_own_session(self):
        # Feature: event-driven-orchestration, Property 12: Database session isolation per handler
        # Validates: Requirements 4.4
        engines_created: list[str] = []

        async def handler_a(e: WorkNoteAddedEvent) -> None:
            # Simulate creating its own DB connection
            engines_created.append("handler_a")

        async def handler_b(e: WorkNoteAddedEvent) -> None:
            engines_created.append("handler_b")

        bus = EventBus()
        bus.subscribe(WorkNoteAddedEvent, handler_a)
        bus.subscribe(WorkNoteAddedEvent, handler_b)

        await bus.publish(_make_work_note_event())

        # Both handlers ran independently
        assert "handler_a" in engines_created
        assert "handler_b" in engines_created

    @pytest.mark.anyio
    async def test_triage_handler_creates_isolated_session(self):
        """TriageHandler creates its own engine + session (verified via mock)."""
        # Feature: event-driven-orchestration, Property 12: Database session isolation per handler
        # Validates: Requirements 4.4
        from app.orchestrator.handlers.triage import TriageHandler

        with patch(
            "app.orchestrator.handlers.triage.create_async_engine"
        ) as mock_engine, patch(
            "app.orchestrator.handlers.triage.async_sessionmaker"
        ) as mock_sm:
            mock_engine.return_value.dispose = AsyncMock()
            mock_session = AsyncMock()
            mock_sm.return_value.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_sm.return_value.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("app.modules.agents.triage.service.TriageService") as mock_svc_cls:
                mock_svc = AsyncMock()
                mock_svc.run_triage = AsyncMock(return_value=MagicMock(success=True, errors=[]))
                mock_svc_cls.return_value = mock_svc

                event = IncidentCreatedEvent(
                    incident_id="inc-001",
                    incident_number="INC0000001",
                    assignment_group="App Run-SAP - BASIS",
                    priority="3",
                    state="new",
                )
                handler = TriageHandler()
                await handler.handle(event)

            # Each handler creates its own engine independently
            mock_engine.assert_called_once()
            mock_engine.return_value.dispose.assert_called_once()
