# Incident AI Platform — Complete Implementation Documentation

---

## Project Overview

Production-ready AI Incident Management Platform built with FastAPI.
Clean Architecture — business logic never lives in API routes.

```
API Layer → Service Layer → Repository Layer → Database
AI Context Builder → Service Layer (read only) → AIContext Object
```

---

## Tech Stack

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.11+ | Runtime |
| FastAPI | 0.109.0 | Web framework |
| Uvicorn | 0.27.0 | ASGI server |
| SQLAlchemy | 2.0.25 | Async ORM |
| asyncpg | 0.29.0 | PostgreSQL async driver |
| Alembic | 1.13.1 | Database migrations |
| Pydantic | 2.x | Data validation |
| pydantic-settings | 2.1.0 | Config management |
| openpyxl | 3.1.2 | Excel parsing |
| python-multipart | 0.0.9 | File upload |
| pytest | 7.4.4 | Testing |
| pytest-asyncio | 0.23.3 | Async tests |
| httpx | 0.26.0 | HTTP test client |
| aiosqlite | — | In-memory SQLite for tests |

---

## Full Project Structure

```
backend/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── router.py
│   │   ├── dependencies.py
│   │   └── v1/
│   │       ├── health.py
│   │       ├── db_health.py
│   │       ├── incidents.py
│   │       ├── shift_roster.py
│   │       └── triage.py              # Context API only (agent is future phase)
│   ├── core/
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   ├── app.py / database.py / logging.py / security.py / settings.py
│   │   ├── lifecycle.py
│   │   ├── logging.py
│   │   └── middleware.py
│   ├── common/
│   │   ├── constants/app.py
│   │   ├── enums/base.py
│   │   ├── exceptions/base.py + handlers.py
│   │   ├── responses/base.py
│   │   ├── schemas/pagination.py
│   │   ├── utils/datetime.py + uuid.py
│   │   └── validators/common.py
│   ├── database/
│   │   └── postgres/base.py + session.py
│   ├── modules/
│   │   ├── incidents/
│   │   │   ├── enums.py / model.py / schemas.py / repository.py / service.py
│   │   ├── shift_roster/
│   │   │   ├── enums.py / model.py / schemas.py / repository.py / service.py / parser.py
│   │   ├── context/                   # ✅ Implemented
│   │   │   ├── __init__.py
│   │   │   ├── schemas.py             # AIContext, IncidentContext, EngineerContext
│   │   │   ├── builder.py             # Assembles AIContext from service data
│   │   │   ├── service.py             # Fetches data, calls builder
│   │   │   └── exceptions.py          # ContextBuildError
│   │   └── agents/
│   │       ├── base/                  # ✅ Skeleton implemented
│   │       │   ├── base_agent.py
│   │       │   ├── context.py
│   │       │   ├── request.py
│   │       │   ├── response.py
│   │       │   └── exceptions.py
│   │       └── triage/                # ⏸️ Placeholder (future phase)
│   │           ├── agent.py
│   │           ├── service.py
│   │           ├── prompts.py
│   │           └── schemas.py
│   ├── ai_platform/
│   │   ├── tools/
│   │   │   ├── base_tool.py           # ✅ BaseTool ABC + ToolResult
│   │   │   ├── incident_tool.py       # ⏸️ Placeholder
│   │   │   └── shift_roster_tool.py   # ⏸️ Placeholder
│   │   ├── llm/ embeddings/ prompts/ retrieval/ services/
│   ├── integrations/
│   │   └── servicenow/ teams/ email/ cmdb/
│   ├── platform/
│   │   └── caching/ events/ execution/ messaging/ registry/ scheduler/ telemetry/ workers/
│   └── tests/
│       ├── conftest.py
│       ├── unit/test_incident_service.py
│       └── api/test_incidents_api.py
├── alembic/versions/
│   ├── 78b5282e58c6_create_incidents_table.py
│   ├── 15fef2bf1df7_create_shift_roster_table.py
│   └── 9092bd4e4a4f_normalized_shift_roster_schema.py
├── scripts/seed_incidents.py
├── docs/
├── alembic.ini / pyproject.toml / pytest.ini
└── .env / .env.example / README.md
```

