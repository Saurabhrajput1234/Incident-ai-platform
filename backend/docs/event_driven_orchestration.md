# Event-Driven Orchestration — Complete Technical Reference

## What Is This?

The platform uses an **in-process async event bus** to coordinate four AI agents.
Agents never call each other directly. Instead, services publish domain events and
the orchestrator decides which agent to run.

```
Service → publishes Event → EventBus → dispatches to Handler → runs Agent
```

No Redis, no RabbitMQ, no external infrastructure. Pure Python asyncio.

---

## File-by-File Reference

### `app/orchestrator/bus.py` — The Event Bus

**What it does:** Routes events to registered handlers concurrently.

```python
class EventBus:
    def __init__(self):
        self._handlers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable) -> None:
        # Register a handler for an event type
        self._handlers[event_type].append(handler)

    async def publish(self, event: Any) -> None:
        # Find all handlers for this event type
        # Run them ALL concurrently using asyncio.gather
        # One handler failing does NOT block the others
        handlers = self._handlers.get(type(event), [])
        results = await asyncio.gather(
            *[handler(event) for handler in handlers],
            return_exceptions=True,
        )
        # Log errors from any failed handler
        for handler, result in zip(handlers, results):
            if isinstance(result, Exception):
                logger.error("[EventBus] Handler %s failed: %s", handler.__qualname__, result)

event_bus = EventBus()  # singleton — imported everywhere
```

**Key rules:**
- All handlers for one event run concurrently (not sequentially)
- Errors in one handler never stop other handlers
- `event_bus` is a module-level singleton — same instance used everywhere

---

### `app/orchestrator/events.py` — Domain Events (Data)

**What it does:** Defines what data each event carries. Plain Python dataclasses — no serialization.

```python
@dataclass
class IncidentCreatedEvent:
    # Published by: IncidentService.create_incident()
    # Triggers:     TriageHandler
    incident_id: str
    incident_number: str
    assignment_group: str | None
    priority: str
    state: str                        # "new"
    created_at: datetime

@dataclass
class IncidentStateChangedEvent:
    # Published by: IncidentService (all state transitions)
    # Triggers:     AcknowledgementHandler, PendingHandler, ResolutionHandler
    incident_id: str
    incident_number: str
    previous_state: str               # e.g. "new", "in_progress", "on_hold"
    current_state: str                # e.g. "in_progress", "on_hold", "resolved"
    changed_by: str                   # "system" / "engineer" / "TriageAgent" / "PendingAgent" / etc.
    triggering_work_note_id: str | None   # ID of the work note that caused this (if any)
    triggering_work_note_source: str | None  # "USER" / "PENDING_AGENT" / etc.
    changed_at: datetime

@dataclass
class WorkNoteAddedEvent:
    # Published by: WorkNoteService.add_note()
    # Currently:    No handler subscribed (published but not consumed)
    # Future use:   Additional handlers can subscribe without changing WorkNoteService
    incident_id: str
    incident_number: str
    work_note_id: str
    source_type: str                  # "USER" / "ENGINEER" / "TRIAGE_AGENT" / etc.
    source_name: str
    action_type: str
    incident_state: str               # snapshot of state BEFORE any auto-activation
    added_at: datetime
```

---

### `app/orchestrator/registry.py` — Wiring (Orchestration Rules)

**What it does:** The single place where ALL orchestration rules live. Called once at startup.

```python
def register_all_handlers(bus: EventBus) -> None:

    # RULE 1: New incident → run Triage
    bus.subscribe(IncidentCreatedEvent, TriageHandler().handle)

    # RULE 2: Triage moves incident to in_progress → run Acknowledgement
    bus.subscribe(IncidentStateChangedEvent, AcknowledgementHandler().handle)

    # RULE 3: Any agent moves incident to on_hold → start Pending reminder cycle
    bus.subscribe(IncidentStateChangedEvent, PendingHandler().handle)

    # RULE 4: User work note activates incident from on_hold → run Resolution Alert
    bus.subscribe(IncidentStateChangedEvent, ResolutionHandler().handle)
```

