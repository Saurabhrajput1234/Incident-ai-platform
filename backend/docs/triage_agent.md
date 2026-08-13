# Triage Agent — Complete Documentation

---

## Overview

The Triage Agent is the first AI agent in the Incident AI Platform.
Its job is to automatically assign a new incident to the most appropriate available engineer.

It combines two intelligence mechanisms:
- **LLM intelligence** — determines the correct team (assignment group) from incident text
- **Rule-based selection** — picks the engineer using persistent round-robin rotation

The agent never queries the database directly and never updates incidents itself.
All DB reads/writes go through service layers.

---

## Architecture

```
POST /v1/incidents (new incident)
         │
         ▼ [BackgroundTask — fires automatically]
POST /v1/triage/{incident_id}
         │
         ▼
TriageService.run_triage()
         │
    ┌────┴────────────────────────────────┐
    │           GUARD CHECKS              │
    │  state must be 'new' or 'in_progress'
    │  assigned_to must be empty          │
    └────┬────────────────────────────────┘
         │
         ▼
STEP 1 — Resolve Assignment Group
         │
    Does incident have a specific group?
    ├── YES (e.g. "Windows Support") → use it directly
    └── NO or common queue group
              │
              ▼
         Groq LLM (llama-3.3-70b-versatile)
         reads: short_description + description + work_notes
         picks from: ASSIGNMENT_GROUPS (hardcoded list of 20)
         updates incident.assignment_group in DB
         │
         ▼
STEP 2 — Build AIContext
         │
    IncidentService.get_incident()
    ShiftRosterService.get_available_engineers(date, group)
         │
    Context Builder assembles AIContext:
      {incident: IncidentContext, engineers: [EngineerContext]}
         │
         ▼
STEP 3 — TriageAgent.run(AIContext)
         │
    Validates: assignment_group must be present
    Counts: available / total engineers
    Returns: AgentResponse (success=True, group confirmed)
         │
         ▼
STEP 4 — AssignmentService.assign_engineer()
         │
    [See Round-Robin section below]
         │
         ▼
STEP 5 — IncidentService.update_incident()
    assigned_to = selected engineer name
    state       = 'in_progress'
    work_notes  = full triage reasoning
         │
         ▼
    PostgreSQL updated
```

---

## Files & Responsibilities

| File | Class/Function | Responsibility |
|---|---|---|
| `triage/service.py` | `TriageService` | Orchestrates all 5 steps, the only place that writes back to DB |
| `triage/agent.py` | `TriageAgent` | Validates AIContext, confirms group, counts availability |
| `triage/assignment_service.py` | `AssignmentService` | Round-robin engineer selection, writes history |
| `triage/prompts.py` | `ASSIGNMENT_GROUPS`, `COMMON_QUEUE_GROUPS`, `build_assignment_group_messages()` | LLM prompt building, group classification |
| `triage/schemas.py` | `EngineerRecommendation`, `TriageResult` | Output data structures |
| `triage/models.py` | `AssignmentGroupRRState`, `AssignmentHistory` | DB tables for round-robin state and audit |
| `context/schemas.py` | `AIContext`, `IncidentContext`, `EngineerContext` | Data contract — what the agent receives |
| `context/builder.py` | `build_context()` | Assembles AIContext from service data |
| `context/service.py` | `ContextService` | Fetches incident + engineers, calls builder |
| `agents/base/base_agent.py` | `BaseAgent` | Abstract base — all agents inherit from this |
| `shift_roster/shift_time_checker.py` | `is_shift_active_now()` | Checks if a shift window is active right now |
| `ai_platform/llm/groq_client.py` | `get_groq_client()` | Shared Groq API client |
| `ai_platform/services/llm_service.py` | `LLMService` | Shared LLM call wrapper |

---

## Step 1 — Assignment Group Resolution

### Two Paths

**Path 1 — Group already set (specific team):**
```
incident.assignment_group = "Windows Support"
is_common_queue("Windows Support") → False
→ use it directly, skip LLM
```

**Path 2 — Common queue or missing group:**
```
incident.assignment_group = "IT Helpdesk"   (or None)
is_common_queue("IT Helpdesk") → True
→ call LLM
```

### Common Queue Groups (never go directly to engineers)
```python
COMMON_QUEUE_GROUPS = {
    "IT Service Desk",
    "IT Helpdesk",
    "General IT Support",
    "L1 Support",
    "Enterprise Support",
    "General Support",
    "Technical Support",
    "Service Operations",
}
```

### Specific Assignment Groups (LLM picks from these)
```python
ASSIGNMENT_GROUPS = [
    "Windows Support",      "Network Support",     "Database Support",
    "Linux Support",        "Cloud Infrastructure", "Storage Support",
    "SAP Support",          "Oracle Support",       "Security Operations",
    "Middleware Support",   "Active Directory Support", "Backup Support",
    "Citrix Support",       "Application Support",  "DevOps Support",
    "Hardware Support",     "Virtualization Support", "Email Support",
    "Telecom Support",      "Endpoint Support",
]
```

