# Context Layer & AI Tools — Complete Documentation

---

## Overview

The Context Layer and AI Tool Layer are the two middleware layers that sit between business modules and AI agents.

```
Business Modules (Incidents, Shift Roster)
         ↓
  Context Layer          ← assembles structured data for agents
         ↓
    AI Agents            ← reason on context only
         ↓
   Tool Layer            ← agents call tools for on-demand data (future)
         ↓
Business Services        ← tools talk to services only, never DB directly
```

**Key rule:** Agents never touch the database, repositories, or business services directly. They receive a pre-built context object and may call tools. That's it.

---

## Part 1 — Context Layer

### Purpose

The Context Layer collects data from multiple business modules and assembles it into a single, clean `AIContext` object. The agent receives only this object — nothing else.

### Files

| File | Purpose |
|---|---|
| `modules/context/schemas.py` | Data contracts: `IncidentContext`, `EngineerContext`, `AIContext` |
| `modules/context/builder.py` | Pure functions that assemble AIContext from service data |
| `modules/context/service.py` | `ContextService` — fetches data, calls builder |
| `modules/context/exceptions.py` | `ContextBuildError` |
| `modules/agents/base/context.py` | Helper utilities agents use to query the context |

---

### Schemas (`context/schemas.py`)

Three Pydantic models define the complete data contract between the Context Layer and all agents.

#### IncidentContext

Subset of incident fields needed for AI reasoning. Strips out internal DB fields.

```python
class IncidentContext(BaseModel):
    incident_id: str            # UUID
    incident_number: str        # e.g. INC0000001
    short_description: str      # required field
    description: str | None     # optional detail
    priority: str               # "1"=Critical, "2"=High, "3"=Medium, "4"=Low
    state: str                  # new, in_progress, on_hold, resolved, closed
    category: str | None        # network, database, software, etc.
    subcategory: str | None
    assignment_group: str | None  # target team — must be set before building context
    caller: str | None          # who reported it
    created_at: datetime
```

#### EngineerContext

Engineer master record combined with their shift for the context date.

```python
class EngineerContext(BaseModel):
    engineer_id: str
    name: str
    email: str
    assignment_group: str
    level: str | None           # "L1", "L2", or "L3"
    default_shift: str | None   # their usual shift from Excel
    current_shift: str | None   # their actual shift on context_date
                                # one of: Shift1, Shift2, Shift3, WO, PL, CH, RH
    is_available: bool          # True if current_shift is Shift1/2/3
    is_shift_active: bool       # True if shift window is active RIGHT NOW (clock check)
    roster_date: date | None    # the date this shift applies to
```

The difference between `is_available` and `is_shift_active`:
- `is_available = True` means the engineer is scheduled for a working shift today
- `is_shift_active = True` means their shift window is currently open (e.g. Shift2 is active 10:00–19:30 IST)

#### AIContext

The complete package delivered to the agent.

```python
class AIContext(BaseModel):
    incident: IncidentContext            # the incident being processed
    engineers: list[EngineerContext]     # all engineers in the assignment group
    context_date: date                  # date used for shift lookup (defaults to today)
    created_at: datetime                # when this context was assembled
    context_version: str = "1.0"       # for future schema versioning
```

---

### Context Builder (`context/builder.py`)

Pure stateless functions. No DB access. No AI logic. No business rules.
Just transforms service output into context schemas.

```python
build_incident_context(incident: IncidentResponse) → IncidentContext
```
Maps `IncidentResponse` fields to `IncidentContext`. Picks only what agents need.

```python
build_engineer_context(eng: EngineerAvailability) → EngineerContext
```
Maps `EngineerAvailability` + calls `is_shift_active_now(shift_code)` to set `is_shift_active`.

```python
build_context(incident, engineers, context_date) → AIContext
```
Calls both builders and assembles the final `AIContext`.

**Rules the builder never breaks:**
- Never queries the database
- Never updates anything
- Never contains if/else business decisions
- Never calls LLM or AI services

---

### Context Service (`context/service.py`)

`ContextService` is the orchestrator. It fetches data from business services and hands it to the builder.

```python
class ContextService:
    async def build_for_incident(incident_id, context_date=None) → AIContext
```

**Internal steps:**

```
1. incident_service.get_incident(incident_id)
        ↓
   Validates: assignment_group must exist
   Raises ContextBuildError if missing
        ↓
2. roster_service.get_available_engineers(
       roster_date=context_date,
       assignment_group=incident.assignment_group
   )
        ↓
   Returns list of EngineerAvailability (from shift_roster table)
        ↓
3. build_context(incident, engineers, context_date)
        ↓
   Returns AIContext
```

