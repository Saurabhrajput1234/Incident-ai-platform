# Incident AI Platform — Complete Implementation Documentation

---

## Project Overview

Production-ready AI Incident Management Platform built with FastAPI.
Uses Clean Architecture: API → Service → Repository → PostgreSQL.
AI agents receive structured context objects — never direct DB access.

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
| pydantic-settings | 2.1.0 | Config from .env |
| openpyxl | 3.1.2 | Excel file parsing |
| python-multipart | 0.0.9 | File upload support |
| groq | 0.9.0 | Groq LLM API client |
| pytz | 2024.1 | Timezone handling |
| pytest | 7.4.4 | Testing |
| pytest-asyncio | 0.23.3 | Async tests |
| httpx | 0.26.0 | HTTP test client |
| aiosqlite | — | In-memory SQLite for tests |

---

## Environment Variables (.env)

```env
APP_NAME=Incident AI Platform
APP_VERSION=0.1.0
ENVIRONMENT=development
DEBUG=true
API_V1_PREFIX=/v1
ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:8000"]
LOG_LEVEL=INFO
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/incident_ai
SECRET_KEY=changeme
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_MAX_TOKENS=1024
GROQ_TEMPERATURE=0.0
```

---

## Complete Project Structure

```
backend/
├── app/
│   ├── main.py                            FastAPI app bootstrap, middleware, exception handlers, lifespan
│   │
│   ├── api/
│   │   ├── router.py                      Registers all versioned sub-routers
│   │   ├── dependencies.py                Shared API dependencies (placeholder)
│   │   └── v1/
│   │       ├── health.py                  GET /v1/health — app liveness
│   │       ├── db_health.py               GET /v1/db-health — PostgreSQL connectivity
│   │       ├── ai_health.py               GET /v1/ai-health — Groq LLM test
│   │       │                              GET /v1/shift-status — current active shifts
│   │       ├── incidents.py               Incident CRUD + auto-triggers triage on create
│   │       ├── shift_roster.py            Roster upload, engineer management APIs
│   │       └── triage.py                  POST /v1/triage/{id} — run triage
│   │                                      GET  /v1/triage/{id}/context — preview AIContext
│   │
│   ├── core/
│   │   ├── config/
│   │   │   ├── __init__.py                Exports single `settings` instance
│   │   │   ├── app.py                     APP_NAME, VERSION, CORS, API prefix
│   │   │   ├── database.py                DATABASE_URL
│   │   │   ├── logging.py                 LOG_LEVEL
│   │   │   ├── security.py                SECRET_KEY, JWT config
│   │   │   ├── ai.py                      GROQ_API_KEY, GROQ_MODEL, temperature
│   │   │   └── settings.py                Merges all config classes → settings singleton
│   │   ├── lifecycle.py                   Startup/shutdown events (lifespan)
│   │   ├── logging.py                     Logger setup (stdout, format, level)
│   │   └── middleware.py                  CORS middleware registration
│   │
│   ├── common/
│   │   ├── constants/app.py               DEFAULT_PAGE_SIZE, date format constants
│   │   ├── enums/base.py                  Environment, Status enums
│   │   ├── exceptions/
│   │   │   ├── base.py                    NotFoundError, BadRequestError, etc.
│   │   │   └── handlers.py                HTTP/validation/500 exception handlers
│   │   ├── responses/base.py              SuccessResponse[T], ErrorResponse
│   │   ├── schemas/pagination.py          PaginationParams, PaginatedResponse[T]
│   │   ├── utils/datetime.py              utcnow(), format_datetime()
│   │   ├── utils/uuid.py                  generate_uuid(), is_valid_uuid()
│   │   └── validators/common.py           is_valid_email(), is_non_empty_string()
│   │
│   ├── database/
│   │   └── postgres/
│   │       ├── base.py                    SQLAlchemy declarative Base (all models inherit)
│   │       └── session.py                 Async engine, session factory, get_db() dependency
│   │
│   ├── modules/
│   │   │
│   │   ├── incidents/
│   │   │   ├── enums.py                   Priority, State, Category, Impact, Urgency, Source enums
│   │   │   ├── model.py                   SQLAlchemy Incident model (incidents table)
│   │   │   ├── schemas.py                 IncidentCreate, IncidentUpdate, IncidentResponse, IncidentListResponse
│   │   │   ├── repository.py              All SQL queries: create, get, list, update, delete, search
│   │   │   └── service.py                 Business logic: create, get (by ID or INC number), list, update, delete, search
│   │   │
│   │   ├── shift_roster/
│   │   │   ├── enums.py                   ShiftCode, EngineerLevel, EngineerStatus, UploadStatus, SHIFT_DEFINITIONS, WORKING_SHIFTS
│   │   │   ├── model.py                   4 SQLAlchemy models: ShiftRosterUpload, Engineer, ShiftRoster, ShiftRosterHistory
│   │   │   ├── schemas.py                 UploadSummary, EngineerResponse, ShiftRosterResponse, EngineerAvailability, etc.
│   │   │   ├── parser.py                  parse_excel() + parse_csv() → ParsedRoster (reads Day1..Day31 columns)
│   │   │   ├── repository.py              DB operations: upsert engineers, bulk insert roster, round-robin queries
│   │   │   ├── service.py                 Business logic: upload, search, get_available_engineers, update, history
│   │   │   ├── shift_time_checker.py      is_shift_active_now() — checks if shift window is active by current time/timezone
│   │   │   └── validator.py               File validation utilities
│   │   │
│   │   ├── context/
│   │   │   ├── __init__.py
│   │   │   ├── schemas.py                 IncidentContext, EngineerContext, AIContext — data contract for agents
│   │   │   ├── builder.py                 build_context() — assembles AIContext from incident + engineers (no AI, no DB)
│   │   │   ├── service.py                 ContextService.build_for_incident() — fetches data, calls builder
│   │   │   └── exceptions.py              ContextBuildError
│   │   │
│   │   └── agents/
│   │       ├── __init__.py
│   │       ├── base/
│   │       │   ├── base_agent.py          Abstract BaseAgent — validate_context(), run(), reason() lifecycle
│   │       │   ├── context.py             Helper utils: get_available_engineers(), get_engineers_by_level()
│   │       │   ├── request.py             AgentRequest(context: AIContext)
│   │       │   ├── response.py            AgentResponse(success, reasoning, confidence, result, errors)
│   │       │   └── exceptions.py          ContextValidationError, AgentReasoningError
│   │       │
│   │       └── triage/
│   │           ├── agent.py               TriageAgent — validates context, confirms assignment group, counts availability
│   │           ├── service.py             TriageService — orchestrates: LLM group resolve → context → agent → assignment → update
│   │           ├── assignment_service.py  AssignmentService — persistent round-robin engineer selection (DB-backed, concurrency safe)
│   │           ├── prompts.py             ASSIGNMENT_GROUPS list, COMMON_QUEUE_GROUPS set, is_common_queue(), LLM prompt builder
│   │           ├── schemas.py             EngineerRecommendation, TriageResult
│   │           ├── models.py              AssignmentGroupRRState, AssignmentHistory (DB models)
│   │           └── round_robin.py         In-memory round-robin fallback (superseded by DB-backed AssignmentService)
│   │
│   ├── ai_platform/
│   │   ├── llm/
│   │   │   └── groq_client.py             Shared AsyncGroq client singleton
│   │   ├── services/
│   │   │   └── llm_service.py             LLMService.complete() — shared LLM call used by any agent
│   │   └── tools/
│   │       ├── base_tool.py               BaseTool ABC + ToolResult — all tools inherit from this
│   │       ├── incident_tool.py            Placeholder — agent access to IncidentService (future)
│   │       ├── shift_roster_tool.py        Placeholder — agent access to ShiftRosterService (future)
│   │       └── knowledge_tool.py           Placeholder — knowledge base tool (future)
│   │
│   ├── integrations/
│   │   ├── servicenow/                    Placeholder — ServiceNow repository swap (future)
│   │   ├── teams/                         Placeholder — MS Teams notifications (future)
│   │   ├── email/                         Placeholder — email notifications (future)
│   │   └── cmdb/                          Placeholder — CMDB integration (future)
│   │
│   ├── platform/
│   │   ├── caching/                       Placeholder — Redis cache (future)
│   │   ├── events/                        Placeholder — event bus (future)
│   │   ├── messaging/                     Placeholder — message queue (future)
│   │   ├── scheduler/                     Placeholder — job scheduler (future)
│   │   ├── telemetry/                     Placeholder — observability (future)
│   │   └── workers/                       Placeholder — background workers (future)
│   │
│   └── tests/
│       ├── conftest.py                    Test fixtures, in-memory SQLite setup, get_db override
│       ├── unit/test_incident_service.py  9 unit tests (service layer with mocks)
│       └── api/test_incidents_api.py      14 API integration tests (full HTTP via SQLite)
│
├── alembic/
│   └── versions/
│       ├── 78b5282e58c6_create_incidents_table.py
│       ├── 15fef2bf1df7_create_shift_roster_table.py
│       ├── 9092bd4e4a4f_normalized_shift_roster_schema.py
│       ├── e67628208ea8_add_assignment_rr_state_and_history.py
│       ├── 2dab1e1fa831_fix_enum_values_lowercase.py
│       └── 76deb7e985b5_shift_roster_string_columns.py
│
├── scripts/
│   └── check_roster_data.py               Debug: shows DB groups, shift_roster count, today's roster
│
├── docs/implementation.md                 This file
├── alembic.ini
├── pyproject.toml
├── pytest.ini
├── .env / .env.example
└── README.md
```