**This is the only place that controls which agent runs when.**
Adding a new agent = add one `bus.subscribe()` line here. No existing code changes needed.

---

### `app/orchestrator/handlers/triage.py` — Triage Handler

**What it does:** Listens for new incidents and runs the Triage Agent.

```python
class TriageHandler:
    async def handle(self, event: IncidentCreatedEvent) -> None:
        # Condition: only run for brand-new incidents
        if event.state != "new":
            return

        # Create isolated DB session (handlers run concurrently — no shared state)
        engine = create_async_engine(settings.DATABASE_URL)
        async with session_factory() as db:
            response = await TriageService(db).run_triage(incident_id=event.incident_id)
```

**Condition check:** `state == "new"`
**Calls:** `TriageService.run_triage()`

---

### `app/orchestrator/handlers/acknowledgement.py` — Acknowledgement Handler

**What it does:** Listens for Triage completing and runs the Acknowledgement Agent.

```python
class AcknowledgementHandler:
    async def handle(self, event: IncidentStateChangedEvent) -> None:
        # Condition 1: state must be in_progress
        if event.current_state != "in_progress":
            return
        # Condition 2: ONLY trigger when TriageAgent caused the change
        # (not manual engineer updates or other agents)
        if event.changed_by != "TriageAgent":
            return

        async with session_factory() as db:
            response = await AcknowledgementService(db).process_acknowledgement(
                incident_id=event.incident_id
            )
```

**Condition check:** `current == "in_progress"` AND `changed_by == "TriageAgent"`
**Why `changed_by` check:** Prevents ACK from firing every time any agent sets in_progress.
**Calls:** `AcknowledgementService.process_acknowledgement()`

---

### `app/orchestrator/handlers/pending.py` — Pending Handler

**What it does:** Listens for on_hold transitions and starts the reminder cycle.

```python
class PendingHandler:
    async def handle(self, event: IncidentStateChangedEvent) -> None:
        # Condition 1: state must be on_hold
        if event.current_state not in ("on_hold", "pending"):
            return
        # Condition 2: skip if PendingAgent caused it (avoids infinite loops)
        # PendingAgent sets on_hold after each reminder — we must not create a new cycle
        if event.changed_by in ("PendingAgent", "PENDING AGENT"):
            return

        async with session_factory() as db:
            response = await PendingService(db).process_pending_transition(
                incident_id=event.incident_id
            )
```

**Condition check:** `current == "on_hold"` AND `changed_by != "PendingAgent"`
**Loop prevention:** `changed_by="PendingAgent"` guard stops infinite reminder loops.
**Calls:** `PendingService.process_pending_transition(force_reminder=False)`

---

### `app/orchestrator/handlers/resolution.py` — Resolution Handler

**What it does:** Listens for user replies (on_hold → in_progress) and runs the Resolution Agent.

```python
_NON_USER_SOURCES = {"PENDING_AGENT", "ACKNOWLEDGEMENT_AGENT", "TRIAGE_AGENT", "SYSTEM"}

class ResolutionHandler:
    async def handle(self, event: IncidentStateChangedEvent) -> None:
        # Condition 1: must be on_hold → in_progress transition
        if event.previous_state != "on_hold":
            return
        if event.current_state not in {"in_progress", "active"}:
            return
        # Condition 2: skip if triggered by an agent (not a user)
        # PENDING_AGENT sends reminders → auto-activates → we must NOT run Resolution
        if event.triggering_work_note_source in _NON_USER_SOURCES:
            return
        # None source = manual engineer state change → let ResolutionService decide

        async with session_factory() as db:
            trigger = ResolutionTrigger(
                incident_id=event.incident_id,
                previous_state=event.previous_state,
                current_state="active",
                triggering_work_note_id=event.triggering_work_note_id,
                triggering_work_note_source=event.triggering_work_note_source,
            )
            response = await ResolutionService(db).process(trigger)
```