**Who calls ContextService:**
- `TriageService.run_triage()` — before running the Triage Agent
- `GET /v1/triage/{id}/context` — debug endpoint to preview context

---

### Context Helper Utilities (`agents/base/context.py`)

Helper functions that agents use to query the AIContext without writing filter logic themselves.

```python
get_available_engineers(context: AIContext) → list[EngineerContext]
# Returns only engineers where is_available=True (on Shift1/2/3)

get_engineers_on_leave(context: AIContext) → list[EngineerContext]
# Returns engineers on WO/PL/CH/RH

has_available_engineers(context: AIContext) → bool
# Quick check — any working-shift engineers?

get_engineers_by_level(context: AIContext, level: str) → list[EngineerContext]
# Filter by L1, L2, or L3
```

Any agent can import and use these. They operate on the already-built AIContext — no DB calls.

---

### Context API Endpoint

```
GET /v1/triage/{incident_id}/context?context_date=YYYY-MM-DD
```

Returns the full AIContext JSON for debugging. Does not run any agent, does not update anything.

**Example response:**
```json
{
  "incident": {
    "incident_id": "abc-123",
    "incident_number": "INC0000001",
    "short_description": "Database timeout on production",
    "priority": "1",
    "state": "new",
    "category": "database",
    "assignment_group": "Windows Support"
  },
  "engineers": [
    {
      "engineer_id": "eng-456",
      "name": "Swapna Maji",
      "email": "swapna@example.com",
      "level": "L2",
      "current_shift": "Shift2",
      "is_available": true,
      "is_shift_active": true,
      "roster_date": "2026-08-12"
    }
  ],
  "context_date": "2026-08-12",
  "created_at": "2026-08-12T10:33:00Z",
  "context_version": "1.0"
}
```

---

### Extending the Context

To add a new data source to the context (e.g. CMDB, previous incidents):

1. Add new fields to `EngineerContext` or `AIContext` in `schemas.py`
2. Add a fetch call in `ContextService.build_for_incident()`
3. Add a mapping function in `builder.py`

The Triage Agent and all other agents automatically receive the enriched context — no changes needed in the agents themselves.

---

## Part 2 — AI Tool Layer

### Purpose

The Tool Layer is an abstraction layer that gives AI agents a clean, standardized way to query business data on demand — without calling services or repositories directly.

Think of tools as **named, callable functions** that agents can invoke.

```
Agent → IncidentTool.run(action="get_incident", incident_id="...")
         ↓
    IncidentService.get_incident(...)
         ↓
    ToolResult(success=True, data={...})
         ↓
    Agent receives clean dict, processes it
```

### When are tools used vs context?

| Context Layer | Tool Layer |
|---|---|
| Pre-fetches all data BEFORE agent runs | Agent fetches data ON DEMAND during reasoning |
| Best for structured, predictable data | Best for dynamic/conditional data needs |
| Used by current Triage Agent | Used by future LLM-driven agents |
| No extra DB calls during reasoning | Each tool call = one DB/service call |

**Current state:** The Triage Agent uses the Context Layer only. Tools are scaffolded for future LLM integration.

---

### BaseTool (`ai_platform/tools/base_tool.py`)

Abstract base class all tools inherit from.

```python
class ToolResult(BaseModel):
    success: bool
    tool_name: str
    data: dict = {}
    error: str | None = None

class BaseTool(ABC):
    @property
    @abstractmethod
    def tool_name(self) -> str: ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult: ...

    async def run(self, **kwargs) -> ToolResult:
        # Wraps execute() with error handling
        # Catches all exceptions → returns ToolResult(success=False, error=...)
```

Every tool:
- Has a unique `tool_name`
- Implements `execute(**kwargs)` with its logic
- Calls `run()` as the public entry point (which handles errors)
- Returns `ToolResult` — always, even on failure

---

### IncidentTool (planned)

**File:** `ai_platform/tools/incident_tool.py`

**Planned actions:**

```python
await incident_tool.run(action="get_incident", incident_id="abc-123")
→ ToolResult(success=True, data={"id": "...", "priority": "1", ...})

await incident_tool.run(action="get_assignment_group", incident_id="abc-123")
→ ToolResult(success=True, data={"assignment_group": "Windows Support"})
```

**Rule:** Only calls `IncidentService`. Never calls repository directly.

---

### ShiftRosterTool (planned)

**File:** `ai_platform/tools/shift_roster_tool.py`

**Planned actions:**

```python
await roster_tool.run(
    action="get_available_engineers",
    roster_date=date(2026, 8, 12),
    assignment_group="Windows Support"
)
→ ToolResult(success=True, data={"engineers": [...]})

await roster_tool.run(
    action="get_on_call_engineer",
    assignment_group="Windows Support",
    roster_date=date(2026, 8, 12)
)
→ ToolResult(success=True, data={"on_call_engineer": {...}})
```