---

# Phase 1 — Foundation ✅

Setup, config, logging, CORS, exception handling, API versioning, health endpoints, Swagger.

**Health endpoints:**
- `GET /v1/health` — app liveness
- `GET /v1/db-health` — PostgreSQL connectivity (SELECT 1)
- `GET /v1/ai-health` — Groq LLM ping test
- `GET /v1/shift-status` — shows which shifts are active right now

---

# Phase 2 — Incident Module ✅

## Database
Table: `incidents`

| Field | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| incident_number | String | INC0000001, unique, indexed |
| short_description | String(255) | Required |
| description | Text | Optional |
| priority | String | 1=Critical, 2=High, 3=Medium, 4=Low |
| state | String | new, in_progress, on_hold, resolved, closed, cancelled |
| category | String | network, database, software, etc. |
| assignment_group | String | target team |
| assigned_to | String | assigned engineer name |
| caller | String | reporter |
| work_notes | Text | internal notes |
| created_at / updated_at | DateTime | auto |

## REST Endpoints

| Method | URL | Description |
|---|---|---|
| POST | /v1/incidents | Create + auto-triggers triage in background |
| GET | /v1/incidents | List with pagination + filters |
| GET | /v1/incidents/search | Keyword search |
| GET | /v1/incidents/{id} | Get by UUID or INC number |
| PUT | /v1/incidents/{id} | Update |
| DELETE | /v1/incidents/{id} | Delete |

