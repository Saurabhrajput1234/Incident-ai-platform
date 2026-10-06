# Incident Work Notes

## Overview

Work notes are a structured, append-only audit trail attached to every incident.
They replace the old flat `work_notes` text field on the `incidents` table with a
proper one-to-many relationship in the `incident_work_notes` table.

Every significant event in an incident's lifecycle — creation, assignment,
acknowledgement, state change, reminder, resolution alert, or a manual note
from a user or engineer — is recorded as a work note with full context about
who did it and what action was taken.

**Key rule:** No code writes directly to `Incident.work_notes`. All paths go
through `WorkNoteService.add_note()`.

---

## File Structure

```
backend/app/modules/work_notes/
├── model.py        SQLAlchemy ORM model (incident_work_notes table)
├── repository.py   All DB queries (create, get, filter)
├── schemas.py      Pydantic input/output schemas
├── enums.py        WorkNoteSourceType + WorkNoteActionType enums
└── service.py      Business logic — the only entry point for creating notes
```

---

## Data Model

### File: `model.py` — Table `incident_work_notes`

| Column | Type | Required | Description |
|---|---|---|---|
| `id` | String(36) UUID | Yes | Primary key, auto-generated |
| `incident_id` | String(36) FK | Yes | References `incidents.id` (CASCADE DELETE) |
| `message` | Text | Yes | Human-readable description of the action |
| `source_type` | String(40) | Yes | Who/what created this note — see enum |
| `source_name` | String(200) | Yes | Specific actor name (e.g. "Priya Sharma", "TriageAgent") |
| `source_id` | String(100) | No | Optional identifier for the originating entity |
| `action_type` | String(50) | No | Operation type — see enum |
| `created_at` | DateTime (TZ) | Yes | Auto-set to UTC on creation |

### Indexes (defined in `model.py`)

```python
Index("ix_work_notes_incident_id", "incident_id")  # fast lookup per incident
Index("ix_work_notes_source_type", "source_type")  # filter by agent/user
Index("ix_work_notes_created_at", "created_at")    # chronological ordering
```

### Relationship

```python
# In IncidentWorkNote model (model.py)
incident: Mapped["Incident"] = relationship("Incident", back_populates="work_note_entries")

# In Incident model (incidents/model.py)
work_note_entries: Mapped[list["IncidentWorkNote"]] = relationship(...)
```

---

## Enums

### File: `enums.py`

### `WorkNoteSourceType` — who created the note

| Value | Description |
|---|---|
| `SYSTEM` | Automatic system event (incident creation, state change audit) |
| `USER` | A portal user manually adding a note |
| `ENGINEER` | An engineer manually adding a note |
| `TRIAGE_AGENT` | The Triage AI Agent |
| `ACKNOWLEDGEMENT_AGENT` | The Acknowledgement AI Agent |
| `PENDING_AGENT` | The Pending AI Agent |
| `RESOLUTION_AGENT` | The Resolution Alert AI Agent |

### `WorkNoteActionType` — what operation was performed

| Value | Description |
|---|---|
| `INCIDENT_CREATE` | Incident was created |
| `INCIDENT_UPDATE` | General field update |
| `ASSIGN_ENGINEER` | Engineer assigned to incident |
| `STATE_CHANGE` | Incident state changed |
| `GROUP_RESOLVED` | Assignment group resolved by AI |
| `SEND_ACKNOWLEDGEMENT` | Acknowledgement email/Teams notification sent |
| `SEND_REMINDER` | Reminder sent by Pending Agent |
| `MANUAL_NOTE` | Manual note added by user or engineer |
| `SYSTEM_NOTE` | Informational note from the system or agent |

---

## Schemas

### File: `schemas.py`

```python
# Input — used when creating a work note
class WorkNoteCreate(BaseModel):
    incident_id: str
    message: str                       # required, min length 1
    source_type: WorkNoteSourceType    # enum — who is creating the note
    source_name: str                   # e.g. "Priya Sharma", "TriageAgent"
    source_id: str | None = None       # optional opaque identifier
    action_type: WorkNoteActionType | None = None

# Output — returned by API and service methods
class WorkNoteResponse(BaseModel):
    id: str
    incident_id: str
    message: str
    source_type: str
    source_name: str
    source_id: str | None
    action_type: str | None
    created_at: datetime
```

---

## Repository

### File: `repository.py`

All raw DB queries live here. The service always goes through the repository.

| Method | Description |
|---|---|
| `create(data: dict)` | Insert a new work note row, commit, return it |
| `get_by_incident(incident_id, limit=100)` | All notes for an incident, newest first |
| `get_by_id(note_id)` | Fetch a single note by primary key |
| `get_latest_by_incident(incident_id)` | Most recent note for an incident |
| `get_by_source_type(incident_id, source_type)` | All notes from a specific source |

---

## Service

### File: `service.py` — The Only Entry Point

`WorkNoteService.add_note()` is the single method all agents, services, and
API handlers must call to create work notes.

### `add_note()` — Full Execution Flow