### LLM Prompt Design

System prompt:
```
You are an IT incident management expert.
Pick ONE assignment group from the list.
Respond with ONLY the group name. No explanation.
If unsure, respond: UNKNOWN
```

User prompt provides:
- Short Description
- Description
- Work Notes

LLM responds with a single group name (e.g. `Windows Support`).

The service validates the response against `ASSIGNMENT_GROUPS`. If unrecognized or `UNKNOWN`, triage returns an error.

---

## Step 2 — AI Context Building

The `ContextService` fetches data from two modules and passes it to the `Context Builder`:

```python
# IncidentService.get_incident(incident_id) → IncidentContext
IncidentContext(
    incident_id, incident_number,
    short_description, description,
    priority, state, category, subcategory,
    assignment_group, caller, created_at
)

# ShiftRosterService.get_available_engineers(date, group) → list[EngineerContext]
EngineerContext(
    engineer_id, name, email,
    assignment_group, level,          # L1/L2/L3
    default_shift,                    # from Excel roster
    current_shift,                    # Shift1/Shift2/Shift3/WO/PL/CH/RH for context_date
    is_available,                     # True if current_shift is a working shift
    is_shift_active,                  # True if shift window is active RIGHT NOW (time check)
    roster_date
)
```

Final `AIContext`:
```python
AIContext(
    incident=IncidentContext,
    engineers=list[EngineerContext],
    context_date=date,        # defaults to today
    created_at=datetime,
    context_version="1.0"
)
```

---

## Step 3 — Shift Time Checker

The `is_shift_active` flag in `EngineerContext` is set by `shift_time_checker.py`.

### How it works

Each shift has a defined time window in its local timezone:

| Shift | Window | Timezone |
|---|---|---|
| Shift1 | 12:30 PM – 09:30 PM | IST (UTC+5:30) |
| Shift2 | 10:00 AM – 07:30 PM | IST (UTC+5:30) |
| Shift3 | 08:00 AM – 05:00 PM | EST (UTC-5:00) |
| WO / PL / CH / RH | Never active | — |

At runtime:
1. Gets current UTC time
2. Converts to the shift's timezone
3. Checks if current local time falls within the window

```python
is_shift_active_now("Shift2")
# → converts UTC to IST
# → checks if 10:00 ≤ current_IST_time ≤ 19:30
# → returns True or False
```

Check current status:
```
GET /v1/shift-status
→ returns active/inactive for all shifts with current local times
```

---

## Step 4 — Round-Robin Engineer Selection

### Why Round-Robin?
Ensures fair, even distribution of incidents across engineers in the same assignment group. No engineer is overloaded while others sit idle.

### How it works

**Priority order:**
```
1. Engineers where is_shift_active = True   (in active shift window NOW)
2. Engineers where is_available = True      (on working shift today, window not active yet)
3. NO_AVAILABLE_ENGINEER                    (all on WO/PL/CH/RH)
```

**Round-robin algorithm (DB-persisted):**

```python
# Read current state with row lock (prevents race conditions)
SELECT * FROM assignment_group_rr_state
WHERE assignment_group = 'Windows Support'
FOR UPDATE

# Calculate next index
next_index = (last_index + 1) % len(candidates)

# Pick engineer at that index
selected = candidates[next_index]

# Save new index
UPDATE assignment_group_rr_state
SET last_index = next_index
WHERE assignment_group = 'Windows Support'
```

**Example with 3 available engineers [A, B, C]:**
```
Assignment 1: last_index=0 → picks A → saves index=0
Assignment 2: last_index=0 → next=(0+1)%3=1 → picks B → saves index=1
Assignment 3: last_index=1 → next=(1+1)%3=2 → picks C → saves index=2
Assignment 4: last_index=2 → next=(2+1)%3=0 → picks A → saves index=0
```

**Persistence:** The `assignment_group_rr_state` table stores `last_index` per group. This survives server restarts — unlike in-memory round-robin.

**Concurrency safety:** `SELECT ... FOR UPDATE` locks the row so two simultaneous triage requests for the same group cannot both pick the same engineer.

### Fallback Behavior