## Auto-Triage on Create
When a new incident is created via `POST /v1/incidents`, FastAPI's `BackgroundTasks` automatically triggers `TriageService.run_triage()` asynchronously. The API returns 201 immediately; triage runs in background and updates the incident.

---

# Phase 3 — Shift Roster Module ✅

## Source Data (Excel format)
```
Sheet: Roster
Columns: Assignment Group | Assigned To | Email | Shift | YYYY-MM-DD to YYYY-MM-DD | Level | 1 | 2 | ... | 31
Values:  Shift1 | Shift2 | Shift3 | WO | PL | CH | RH
```

## Shift Code Reference (constant — no DB table)
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

## Shift Time Checker (`shift_time_checker.py`)
Checks if a shift is **currently active** based on real-world clock:
```python
is_shift_active_now("Shift2")  # True if current IST time is 10:00-19:30
get_shift_status_summary()     # returns all shifts with active status
```

## Database (4 tables, all String columns — no PostgreSQL enum types)

| Table | Purpose |
|---|---|
| shift_roster_uploads | One row per uploaded file — filename, date range, counts, status |
| engineers | Master engineer records, deduplicated by email, upserted on upload |
| shift_roster | One row per engineer per day — normalized from Day1..Day31 |
| shift_roster_history | Audit trail for any post-upload manual changes |

## REST Endpoints

| Method | URL | Description |
|---|---|---|
| POST | /v1/shift-roster/upload | Upload .xlsx or .csv |
| GET | /v1/shift-roster/uploads | Upload history |
| GET | /v1/shift-roster/available | Engineers on a date (primary Triage query) |
| GET | /v1/shift-roster/search | Search with optional date + shift filter |
| PUT | /v1/shift-roster/roster/{id} | Update single daily entry + log history |
| GET | /v1/shift-roster/engineer/{email} | Engineer details |
| PUT | /v1/shift-roster/engineer/{email} | Update engineer |
| DELETE | /v1/shift-roster/engineer/{email} | Mark inactive |
| GET | /v1/shift-roster/engineer/{email}/roster | Roster for date range |
| GET | /v1/shift-roster/engineer/{email}/history | Change audit trail |

---

# Phase 5 — AI Context Builder & Triage Agent ✅

## Complete Triage Flow