---

# Phase 1 — Foundation ✅

| Task | Status |
|---|---|
| Project structure | ✅ |
| Virtual environment | ✅ |
| Dependency management | ✅ |
| Configuration (.env) | ✅ |
| FastAPI app + lifespan | ✅ |
| Logging | ✅ |
| CORS Middleware | ✅ |
| Exception handlers | ✅ |
| API versioning (/v1) | ✅ |
| Health APIs | ✅ |
| Swagger / OpenAPI | ✅ |
| README | ✅ |

**Endpoints**

| URL | Description |
|---|---|
| GET /v1/health | App liveness |
| GET /v1/db-health | DB connectivity |

---

# Phase 2 — Database Foundation ✅

- PostgreSQL + SQLAlchemy async engine
- Alembic migrations
- `base.py` — declarative Base for all models
- `session.py` — async engine, `get_db()` dependency

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

---

# Phase 2 — Incident Module ✅

## REST Endpoints

| Method | URL | Description |
|---|---|---|
| POST | /v1/incidents | Create (201) |
| GET | /v1/incidents | List + pagination + filters |
| GET | /v1/incidents/search | Keyword search |
| GET | /v1/incidents/{id} | Get by ID |
| PUT | /v1/incidents/{id} | Update |
| DELETE | /v1/incidents/{id} | Delete (204) |

## Database Model
`incidents` table: id, incident_number, short_description, description, priority, state, category, subcategory, impact, urgency, assignment_group, assigned_to, caller, configuration_item, business_service, environment, source, work_notes, comments, created_at, updated_at

## Seed Data
```bash
python scripts/seed_incidents.py   # 100 realistic incidents
```

## Tests
```bash
pytest app/tests/unit/    # 9 unit tests
pytest app/tests/api/     # 14 API integration tests
pytest                    # all 23
```

---

# Phase 3 — Shift Roster Module ✅

## Shift Code Definitions (constant, no DB table)
```python
from app.modules.shift_roster.enums import SHIFT_DEFINITIONS, WORKING_SHIFTS, NON_WORKING_CODES
```

| Code | Label | Timing | Working |
|---|---|---|---|
| Shift1 | Shift 1 | 12:30 PM IST - 09:30 PM IST | ✅ |
| Shift2 | Shift 2 | 10:00 AM IST - 07:30 PM IST | ✅ |
| Shift3 | Shift 3 | 08:00 AM EST - 05:00 PM EST | ✅ |
| WO | Week Off | — | ❌ |
| PL | Planned Leave | — | ❌ |
| CH | Company Holiday | — | ❌ |
| RH | Restricted Holiday | — | ❌ |

## Database Design (4 tables)

```
shift_roster_uploads ──► shift_roster ◄── engineers
                               │
                               ▼
                     shift_roster_history
```

| Table | Purpose |
|---|---|
| shift_roster_uploads | One row per uploaded file |
| engineers | Master engineer records, upserted by email |
| shift_roster | One row per engineer per day |
| shift_roster_history | Audit trail for post-upload changes |

## REST Endpoints

| Method | URL | Description |
|---|---|---|
| POST | /v1/shift-roster/upload | Upload .xlsx or .csv |
| GET | /v1/shift-roster/uploads | Upload history |
| GET | /v1/shift-roster/available | Engineers on a date |
| GET | /v1/shift-roster/search | Search with optional date+shift |
| PUT | /v1/shift-roster/roster/{id} | Update daily entry + log history |
| GET | /v1/shift-roster/engineer/{email} | Engineer details |
| PUT | /v1/shift-roster/engineer/{email} | Update engineer |
| DELETE | /v1/shift-roster/engineer/{email} | Mark inactive |
| GET | /v1/shift-roster/engineer/{email}/roster | Roster for date range |
| GET | /v1/shift-roster/engineer/{email}/history | Change audit trail |

