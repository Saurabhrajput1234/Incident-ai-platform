# Event-Driven Orchestration Layer — Design Document

## Problem: Current Direct-Call Architecture

Today, agents are invoked by **direct function calls** hardcoded across the codebase:

```
incidents.py      → _auto_triage() → TriageService.run_triage()
triage/service.py → AcknowledgementService.process_acknowledgement()
ack/service.py    → PendingService.process_pending_transition()
work_notes        → ResolutionService.process()
```

**Problems with this:**
- Tight coupling — adding a new agent means editing existing service files
- No central visibility of what triggered what
- No retry or error isolation between agent transitions
- Triage directly calls Acknowledgement. Acknowledgement directly calls Pending. Hard to change the chain
- Background tasks create their own DB sessions inconsistently
- No way to replay or audit what events fired

---

## Solution: In-Process Event Bus Orchestration

Replace direct calls with a **lightweight in-process event bus** that:
- Decouples agents from each other — no agent knows about the next one
- Centralizes all agent-triggering logic in one place (`orchestrator/`)
- Allows adding/removing/reordering agents without touching agent code
- Provides a full event audit log in the database
- Supports retry logic per event type

**No external message queue required** (no Redis, no RabbitMQ). This is a pure Python async event bus backed by PostgreSQL for persistence/audit. Simple, reliable, zero new infrastructure.

---

## Architecture Overview

```
                    ┌─────────────────────────────┐
                    │         Event Bus            │
                    │  (in-process async queue)    │
                    └────────────┬────────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
    ┌─────▼──────┐        ┌──────▼─────┐        ┌──────▼──────┐
    │  incident  │        │  incident  │        │  work_note  │
    │  .created  │        │  .updated  │        │   .added    │
    └─────┬──────┘        └──────┬─────┘        └──────┬──────┘
          │                      │                      │
          ▼                      ▼                      ▼
   TriageHandler          StateChangeHandler     WorkNoteHandler
          │                      │                      │
          ▼                      ▼                      ▼
   TriageService        AcknowledgementService   ResolutionService
                        PendingService
```

---

## Event Types

All events are plain Python dataclasses. No serialization required for in-process delivery.

```python
# orchestrator/events.py

@dataclass
class IncidentCreatedEvent:
    incident_id: str
    incident_number: str
    assignment_group: str | None
    priority: str
    state: str
    created_at: datetime

@dataclass
class IncidentStateChangedEvent:
    incident_id: str
    incident_number: str
    previous_state: str
    current_state: str
    changed_by: str          # "system", "engineer", "agent_name"
    triggering_work_note_id: str | None
    triggering_work_note_source: str | None
    changed_at: datetime

@dataclass
class WorkNoteAddedEvent:
    incident_id: str
    incident_number: str
    work_note_id: str
    source_type: str          # USER, ENGINEER, TRIAGE_AGENT, etc.
    source_name: str
    action_type: str
    added_at: datetime
```

---

## Event Handlers (Who Listens to What)

| Event | Handler | Agent Triggered | Condition |
|-------|---------|----------------|-----------|
| `IncidentCreatedEvent` | `TriageHandler` | TriageService | Always (state=new) |
| `IncidentStateChangedEvent` | `AcknowledgementHandler` | AcknowledgementService | `new/in_progress → in_progress` AND assigned_to is set |
| `IncidentStateChangedEvent` | `PendingHandler` | PendingService | `* → on_hold` |
| `IncidentStateChangedEvent` | `ResolutionHandler` | ResolutionService | `on_hold → active` |
| `WorkNoteAddedEvent` | `ResolutionHandler` | ResolutionService | source_type=USER AND state=on_hold |

---

## File Structure

```
backend/app/
└── orchestrator/
    ├── __init__.py
    ├── bus.py              EventBus — register handlers, publish events
    ├── events.py           All event dataclasses (IncidentCreatedEvent, etc.)
    ├── handlers/
    │   ├── __init__.py
    │   ├── triage.py       TriageHandler — listens to IncidentCreatedEvent
    │   ├── acknowledgement.py  AcknowledgementHandler — listens to IncidentStateChangedEvent
    │   ├── pending.py      PendingHandler — listens to IncidentStateChangedEvent
    │   └── resolution.py   ResolutionHandler — listens to IncidentStateChangedEvent + WorkNoteAddedEvent
    └── registry.py         Wires bus + handlers together, called from lifecycle.py
```