**Condition check:** `previous == "on_hold"` AND `current == "in_progress"` AND `source NOT IN non-user sources`
**Why this fires AFTER state change:** State change event publishes after `in_progress` is saved → Resolution runs AFTER the audit trail is correct.
**Calls:** `ResolutionService.process(trigger)`

---

### `app/core/lifecycle.py` — Startup Wiring

**What it does:** Registers all handlers once when the app starts. Also starts the background scheduler.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Wire all event handlers to the bus
    register_all_handlers(event_bus)

    # Start the background scheduler for pending reminders
    scheduler_task = asyncio.create_task(
        start_pending_reminder_scheduler(poll_interval_seconds=10)
    )
    yield
    # Clean shutdown
    scheduler_task.cancel()
```

---

## Where Events Are Published

### `app/modules/incidents/service.py`

```python
# create_incident() — after row is saved
await event_bus.publish(IncidentCreatedEvent(
    incident_id=incident.id,
    incident_number=incident.incident_number,
    state="new",
    ...
))

# update_incident_internal() — after ANY state change
if new_state != old_state:
    await event_bus.publish(IncidentStateChangedEvent(
        previous_state=old_state,
        current_state=new_state,
        changed_by=changed_by,           # "TriageAgent", "PendingAgent", "system", etc.
        triggering_work_note_id=...,     # passed through from WorkNoteService
        triggering_work_note_source=..., # "USER", "PENDING_AGENT", etc.
    ))

# activate_incident_from_work_note() — when WorkNoteService auto-activates
# Called by WorkNoteService after a note triggers on_hold → in_progress
await event_bus.publish(IncidentStateChangedEvent(
    previous_state=old_state,
    current_state="in_progress",
    changed_by=triggered_by,
    triggering_work_note_id=triggering_work_note_id,
    triggering_work_note_source=triggering_work_note_source,
))
```

### `app/modules/work_notes/service.py`

```python
async def add_note(self, incident_id, message, source_type, source_name,
                   action_type=None, auto_activate=True) -> WorkNoteResponse:

    # Step 1: Save the note
    note = await self.repo.create(...)

    # Step 2: Fetch incident state snapshot (BEFORE auto-activation)
    incident_state, incident_number = await self._get_incident_state_and_number(incident_id)

    # Step 3: Publish WorkNoteAddedEvent (currently no handler subscribed)
    await event_bus.publish(WorkNoteAddedEvent(
        incident_id=incident_id,
        incident_number=incident_number,
        work_note_id=note.id,
        source_type=source_type_val,     # "USER", "PENDING_AGENT", etc.
        incident_state=incident_state,   # snapshot BEFORE activation
    ))

    # Step 4: Auto-activate if enabled (triggers IncidentStateChangedEvent internally)
    if auto_activate:
        await self._maybe_activate_incident(
            incident_id=incident_id,
            triggered_by=source_name,
            triggering_work_note_id=note.id,
            triggering_work_note_source=source_type_val,
        )
```

**Key:** `triggering_work_note_id` and `triggering_work_note_source` travel through the entire chain:
```
WorkNoteService.add_note()
  → IncidentService.activate_incident_from_work_note(triggering_work_note_id, triggering_work_note_source)
    → event_bus.publish(IncidentStateChangedEvent(triggering_work_note_source="USER"))
      → ResolutionHandler checks: source="USER" → runs Resolution
```

---

## Complete Lifecycle Walkthrough

### Step 1 — Incident Created (state: `new`)

```
POST /v1/incidents
  ↓
IncidentService.create_incident()
  ↓ saves incident (state=new)
  ↓ writes INCIDENT_CREATE work note
  ↓ publishes IncidentCreatedEvent(state="new")
  ↓
EventBus dispatches to:
  → TriageHandler ✓ (state=new)