---

# Phase 5 — AI Context Builder ✅

## What is Implemented

The Context Builder is fully implemented. It collects data from the
Incident Module and Shift Roster Module and assembles a single
structured `AIContext` object — ready to be consumed by the Triage Agent.

The **Triage Agent itself is not yet implemented** (next phase).

---

## Context Building Flow

```
GET /v1/triage/{incident_id}/context
          │
          ▼
ContextService.build_for_incident(incident_id, context_date)
          │
    ┌─────┴──────────────────────┐
    ▼                            ▼
IncidentService              ShiftRosterService
get_incident(id)             get_available_engineers(
                               roster_date=context_date,
                               assignment_group=incident.assignment_group
                             )
    │                            │
    └──────────┬─────────────────┘
               ▼
        Context Builder
        build_context(incident, engineers, context_date)
               │
               ▼
          AIContext object (structured JSON)
```

---

## Context Schemas (`modules/context/schemas.py`)

### IncidentContext
Subset of incident fields needed for AI reasoning:
```python
incident_id, incident_number, short_description, description,
priority, state, category, subcategory,
assignment_group, caller, created_at
```

### EngineerContext
Engineer master record + current shift on the context date:
```python
engineer_id, name, email, assignment_group,
level,           # L1 / L2 / L3
default_shift,   # from Excel
current_shift,   # shift code on context_date (Shift1 / WO / PL etc.)
is_available,    # True if on Shift1/2/3, False if WO/PL/CH/RH
roster_date
```

### AIContext — final output
```python
incident: IncidentContext      # the incident being triaged
engineers: list[EngineerContext]  # all engineers in assignment group
context_date: date             # date used for shift lookup
created_at: datetime           # when context was built
context_version: str           # "1.0"
```

---

## Context Builder (`modules/context/builder.py`)

Pure functions — no DB access, no AI logic, no business rules.

| Function | Input | Output |
|---|---|---|
| `build_incident_context(incident)` | IncidentResponse | IncidentContext |
| `build_engineer_context(engineer)` | EngineerAvailability | EngineerContext |
| `build_context(incident, engineers, date)` | both + date | AIContext |

`is_available` is determined by checking if `shift_code ∈ WORKING_SHIFTS`.

---

## Context Service (`modules/context/service.py`)

```python
class ContextService:
    async def build_for_incident(incident_id, context_date) -> AIContext
```

Steps:
1. Call `IncidentService.get_incident(incident_id)`
2. Validate `incident.assignment_group` exists
3. Call `ShiftRosterService.get_available_engineers(roster_date, assignment_group)`
4. Pass both to `build_context()` and return `AIContext`

Raises `ContextBuildError` (400) if assignment group is missing.

---

## Context API (`api/v1/triage.py`)

```
GET /v1/triage/{incident_id}/context?context_date=YYYY-MM-DD
```

- `context_date` is optional — defaults to today
- Returns the full `AIContext` JSON
- Does not run any agent, does not update anything
- Use this to verify the context before building the agent

**Example response:**
```json
{
  "incident": {
    "incident_id": "abc-123",
    "incident_number": "INC0000001",
    "short_description": "Database timeout on prod",
    "priority": "1",
    "state": "new",
    "category": "database",
    "assignment_group": "DBA Team"
  },
  "engineers": [
    {
      "engineer_id": "eng-456",
      "name": "Vinay Raghuwanshi",
      "email": "vinay@example.com",
      "level": "L1",
      "current_shift": "Shift2",
      "is_available": true,
      "roster_date": "2026-07-15"
    }
  ],
  "context_date": "2026-07-15",
  "created_at": "2026-08-07T10:00:00Z",
  "context_version": "1.0"
}
```

