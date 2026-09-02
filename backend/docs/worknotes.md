# Incident Work Notes

## Overview

Work notes are a structured, append-only audit trail attached to every incident. They replace the old flat `work_notes` text field on the `incidents` table with a proper one-to-many relationship in the `incident_work_notes` table.

Every significant event in an incident's lifecycle — creation, assignment, acknowledgement, state change, or a manual note from a user or engineer — is recorded as a work note with full context about who did it and what action was taken.

---

## Data Model

### Table: `incident_work_notes`

| Column | Type | Required | Description |
|---|---|---|---|
| `id` | UUID | Yes | Primary key |
| `incident_id` | UUID FK | Yes | References `incidents.id` (CASCADE DELETE) |
| `message` | Text | Yes | Human-readable description of the action |
| `source_type` | String(40) | Yes | Who/what created this note — see enum below |
| `source_name` | String(200) | Yes | Specific actor name (e.g. "Priya Sharma", "TriageAgent") |
| `source_id` | String(100) | No | Identifier of the actor when available (engineer_id, etc.) |
| `action_type` | String(50) | No | Operation type — see enum below |
| `created_at` | DateTime (TZ) | Yes | Auto-set to UTC on creation |

### Indexes

- `ix_work_notes_incident_id` — fast lookup of all notes for an incident
- `ix_work_notes_source_type` — filter notes by source (e.g. all agent notes)
- `ix_work_notes_created_at` — chronological ordering

---

## Enums

### `WorkNoteSourceType` — who created the note

| Value | Description |
|---|---|
| `SYSTEM` | Automatic system event (incident creation) |
| `USER` | A portal user manually adding a note |
| `ENGINEER` | An engineer manually adding a note |
| `TRIAGE_AGENT` | The Triage AI Agent |
| `ACKNOWLEDGEMENT_AGENT` | The Acknowledgement AI Agent |
| `PENDING_AGENT` | The Pending AI Agent |

### `WorkNoteActionType` — what operation was performed

| Value | Description |
|---|---|
| `INCIDENT_CREATE` | Incident was created |
| `INCIDENT_UPDATE` | General field update |
| `ASSIGN_ENGINEER` | Engineer assigned to incident |
| `STATE_CHANGE` | Incident state changed |
| `GROUP_RESOLVED` | Assignment group resolved by AI |
| `SEND_ACKNOWLEDGEMENT` | Acknowledgement email sent to caller |
| `SEND_REMINDER` | Reminder sent |
| `MANUAL_NOTE` | Manual note added by user or engineer |
| `SYSTEM_NOTE` | Informational note from the system or agent |

---

## How Work Notes Are Created

### 1. On Incident Creation (automatic)

When any incident is created via `POST /v1/incidents` or bulk import, `IncidentService.create_incident()` writes the first work note immediately:

```
source_type: SYSTEM
source_name: System
action_type: INCIDENT_CREATE
message: "Incident INC0000106 created by Rahul Sharma.
          Description: My SHQ is not opening...
          Priority: 3 | State: new | Source: manual"
```

### 2. On Incident Update (automatic)

When a user updates an incident via `PUT /v1/incidents/{id}`, `IncidentService.update_incident()` writes a note automatically. The action type is chosen based on what changed:

- `state` changed → `STATE_CHANGE`
- `assigned_to` changed → `ASSIGN_ENGINEER`
- anything else → `INCIDENT_UPDATE`

```
source_type: USER
source_name: User
action_type: STATE_CHANGE
message: "State changed to: resolved"
```

> **Note:** Agent services use `update_incident_internal()` which skips this automatic note because agents write their own richer notes immediately after.

### 3. From the Triage Agent (automatic)

The Triage Agent writes work notes at every meaningful step:

| Trigger | action_type | Example message |
|---|---|---|
| AI resolves assignment group | `GROUP_RESOLVED` | "Assignment group resolved by AI to: Apps Run-SAP - BASIS" |
| Engineer successfully assigned | `ASSIGN_ENGINEER` | "Assigned to Priya Sharma (shift=MOR, active_now=True, group=...)" |
| No shift roster found | `SYSTEM_NOTE` | "Triage failed: no shift roster found for 2026-09-02..." |
| No available engineers | `SYSTEM_NOTE` | "No available engineers in 'Apps Run-SAP - BASIS' on 2026-09-02..." |

### 4. From the Acknowledgement Agent (automatic)

The Acknowledgement Agent writes one note per execution, classifying the intent and describing what action was taken:

```
source_type: ACKNOWLEDGEMENT_AGENT
source_name: AcknowledgementAgent
action_type: SEND_ACKNOWLEDGEMENT
message: "Acknowledgement Agent executed successfully.
          • Incident classified as Standard Incident.
          • Ticket assigned to Priya Sharma (Apps Run-SAP - BASIS).
          • User notified with assignment details."
```

### 5. Manual Notes from the UI

Users or engineers can add notes directly from the Incident Detail page by clicking **Add Note**.

The form collects:
- **Source** — dropdown: `User` or `Engineer`
- **Name** — free text (the person's actual name, e.g. "Rahul Sharma")
- **Note** — the message text

This calls `POST /v1/incidents/{id}/work-notes` with:

```json
{
  "message": "Checked with the SAP BASIS team, issue is with role assignment",
  "source_type": "ENGINEER",
  "source_name": "Priya Sharma",
  "source_id": null
}
```

The `action_type` is automatically set to `MANUAL_NOTE` by the API.

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
Used by agents (e.g. Pending Agent) to inspect the most recent activity.

---

## How the Pending Agent Uses Work Notes

The Pending Agent can determine the current state of an incident's history by:

1. Call `GET /v1/incidents/{id}/work-notes/latest` to get the most recent note
2. Inspect `source_type` to know who last acted:
   - `ENGINEER` or `USER` → a human has responded, may need to close/progress
   - `TRIAGE_AGENT` or `ACKNOWLEDGEMENT_AGENT` → agent last acted, waiting for human
   - `SYSTEM` → just created, no action yet
3. Use `WorkNoteService.get_by_source_type()` to get all notes from a specific actor
4. Use `source_id` for future correlation (e.g. link to engineer record)

This design means the Pending Agent never needs to parse free-text — it reads structured fields.

---

## Architecture

```
IncidentService.create_incident()
    └─► WorkNoteService.add_note(source_type=SYSTEM, action=INCIDENT_CREATE)

IncidentService.update_incident()          ← called from API (user actions)
    └─► WorkNoteService.add_note(source_type=USER, action=STATE_CHANGE|ASSIGN_ENGINEER|INCIDENT_UPDATE)

IncidentService.update_incident_internal() ← called from agents (no auto-note)

TriageService.run_triage()
    └─► WorkNoteService.add_note(source_type=TRIAGE_AGENT, ...)

AcknowledgementService.process_acknowledgement()
    └─► WorkNoteService.add_note(source_type=ACKNOWLEDGEMENT_AGENT, ...)

API: POST /v1/incidents/{id}/work-notes    ← manual notes from UI
    └─► WorkNoteService.add_note(source_type=USER|ENGINEER, action=MANUAL_NOTE)
```

All paths go through `WorkNoteService.add_note()`. No code writes directly to `incident.work_notes`.

---

## Frontend Display

The Work Notes card on the Incident Detail page:

- Fetches from `GET /v1/incidents/{id}/work-notes` on load and polls every 5 seconds
- Shows each note as a timeline entry with a colour-coded source badge:
  - Purple — Triage Agent
  - Blue — Acknowledgement Agent
  - Yellow — Pending Agent
  - Green — Engineer
  - Gray — User
  - Slate — System
- Shows `source_name`, `action_type` pill, timestamp, and message
- **Add Note** button opens a form with Source dropdown (User / Engineer), Name field, and message textarea