---

## EventBus Implementation

```python
# orchestrator/bus.py

class EventBus:
    """
    Lightweight in-process async event bus.
    Handlers are registered per event type.
    All handlers for an event run concurrently (asyncio.gather).
    Errors in one handler do NOT block other handlers.
    """

    _handlers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: Any) -> None:
        handlers = self._handlers.get(type(event), [])
        if not handlers:
            return
        results = await asyncio.gather(
            *[handler(event) for handler in handlers],
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Handler %s failed for event %s: %s",
                    handlers[i].__name__, type(event).__name__, result,
                )

# Singleton
event_bus = EventBus()
```

---

## Handler Example: TriageHandler

```python
# orchestrator/handlers/triage.py

class TriageHandler:
    """Handles IncidentCreatedEvent → triggers TriageService."""

    async def handle(self, event: IncidentCreatedEvent) -> None:
        if event.state not in ("new",):
            return

        engine = create_async_engine(settings.DATABASE_URL, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        try:
            async with session_factory() as db:
                service = TriageService(db)
                response = await service.run_triage(incident_id=event.incident_id)
                logger.info(
                    "[TriageHandler] %s — success=%s",
                    event.incident_number, response.success,
                )
        except Exception as exc:
            logger.error("[TriageHandler] %s failed: %s", event.incident_id, exc)
        finally:
            await engine.dispose()
```

---

## How Events Get Published

Events are published from **service layer** — not from API endpoints or agents directly.

### IncidentCreatedEvent → published from IncidentService.create_incident()

```python
# incidents/service.py — after creating the incident

incident = await self.repo.create(payload)
await event_bus.publish(IncidentCreatedEvent(
    incident_id=incident.id,
    incident_number=incident.incident_number,
    assignment_group=incident.assignment_group,
    priority=incident.priority,
    state=incident.state,
    created_at=incident.created_at,
))
return incident
```

### IncidentStateChangedEvent → published from IncidentService.update_incident_internal()

```python
# incidents/service.py — after any state update

if old_state != new_state:
    await event_bus.publish(IncidentStateChangedEvent(
        incident_id=incident.id,
        incident_number=incident.incident_number,
        previous_state=old_state,
        current_state=new_state,
        changed_by=changed_by,
        triggering_work_note_id=triggering_work_note_id,
        triggering_work_note_source=triggering_work_note_source,
        changed_at=datetime.now(timezone.utc),
    ))
```

### WorkNoteAddedEvent → published from WorkNoteService.add_note()

```python
# work_notes/service.py — after creating the note

await event_bus.publish(WorkNoteAddedEvent(
    incident_id=note.incident_id,
    work_note_id=note.id,
    source_type=source_type.value,
    source_name=source_name,
    action_type=action_type.value,
    added_at=note.created_at,
))
```

---

## What Gets Removed

After this change, the following direct calls are **deleted**:

| Location | Line Removed |
|----------|-------------|
| `api/v1/incidents.py` | `background_tasks.add_task(_auto_triage, ...)` |
| `api/v1/incidents.py` | `_auto_triage()` function entirely |
| `triage/service.py` | `AcknowledgementService.process_acknowledgement(incident.id)` |
| `acknowledgement/service.py` | `PendingService.process_pending_transition(incident_id=incident.id)` |
| `work_notes/service.py` | `ResolutionService.process(trigger)` |

Each of these is **replaced by a published event** from the appropriate service.

---

## Wiring (Lifecycle)

The bus is configured once at startup in `registry.py`, called from `lifecycle.py`:

```python
# orchestrator/registry.py

def register_all_handlers(bus: EventBus) -> None:
    from app.orchestrator.handlers.triage import TriageHandler
    from app.orchestrator.handlers.acknowledgement import AcknowledgementHandler
    from app.orchestrator.handlers.pending import PendingHandler
    from app.orchestrator.handlers.resolution import ResolutionHandler

    bus.subscribe(IncidentCreatedEvent, TriageHandler().handle)
    bus.subscribe(IncidentStateChangedEvent, AcknowledgementHandler().handle)
    bus.subscribe(IncidentStateChangedEvent, PendingHandler().handle)
    bus.subscribe(IncidentStateChangedEvent, ResolutionHandler().handle)
    bus.subscribe(WorkNoteAddedEvent, ResolutionHandler().handle)
```