---

## Base Agent Framework (`modules/agents/base/`) ✅ Skeleton

Structure is in place and ready for agents to inherit from.

| File | Purpose |
|---|---|
| `base_agent.py` | Abstract `BaseAgent` — `validate_context()`, `run()`, `reason()` |
| `request.py` | `AgentRequest(context: AIContext)` |
| `response.py` | `AgentResponse(success, reasoning, confidence, result, errors)` |
| `context.py` | Helpers: `get_available_engineers()`, `get_engineers_by_level()` |
| `exceptions.py` | `ContextValidationError`, `AgentReasoningError` |

Agent lifecycle:
```
run(AgentRequest)
  → validate_context()
  → reason(AIContext)   ← implemented by each agent
  → return AgentResponse
```

---

## AI Tool Layer (`ai_platform/tools/`) ✅ BaseTool only

| File | Status |
|---|---|
| `base_tool.py` | ✅ `BaseTool` ABC + `ToolResult` schema |
| `incident_tool.py` | ⏸️ Placeholder — next phase |
| `shift_roster_tool.py` | ⏸️ Placeholder — next phase |

---

# All Active Routes

```
GET  /v1/health
GET  /v1/db-health

POST   /v1/incidents
GET    /v1/incidents
GET    /v1/incidents/search
GET    /v1/incidents/{id}
PUT    /v1/incidents/{id}
DELETE /v1/incidents/{id}

POST   /v1/shift-roster/upload
GET    /v1/shift-roster/uploads
GET    /v1/shift-roster/available
GET    /v1/shift-roster/search
PUT    /v1/shift-roster/roster/{roster_id}
GET    /v1/shift-roster/engineer/{email}
PUT    /v1/shift-roster/engineer/{email}
DELETE /v1/shift-roster/engineer/{email}
GET    /v1/shift-roster/engineer/{email}/roster
GET    /v1/shift-roster/engineer/{email}/history

GET  /v1/triage/{incident_id}/context
```

---

# What the Triage Agent Needs (Next Phase)

The context is ready. To build the Triage Agent, only these files need to be implemented:

| File | What to implement |
|---|---|
| `agents/triage/schemas.py` | `EngineerRecommendation`, `TriageResult` |
| `agents/triage/prompts.py` | Scoring rules (priority → level map, shift weights) |
| `agents/triage/agent.py` | `TriageAgent(BaseAgent)` — `reason(context)` method |
| `agents/triage/service.py` | Orchestrate: build context → run agent → update incident |
| `ai_platform/tools/incident_tool.py` | Wrap `IncidentService` for agent use |
| `ai_platform/tools/shift_roster_tool.py` | Wrap `ShiftRosterService` for agent use |
| Add `POST /v1/triage/{id}` to `triage.py` | Trigger triage + apply recommendation |

---

# Running the Application

```bash
venv\Scripts\activate
pip install -e .
alembic upgrade head
python scripts/seed_incidents.py
uvicorn app.main:app --reload
```

| URL | Purpose |
|---|---|
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/v1/health | App health |
| http://localhost:8000/v1/incidents | Incident list |
| http://localhost:8000/v1/shift-roster/available?roster_date=2026-07-15 | Engineer availability |
| http://localhost:8000/v1/triage/{id}/context | AI context preview |

---

# Future Phases

| Phase | Component |
|---|---|
| Next | Triage Agent (`agents/triage/agent.py`) |
| Next | Triage Service + `POST /v1/triage/{id}` |
| Next | IncidentTool + ShiftRosterTool |
| Later | Acknowledgement / Pending / Resolution Agents |
| Later | LLM integration (replace rule-based scoring) |
| Later | Authentication / JWT / Users |
| Later | ServiceNow integration (swap repository layer) |
| Later | Knowledge Base, Analytics, Audit |
| Later | Platform: Events, Messaging, Caching, Scheduler |