```

### Step 2 — Triage (state: `new` → `in_progress`)

```
TriageService.run_triage()
  ↓
  Step 1: LLM resolves assignment group
    → update_incident_internal(assignment_group=X)  [no state change, no event]
    → writes GROUP_RESOLVED work note
  ↓
  Step 2-4: Build context, validate engineers, round-robin assign
  ↓
  Step 5a: update_incident_internal(assigned_to="Eng Name")  [no state change]
  ↓
  Step 5b: writes ASSIGN_ENGINEER work note  ← COMMITTED BEFORE state change
  ↓
  Step 5c: update_incident_internal(state="in_progress", changed_by="TriageAgent")
    → publishes IncidentStateChangedEvent(new→in_progress, changed_by="TriageAgent")
    ↓
    EventBus dispatches to:
      → AcknowledgementHandler ✓ (in_progress + TriageAgent)
      → PendingHandler ✗ (not on_hold)
      → ResolutionHandler ✗ (previous != on_hold)
```

**Work notes at this point:**
```
INCIDENT_CREATE   System
GROUP_RESOLVED    TriageAgent
ASSIGN_ENGINEER   TriageAgent   ← before state change (correct order)
```

### Step 3 — Acknowledgement (state: stays `in_progress` or → `on_hold`)

```
AcknowledgementService.process_acknowledgement()
  ↓
  LLM classifies intent:
    STANDARD_INCIDENT → state stays in_progress → no Pending cycle
    ACCESS_REQUEST / SERVICE_REQUEST / WRONG_REQUEST / SALESFORCE_INCORRECT_REQUEST
      → update_incident_internal(state="on_hold", changed_by="AcknowledgementAgent")
        → publishes IncidentStateChangedEvent(in_progress→on_hold)
        ↓
        EventBus dispatches to:
          → PendingHandler ✓ (on_hold, changed_by != PendingAgent)
          → ResolutionHandler ✗ (previous != on_hold)
          → AcknowledgementHandler ✗ (not in_progress)
  ↓
  writes SEND_ACKNOWLEDGEMENT work note (auto_activate=False)
```

### Step 4 — Pending Reminders (state: stays `on_hold`)

```
PendingService.process_pending_transition(force_reminder=False)
  ↓
  Creates PendingCycle(max_reminders=3)
  Sets next_reminder_at = now + REMINDER_INTERVAL_SECONDS

[Background Scheduler polls every 10s]
  ↓  when next_reminder_at is due:
PendingService.process_pending_transition(force_reminder=True)
  ↓
  For each reminder (1, 2, 3):
    ① Render email
    ② add_note(SEND_REMINDER, auto_activate=True)
         → auto-activates: on_hold → in_progress
         → publishes IncidentStateChangedEvent(on_hold→in_progress, source="PENDING_AGENT")
         → ResolutionHandler ✗ (source=PENDING_AGENT in _NON_USER_SOURCES → skipped)
    ③ update_incident_internal(state="on_hold", changed_by="PendingAgent")
         → publishes IncidentStateChangedEvent(in_progress→on_hold, changed_by="PendingAgent")
         → PendingHandler ✗ (changed_by="PendingAgent" → skipped)
    ④ add_note(STATE_CHANGE, auto_activate=False)
         → "State restored to On Hold after reminder N sent"
    ⑤ If final reminder (3/3): complete_cycle() → incident stays on_hold
```

**Work notes per reminder:**
```
PENDING AGENT | SEND_REMINDER   — reminder email content
System        | STATE_CHANGE    — "Incident automatically moved to In Progress"
PENDING AGENT | STATE_CHANGE    — "State restored to On Hold after reminder N sent"
```

### Step 5 — User Replies (state: `on_hold` → `in_progress`)

```
User adds work note via API
  ↓