```
add_note(incident_id, message, source_type, source_name, auto_activate=True)
    │
    ├── Step 1: Persist note to DB via WorkNoteRepository.create()
    │
    ├── Step 1.5: Broadcast via WebSocket (_broadcast_work_note)
    │            → sends WORK_NOTE_ADDED event to connected UI clients
    │
    ├── Step 2: Fetch current incident state snapshot
    │          (BEFORE auto-activation — captures pre-change state)
    │
    ├── Step 3: Publish WorkNoteAddedEvent to EventBus
    │          (carries: incident_id, work_note_id, source_type, incident_state)
    │
    └── Step 4: Auto-activate (if auto_activate=True)
               → calls IncidentService.activate_incident_from_work_note()
               → if incident is on_hold → transitions to in_progress
               → publishes IncidentStateChangedEvent (triggers ResolutionHandler)
```

### `auto_activate` Parameter

| Caller | auto_activate | Reason |
|---|---|---|
| `POST /work-notes` API (user/engineer) | `True` (default) | User note resumes the incident |
| `TriageService` (GROUP_RESOLVED, ASSIGN_ENGINEER notes) | `False` | Triage controls state manually |
| `AcknowledgementService` (SEND_ACKNOWLEDGEMENT) | `False` | ACK agent sets its own state |
| `PendingService` (SEND_REMINDER) | `True` | Reminder triggers on_hold → in_progress cycle |
| `PendingService` (STATE_CHANGE restore) | `False` | State already being managed manually |
| `ResolutionService` (SEND_ACKNOWLEDGEMENT, STATE_CHANGE) | `False` | Resolution manages its own state |

### Other Service Methods

| Method | Description |
|---|---|
| `get_note_by_id(note_id)` | Fetch a single note by ID |
| `get_notes(incident_id, limit=100)` | All notes for an incident |
| `get_latest(incident_id)` | Most recent note |
| `get_by_source_type(incident_id, source_type)` | All notes from one source |
| `get_latest_by_source_type(incident_id, source_type)` | Latest note from one source |
| `build_legacy_text(notes)` | Renders notes back to flat text format for legacy fields |

---

## How Each Agent Uses Work Notes

### 1. System — Incident Creation

Written by `IncidentService.create_incident()` automatically.

```
source_type : SYSTEM
source_name : System
action_type : INCIDENT_CREATE
message     : "Incident INC0000106 created by Rahul Sharma.
               Description: My SHQ is not opening...
               Priority: 3 | State: new | Source: manual"
```

### 2. System — User Update via API

Written by `IncidentService.update_incident()` when a user changes a field.
Action type is chosen based on what changed:

```
state changed      → STATE_CHANGE
assigned_to changed → ASSIGN_ENGINEER
anything else      → INCIDENT_UPDATE
```

> `update_incident_internal()` (used by agents) skips this — agents write
> their own richer notes directly.

### 3. Triage Agent

Written by `TriageService.run_triage()` at each meaningful step.

| Step | action_type | Example message |
|---|---|---|
| AI resolves group | `GROUP_RESOLVED` | "Assignment group resolved by AI to: Apps Run-SAP - BASIS" |
| Engineer assigned | `ASSIGN_ENGINEER` | "Assigned to Priya Sharma (shift=MOR, active_now=True)" |
| No roster found | `SYSTEM_NOTE` | "Triage failed: no shift roster found for 2026-09-02" |
| No engineers available | `SYSTEM_NOTE` | "No available engineers in 'Apps Run-SAP - BASIS' on 2026-09-02" |

All triage notes use `auto_activate=False` — triage controls state transition
explicitly afterwards.

### 4. Acknowledgement Agent

Written by `AcknowledgementService.process_acknowledgement()`.

```
source_type : ACKNOWLEDGEMENT_AGENT
source_name : AcknowledgementAgent
action_type : SEND_ACKNOWLEDGEMENT
auto_activate: False
message     : "Acknowledgement Agent executed successfully.
               • Incident classified as Standard Incident.
               • Ticket assigned to Priya Sharma (Apps Run-SAP - BASIS).
               • User notified with assignment details."
```

If intent is non-standard (Access Request, Wrong Request, etc.), the agent
sets `state = on_hold` **before** writing the note, then calls `add_note(auto_activate=False)`.

### 5. Pending Agent

The Pending Agent writes 3 work notes per reminder cycle:

```
① SEND_REMINDER (auto_activate=True)
   source_type : PENDING_AGENT
   action_type : SEND_REMINDER
   → triggers auto-activation: on_hold → in_progress

② STATE_CHANGE (auto_activate=False) — written by IncidentService internally
   source_type : SYSTEM
   action_type : STATE_CHANGE
   message     : "Incident automatically moved to In Progress"

③ STATE_CHANGE (auto_activate=False) — restore to on_hold
   source_type : PENDING_AGENT
   action_type : STATE_CHANGE
   message     : "State restored to On Hold after reminder N/3 sent"
```

After all 3 reminders: cycle completes, incident stays `on_hold`.

### 6. Resolution Alert Agent

Written by `ResolutionService.process()`.