```python
# core/lifecycle.py — startup

register_all_handlers(event_bus)
scheduler_task = asyncio.create_task(start_pending_reminder_scheduler(...))
```

---

## Event Flow After Implementation

```
POST /v1/incidents
        │
        ▼
IncidentService.create_incident()
        │
        ├─── saves incident to DB
        │
        └─── publishes IncidentCreatedEvent
                        │
                        ▼
               [EventBus dispatches]
                        │
                        ▼
               TriageHandler.handle()
                        │
                        ▼
               TriageService.run_triage()
                        │
                        └─── incident.state: new → in_progress
                             incident.assigned_to: Engineer
                             publishes IncidentStateChangedEvent(new → in_progress)
                                        │
                                        ▼
                               AcknowledgementHandler.handle()
                                        │
                                        ▼
                               AcknowledgementService.process_acknowledgement()
                                        │
                                        └─── state: in_progress → on_hold (if special request)
                                             publishes IncidentStateChangedEvent(in_progress → on_hold)
                                                        │
                                                        ▼
                                               PendingHandler.handle()
                                                        │
                                                        ▼
                                               PendingService.process_pending_transition()
                                                        │
                                                        └─── creates PendingCycle, schedules Reminder 1


USER adds work note → state: on_hold → active
        │
        ▼
WorkNoteService.add_note()
        │
        └─── publishes WorkNoteAddedEvent(source=USER)
                        │
                        ▼
               ResolutionHandler.handle()
                        │
                        ▼
               ResolutionService.process()
                        │
                        └─── analyzes response, auto-resolves if eligible
```

---

## Event Audit Log (Optional Enhancement)

Persist every published event to `orchestrator_events` table for full traceability:

```sql
CREATE TABLE orchestrator_events (
    id          UUID PRIMARY KEY,
    event_type  VARCHAR(100) NOT NULL,
    incident_id UUID,
    payload     JSONB NOT NULL,
    published_at TIMESTAMPTZ DEFAULT now(),
    handlers_run INTEGER DEFAULT 0,
    handlers_failed INTEGER DEFAULT 0
);
```

This gives you a full timeline of: what happened, when, what triggered what.

---

## What Does NOT Change

- **Agent logic is untouched** — TriageService, AcknowledgementService, PendingService, ResolutionService stay exactly the same
- **API contracts unchanged** — all REST endpoints work the same
- **Database schema** — no changes to existing tables (audit log is optional)
- **Pending scheduler** — still polls DB directly (unchanged)
- **LLMService** — unchanged

---

## Implementation Phases

### Phase 1 — Core Bus + TriageHandler
- Create `orchestrator/bus.py`, `orchestrator/events.py`
- Create `TriageHandler`
- Publish `IncidentCreatedEvent` from `IncidentService`
- Remove `_auto_triage()` background task from `incidents.py`
- Register handler in `lifecycle.py`

### Phase 2 — State Change Events + ACK/Pending Handlers
- Publish `IncidentStateChangedEvent` from `IncidentService.update_incident_internal()`
- Create `AcknowledgementHandler` and `PendingHandler`
- Remove direct ACK call from `triage/service.py`
- Remove direct Pending call from `acknowledgement/service.py`

### Phase 3 — WorkNote Events + Resolution Handler
- Publish `WorkNoteAddedEvent` from `WorkNoteService.add_note()`
- Create `ResolutionHandler`
- Remove direct Resolution call from `work_notes/service.py`
- Register handler in registry

### Phase 4 (Optional) — Event Audit Log
- Add `orchestrator_events` table + Alembic migration
- Persist events in `EventBus.publish()` before dispatching handlers

---

## Summary

| Aspect | Before | After |
|--------|--------|-------|
| Agent chaining | Hardcoded direct calls in each service | Event handlers in `orchestrator/handlers/` |
| Adding new agent | Edit existing service files | Add new handler + subscribe to event |
| Visibility | No central trace | Event bus log + optional DB audit |
| Coupling | Triage knows about ACK, ACK knows about Pending | No agent knows about any other |
| Error isolation | One agent failure can cascade | Each handler error is isolated |
| Infrastructure | None | None (pure Python, no Redis/Kafka) |