WorkNoteService.add_note(source_type=USER, auto_activate=True)
  ↓
  ① saves note
  ② publishes WorkNoteAddedEvent(source="USER", incident_state="on_hold")
       [no handler subscribed currently]
  ③ auto-activates via IncidentService.activate_incident_from_work_note()
       → on_hold → in_progress
       → writes STATE_CHANGE audit note: "Incident automatically moved to In Progress"
       → publishes IncidentStateChangedEvent(
             previous="on_hold",
             current="in_progress",
             triggering_work_note_source="USER",  ← carries the source through
             triggering_work_note_id=<note_id>
         )
  ↓
  EventBus dispatches to:
    → ResolutionHandler ✓ (on_hold→in_progress, source=USER)
    → PendingHandler ✗ (not on_hold)
    → AcknowledgementHandler ✗ (changed_by != TriageAgent)
```

### Step 6 — Resolution Alert (state: `in_progress` → `resolved` or stays)

```
ResolutionService.process(trigger)
  ↓
  ① Validate: previous=on_hold, source=USER ✓
  ② Load triggering work note by ID (user's note, not the SYSTEM audit note)
  ③ Cancel active PendingCycle (user responded — no more reminders)
  ④ LLM classifies user intent:
       POSITIVE: ISSUE_RESOLVED / REQUEST_COMPLETED / REQUIRED_ACTION_COMPLETED
       NEGATIVE: ESCALATION_REQUIRED / CLARIFICATION_NEEDED / REJECTED
  ⑤ Check provenance:
       Requires: non-standard ACK template note exists
       Blocks if: ENGINEER note exists AFTER the ACK note
  ⑥ Send Teams notification → assigned engineer (always)
  ⑦ If POSITIVE → Send Email → assignment group
  ⑧ If POSITIVE + provenance confirmed:
       → update_incident_internal(state="resolved")
       → writes STATE_CHANGE: "Incident auto-resolved"
```

**Work notes:**
```
User          | MANUAL_NOTE      — user's reply
System        | STATE_CHANGE     — "Incident automatically moved to In Progress"
ResolutionAgent | SEND_ACK       — [TEAMS] notification to engineer
ResolutionAgent | SEND_ACK       — [EMAIL] notification to group (if positive)
ResolutionAgent | STATE_CHANGE   — "Incident auto-resolved" (if positive + provenance)
```

---

## Loop Prevention Summary

| Scenario | Event | Filter | Result |
|----------|-------|--------|--------|
| Pending reminder → don't start new cycle | `IncidentStateChangedEvent(→on_hold, changed_by="PendingAgent")` | `PendingHandler`: `changed_by in ("PendingAgent")` | Skip ✗ |
| Pending restore ON_HOLD → don't start cycle | Same as above | Same | Skip ✗ |
| Pending SEND_REMINDER auto-activates → don't run Resolution | `IncidentStateChangedEvent(→in_progress, source="PENDING_AGENT")` | `ResolutionHandler`: `source in _NON_USER_SOURCES` | Skip ✗ |
| ACK sets ON_HOLD → don't run Resolution | `IncidentStateChangedEvent(→in_progress)` but previous was NOT on_hold | `ResolutionHandler`: `previous != on_hold` | Skip ✗ |
| Multiple PendingHandler calls | `process_pending_transition(force_reminder=False)` | `PendingService`: active cycle exists → preserve | Idempotent ✓ |

---

## Platform Folder — Future Use

The `app/platform/` folder is empty now. It will be used when scaling to multi-server deployment:

| Current (`app/orchestrator/`) | Future (`app/platform/`) |
|-------------------------------|--------------------------|
| In-process asyncio event bus | `platform/events/` → Redis/RabbitMQ |
| In-memory scheduler in `pending/scheduler.py` | `platform/scheduler/` → persistent distributed job queue |
| Single process, all agents co-located | `platform/workers/` → separate agent worker processes |
| `platform/telemetry/` | OpenTelemetry tracing across distributed agents |

The `orchestrator/` layer (handlers, registry, events) **never changes** when migrating to platform infrastructure. Only `bus.py` gets swapped to use `platform/events/` instead of `asyncio.gather`. Zero agent code changes required.