```
SEND_ACKNOWLEDGEMENT  (ResolutionAgent)  — [TEAMS] notification to engineer
SEND_ACKNOWLEDGEMENT  (ResolutionAgent)  — [EMAIL] notification to group (positive intent only)
STATE_CHANGE          (ResolutionAgent)  — "Incident auto-resolved" (if positive + provenance confirmed)
SYSTEM_NOTE           (ResolutionAgent)  — reason if no auto-resolve
```

All with `auto_activate=False`.

### 7. Manual Notes from UI

Users and engineers can add notes via the Incident Detail page.
Calls `POST /v1/incidents/{id}/work-notes`.

```json
{
  "message": "Checked with the SAP BASIS team, issue is with role assignment",
  "source_type": "ENGINEER",
  "source_name": "Priya Sharma",
  "source_id": null
}
```

`action_type` is automatically set to `MANUAL_NOTE` by the API handler.
`auto_activate=True` — this transitions the incident from `on_hold` → `in_progress`,
which triggers the Resolution Alert Agent via the event bus.

---

## API Endpoints

### List work notes for an incident
```
GET /v1/incidents/{incident_id}/work-notes?limit=100
```
Returns notes ordered by `created_at DESC` (newest first).

### Add a manual work note
```
POST /v1/incidents/{incident_id}/work-notes
```
```json
{
  "message": "string (required)",
  "source_type": "USER | ENGINEER",
  "source_name": "string (required)",
  "source_id": "string (optional)"
}
```

### Get the latest work note
```
GET /v1/incidents/{incident_id}/work-notes/latest
```

---

## Complete Architecture

```
POST /v1/incidents                          POST /v1/incidents/{id}/work-notes
    │                                               │
    ▼                                               ▼
IncidentService.create_incident()       API handler (incidents.py)
    │                                               │
    │  source_type=SYSTEM                           │  source_type=USER|ENGINEER
    │  action_type=INCIDENT_CREATE                  │  action_type=MANUAL_NOTE
    │  auto_activate=False                          │  auto_activate=True (default)
    └──────────────┐                                └──────────┐
                   │                                           │
                   ▼                                           ▼
             WorkNoteService.add_note()  ◄────────────────────┘
                   │
                   ├─ Step 1: WorkNoteRepository.create() → DB
                   ├─ Step 1.5: WebSocket broadcast (WORK_NOTE_ADDED)
                   ├─ Step 2: Snapshot incident state
                   ├─ Step 3: EventBus.publish(WorkNoteAddedEvent)
                   └─ Step 4: _maybe_activate_incident()
                                  → IncidentService.activate_incident_from_work_note()
                                  → on_hold → in_progress (if applicable)
                                  → EventBus.publish(IncidentStateChangedEvent)
                                  → ResolutionHandler triggers


TriageService.run_triage()
    │  source_type=TRIAGE_AGENT
    │  auto_activate=False (always)
    └──► WorkNoteService.add_note()

AcknowledgementService.process_acknowledgement()
    │  source_type=ACKNOWLEDGEMENT_AGENT
    │  auto_activate=False (always)
    └──► WorkNoteService.add_note()

PendingService (SEND_REMINDER)
    │  source_type=PENDING_AGENT
    │  auto_activate=True  → triggers on_hold → in_progress → restored to on_hold
    └──► WorkNoteService.add_note()

ResolutionService.process()
    │  source_type=RESOLUTION_AGENT
    │  auto_activate=False (always)
    └──► WorkNoteService.add_note()
```

---

## WebSocket Real-Time Updates

Every call to `add_note()` triggers `_broadcast_work_note()` which sends a
`WORK_NOTE_ADDED` WebSocket event to all connected clients viewing that incident.

```python
event = {
    "type": "WORK_NOTE_ADDED",
    "work_note": {
        "id": note.id,
        "source_type": "TRIAGE_AGENT",
        "source_name": "TriageAgent",
        "action_type": "ASSIGN_ENGINEER",
        "message": "Assigned to Priya Sharma...",  # truncated to 200 chars
        "created_at": "2026-10-01T12:00:00+00:00"
    }
}
```

The frontend polls every 5 seconds AND receives real-time pushes via WebSocket.

---

## Frontend Display (Incident Detail Page)

- Fetches from `GET /v1/incidents/{id}/work-notes` on load
- Polls every 5 seconds + receives real-time WebSocket updates
- Colour-coded source badges:

| Source | Badge colour |
|---|---|
| Triage Agent | Purple |
| Acknowledgement Agent | Blue |
| Pending Agent | Yellow |
| Resolution Agent | Orange |
| Engineer | Green |
| User | Gray |
| System | Slate |

- Shows: `source_name`, `action_type` pill, timestamp, full message
- Add Note button → Source dropdown (User / Engineer), Name field, message textarea

---

## Circular Import Safety

`WorkNoteService` and `IncidentService` depend on each other:

- `IncidentService` imports `WorkNoteService` at module level (to write notes)
- `WorkNoteService` imports `IncidentService` only at call-time inside
  `_maybe_activate_incident()` (local import — safe, avoids circular dependency)

Same pattern for the event bus imports — always done inside methods, never at module level.