If no engineer is in an active shift window (e.g. it's 2 AM and no shift is running):
- Falls back to any engineer scheduled for a working shift today
- Marks `fallback_used=True` in the response and history
- Still uses round-robin ordering within the fallback pool

If all engineers are on WO/PL/CH/RH:
- Returns `NO_AVAILABLE_ENGINEER`
- Incident is NOT updated
- Triage response: `success=False`

---

## Database Tables

### assignment_group_rr_state

Stores the current round-robin position per assignment group.

| Column | Type | Description |
|---|---|---|
| assignment_group | String PK | Group name e.g. "Windows Support" |
| last_index | Integer | Last engineer index used |
| updated_at | DateTime | When last updated |

### assignment_history

Full audit trail of every assignment made by the system.

| Column | Type | Description |
|---|---|---|
| id | UUID PK | |
| incident_id | String | Incident UUID |
| incident_number | String | e.g. INC0000001 |
| assignment_group | String | Group the engineer belongs to |
| engineer_id | String | Engineer UUID |
| engineer_name | String | Engineer name |
| engineer_email | String | Engineer email |
| shift_code | String | Shift they were on when assigned |
| roster_date | String | Date of assignment |
| assigned_at | DateTime | Timestamp of assignment |
| llm_resolved_group | Boolean | True if LLM determined the group |
| notes | Text | Round-robin index, fallback info |

---

## Guard Conditions

Triage only runs if ALL conditions are met:

| Condition | If fails |
|---|---|
| `incident.state == 'new' OR 'in_progress'` | Returns error, no update |
| `incident.assigned_to is None or empty` | Returns "already assigned", no update |
| Assignment group resolved successfully | Returns error, no update |
| At least one engineer exists in group | Returns NO_AVAILABLE_ENGINEER |

---

## Response Format

```json
{
  "success": true,
  "agent_name": "TriageAgent",
  "reasoning": "Assigned Swapna Maji via round-robin (index 3/4, shift=Shift2, active_now=True)",
  "confidence": 1.0,
  "result": {
    "incident_id": "abc-123",
    "incident_number": "INC0000001",
    "assignment_group": "Windows Support",
    "recommended_engineer": null,
    "all_candidates": [],
    "recommendation_reason": "...",
    "llm_resolved_group": false,
    "timestamp": "2026-08-11T10:33:00Z",
    "assigned_engineer": {
      "name": "Swapna Maji",
      "email": "swapna@example.com",
      "shift": "Shift2",
      "is_shift_active": true,
      "group": "Windows Support",
      "fallback_used": false
    }
  },
  "errors": [],
  "timestamp": "2026-08-11T10:33:00Z"
}
```

**Failure response (no available engineer):**
```json
{
  "success": false,
  "agent_name": "TriageAgent",
  "reasoning": "No available engineers in 'Windows Support' on 2026-08-11. All on WO/PL/CH/RH.",
  "errors": ["NO_AVAILABLE_ENGINEER"]
}
```

---

## API Endpoints

| Method | URL | Description |
|---|---|---|
| POST | /v1/triage/{incident_id} | Run full triage flow |
| GET | /v1/triage/{incident_id}/context | Preview AIContext (debug, no agent run) |
| GET | /v1/shift-status | See which shifts are active right now |
| GET | /v1/ai-health | Test Groq LLM connectivity |

### POST /v1/triage/{incident_id} Query Params

| Param | Default | Description |
|---|---|---|
| context_date | today | Date for shift lookup (YYYY-MM-DD) |
| apply_recommendation | true | If false, runs triage but does NOT update incident |

---

## Auto-Trigger on Incident Creation

When a new incident is created via `POST /v1/incidents`, triage fires automatically:

```python
# incidents.py
@router.post("")
async def create_incident(payload, background_tasks: BackgroundTasks, ...):
    incident = await service.create_incident(payload)
    background_tasks.add_task(_auto_triage, incident.id)  # fires async
    return incident  # returns 201 immediately
```

The API returns 201 before triage completes. Triage runs in the background using its own DB session. The incident will be updated (assigned + state=in_progress) within seconds.

---

## Base Agent Framework

All agents (including Triage) inherit from `BaseAgent`:

```python
class BaseAgent(ABC):
    @abstractmethod
    async def reason(self, context: AIContext) -> AgentResponse: ...

    async def run(self, request: AgentRequest) -> AgentResponse:
        validate_context()
        response = await self.reason(context)
        return response
```

Every agent follows the same lifecycle:
```
run(AgentRequest)
  → validate_context()       # checks AIContext is valid
  → reason(AIContext)        # agent-specific logic
  → return AgentResponse     # standardized output
```

Errors are caught and wrapped into `AgentResponse(success=False, errors=[...])` — never propagated as exceptions to the API.

---

## Extending the Agent

To add another agent (e.g. Acknowledgement Agent):

1. Create `modules/agents/acknowledgement/agent.py`
2. Inherit from `BaseAgent`
3. Implement `agent_name` and `reason(context)`
4. Create agent-specific prompts in `agents/acknowledgement/prompts.py`
5. Create a service in `agents/acknowledgement/service.py`
6. Add API endpoint in `api/v1/acknowledgement.py`

The `LLMService`, `ContextService`, and `AssignmentService` are all reusable.

---

## Maintenance Notes

**To update assignment groups:**
Edit `ASSIGNMENT_GROUPS` in `modules/agents/triage/prompts.py`.
No DB migration needed — it's a Python constant.

**To update shift times:**
Edit `SHIFT_WINDOWS` in `modules/shift_roster/shift_time_checker.py`.

**To reset round-robin for a group:**
```sql
UPDATE assignment_group_rr_state SET last_index = 0 WHERE assignment_group = 'Windows Support';
```

**To view assignment history:**
```sql
SELECT * FROM assignment_history ORDER BY assigned_at DESC LIMIT 20;
```