```
POST /v1/incidents (new incident created)
         │
         ▼ [BackgroundTask auto-triggers]
POST /v1/triage/{incident_id}
         │
         ▼
TriageService.run_triage()
         │
         ├── Guard: state must be 'new' or 'in_progress'
         │         assigned_to must be empty
         │
         ▼
Step 1: Resolve Assignment Group
         │
    incident.assignment_group set AND not common queue?
    ├── YES → use it directly
    └── NO  → LLM (Groq llama-3.3-70b) analyzes:
                  short_description + description + work_notes
                  picks from ASSIGNMENT_GROUPS hardcoded list
                  updates incident.assignment_group
         │
         ▼
Step 2: Build AIContext (ContextService)
         │
    IncidentService.get_incident()       → IncidentContext
    ShiftRosterService.get_available_engineers(date, group) → list[EngineerContext]
         │
    Each EngineerContext includes:
      current_shift (Shift1/WO/PL etc.)
      is_available (shift is a working shift)
      is_shift_active (shift window is active right now)
         │
         ▼
Step 3: TriageAgent.run(AIContext)
         │
    Validates: assignment_group must exist
    Returns: group confirmed + availability count
         │
         ▼
Step 4: AssignmentService.assign_engineer()
         │
    Priority 1: engineers where is_shift_active=True (active window NOW)
    Priority 2: fallback to engineers where is_available=True (working shift today)
    If none: return NO_AVAILABLE_ENGINEER
         │
    Round-robin selection (DB-persisted per assignment group):
      SELECT rr_state FOR UPDATE (concurrency safe)
      next_index = (last_index + 1) % len(available)
      saves to assignment_history
         │
         ▼
Step 5: IncidentService.update_incident()
    assigned_to = selected engineer name
    state       = 'in_progress'
    work_notes  = triage reasoning + shift info
         │
         ▼
PostgreSQL updated
```

## Assignment Group Classification

```python
# prompts.py
COMMON_QUEUE_GROUPS = {
    "IT Service Desk", "IT Helpdesk", "General IT Support",
    "L1 Support", "Enterprise Support", "General Support",
    "Technical Support", "Service Operations"
}

ASSIGNMENT_GROUPS = [
    "Windows Support", "Network Support", "Database Support",
    "Linux Support", "Cloud Infrastructure", ... (20 total)
]
```

When `incident.assignment_group` is in `COMMON_QUEUE_GROUPS` or is `None`, LLM determines the real group from `ASSIGNMENT_GROUPS`.

## Context Schemas

```python
# modules/context/schemas.py
IncidentContext   # incident_id, number, description, priority, category, assignment_group
EngineerContext   # engineer_id, name, email, group, level, current_shift, is_available, is_shift_active
AIContext         # incident + engineers + context_date + created_at + context_version
```

## AI Platform (Shared LLM Layer)

```
ai_platform/llm/groq_client.py       Singleton AsyncGroq client
ai_platform/services/llm_service.py  LLMService.complete(messages) → string
                                      Used by TriageService for group resolution
                                      Reusable by any future agent
```

## Assignment DB Tables

| Table | Purpose |
|---|---|
| assignment_group_rr_state | Persists round-robin index per group (survives restarts) |
| assignment_history | Full audit trail: who was assigned, when, which shift, which index |

## Debug Endpoints

```
GET /v1/triage/{incident_id}/context   Preview AIContext without running agent
GET /v1/shift-status                   See which shifts are active right now
GET /v1/ai-health                      Test Groq API connectivity
```

---

# All Active API Routes

```
GET  /v1/health
GET  /v1/db-health
GET  /v1/ai-health
GET  /v1/shift-status

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

POST /v1/triage/{incident_id}
GET  /v1/triage/{incident_id}/context
```

---

# Running the Application

```bash
venv\Scripts\activate
pip install -e .
alembic upgrade head
uvicorn app.main:app --reload
```

| URL | Purpose |
|---|---|
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/v1/health | App health |
| http://localhost:8000/v1/ai-health | Groq LLM test |
| http://localhost:8000/v1/shift-status | Active shifts now |
| http://localhost:8000/v1/triage/{id}/context | Preview AIContext |

---

# Tests

```bash
pytest app/tests/unit/    # 9 unit tests
pytest app/tests/api/     # 14 API integration tests
pytest                    # all 23
```

---

# Not Yet Implemented (Future Phases)

| Module | Location | Purpose |
|---|---|---|
| Acknowledgement Agent | modules/agents/acknowledgement/ | Auto-acknowledge assigned incidents |
| Pending Agent | modules/agents/pending/ | Remind on pending incidents |
| Resolution Agent | modules/agents/resolution/ | Auto-resolve known issues |
| Orchestrator | modules/orchestrator/ | Coordinate multiple agents |
| Users / Auth | modules/users/ | JWT authentication |
| Knowledge Base | modules/knowledge/ | Historical resolution data |
| Analytics | modules/analytics/ | Dashboards, metrics |
| Audit | modules/audit/ | System-wide audit log |
| ServiceNow Integration | integrations/servicenow/ | Replace repository layer |
| LLM Tools | ai_platform/tools/ | Agent-to-service tool layer |
| Platform Services | platform/ | Events, caching, messaging, scheduler |