**Rule:** Only calls `ShiftRosterService`. Never calls repository directly.

---

## Part 3 — LLM Service (Shared)

### Purpose

`LLMService` is the shared wrapper around the Groq API. Any agent that needs language model reasoning uses this service. It is not tied to any single agent.

### Files

| File | Purpose |
|---|---|
| `ai_platform/llm/groq_client.py` | Creates and caches the AsyncGroq client singleton |
| `ai_platform/services/llm_service.py` | `LLMService.complete()` — makes the API call |

### Groq Client (`ai_platform/llm/groq_client.py`)

```python
def get_groq_client() -> AsyncGroq:
    # Returns singleton — created once, reused across requests
    # Reads GROQ_API_KEY from settings
```

Single shared client instance per process. Lazy initialization on first call.

### LLMService (`ai_platform/services/llm_service.py`)

```python
class LLMService:
    async def complete(
        self,
        messages: list[dict],    # [{role, content}, ...]
        model: str | None,       # override GROQ_MODEL from settings
        max_tokens: int | None,  # override GROQ_MAX_TOKENS
        temperature: float | None  # override GROQ_TEMPERATURE
    ) -> str:
        # Calls Groq API
        # Returns response content as plain string
```

**Usage in TriageService:**
```python
llm = LLMService()
messages = build_assignment_group_messages(
    short_description="Database timeout",
    description="...",
    work_notes="...",
    available_groups=ASSIGNMENT_GROUPS
)
result = await llm.complete(messages=messages)
# result = "Database Support"
```

**Settings (from .env):**
```
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_MAX_TOKENS=1024
GROQ_TEMPERATURE=0.0    # deterministic — same input → same output
```

Temperature `0.0` is used because group classification needs deterministic, reproducible results.

---

## Complete Flow Showing All Layers

```
New incident created (state=new, assigned_to=null)
         │
         ▼
TriageService.run_triage(incident_id)
         │
    ┌────┴──────────────────────────────────────────────┐
    │  LAYER 1 — LLM (if common queue)                  │
    │  LLMService.complete(messages)                    │
    │  → Groq API → "Windows Support"                  │
    │  IncidentService.update(assignment_group=...)     │
    └────┬──────────────────────────────────────────────┘
         │
    ┌────┴──────────────────────────────────────────────┐
    │  LAYER 2 — Context Building                       │
    │  ContextService.build_for_incident()              │
    │    → IncidentService.get_incident()               │
    │    → ShiftRosterService.get_available_engineers() │
    │    → builder.build_context()                      │
    │    → AIContext { incident, engineers, date }      │
    └────┬──────────────────────────────────────────────┘
         │
    ┌────┴──────────────────────────────────────────────┐
    │  LAYER 3 — Agent Reasoning                        │
    │  TriageAgent.run(AgentRequest(context=AIContext)) │
    │    → validate_context()                           │
    │    → reason(context) → AgentResponse             │
    │  [Agent only sees AIContext, touches nothing else]│
    └────┬──────────────────────────────────────────────┘
         │
    ┌────┴──────────────────────────────────────────────┐
    │  LAYER 4 — Assignment (Tool-like, DB-backed)      │
    │  AssignmentService.assign_engineer()              │
    │    → filters by is_shift_active                   │
    │    → round-robin from assignment_group_rr_state   │
    │    → writes to assignment_history                 │
    └────┬──────────────────────────────────────────────┘
         │
    ┌────┴──────────────────────────────────────────────┐
    │  LAYER 5 — Incident Update                        │
    │  IncidentService.update_incident()                │
    │    assigned_to = engineer.name                    │
    │    state = "in_progress"                          │
    │    work_notes = triage reasoning                  │
    └────┬──────────────────────────────────────────────┘
         │
         ▼
    PostgreSQL updated
```

---

## Design Principles

**Why Context Layer instead of letting agents query services?**
- Agents stay stateless and testable — you can unit test an agent by just passing an AIContext
- Adding a new data source (CMDB, SLA data, etc.) only requires changing the Context Builder — zero changes in agents
- Agents run faster — all DB queries happen before the agent starts

**Why Tool Layer instead of direct service calls?**
- Tools give each action a name and schema — this is what LLM tool-calling APIs expect (OpenAI functions, Anthropic tools)
- Future LLM agents can dynamically call tools mid-reasoning without pre-fetching everything
- Tools enforce the rule: agents → tools → services → DB (never agents → DB)

**Why LLMService instead of calling Groq directly?**
- Single place to change model, temperature, or provider
- Any agent imports the same service — consistent behavior
- Easy to add retry logic, token counting, or provider switching later
