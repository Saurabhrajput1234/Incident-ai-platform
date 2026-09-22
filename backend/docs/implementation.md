# Incident AI Platform — Complete Implementation Documentation

---

## Project Overview

Production-ready AI Incident Management Platform built with FastAPI.
Uses Clean Architecture: API → Service → Repository → PostgreSQL.
AI agents are coordinated by an **in-process event-driven orchestration layer** — no direct calls between agents.

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
| anthropic | latest | Anthropic Claude LLM API client |
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
ANTHROPIC_API_KEY=sk-ant-...your-anthropic-key...
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
ANTHROPIC_MAX_TOKENS=1024
ANTHROPIC_TEMPERATURE=0.0
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
│   │   ├── dependencies.py                Shared API dependencies
│   │   └── v1/
│   │       ├── health.py                  GET /v1/health — app liveness
│   │       ├── db_health.py               GET /v1/db-health — PostgreSQL connectivity
│   │       ├── ai_health.py               GET /v1/ai-health — Anthropic LLM test
│   │       │                              GET /v1/shift-status — current active shifts
│   │       ├── incidents.py               Incident CRUD — event bus handles agent triggers
│   │       ├── shift_roster.py            Roster upload, engineer management APIs
│   │       └── triage.py                  POST /v1/triage/{id} — manual triage trigger
│   │                                      GET  /v1/triage/{id}/context — preview AIContext
│   │
│   ├── core/
│   │   ├── config/                        App, DB, logging, security, AI settings
│   │   ├── lifecycle.py                   Startup: registers event handlers + starts scheduler
│   │   ├── logging.py                     Logger setup
│   │   └── middleware.py                  CORS middleware
│   │
│   ├── orchestrator/                      ← Event-Driven Orchestration Layer
│   │   ├── bus.py                         EventBus class + event_bus singleton
│   │   ├── events.py                      IncidentCreatedEvent, IncidentStateChangedEvent, WorkNoteAddedEvent
│   │   ├── registry.py                    Wires all handlers to bus (called once at startup)
│   │   └── handlers/
│   │       ├── triage.py                  IncidentCreatedEvent(state=new) → TriageService
│   │       ├── acknowledgement.py         IncidentStateChangedEvent(→in_progress, by=TriageAgent) → AcknowledgementService
│   │       ├── pending.py                 IncidentStateChangedEvent(→on_hold, not by PendingAgent) → PendingService
│   │       └── resolution.py             IncidentStateChangedEvent(on_hold→in_progress, source=USER) → ResolutionService
│   │
│   ├── modules/
│   │   ├── incidents/
│   │   │   ├── enums.py                   Priority, State, Category, Impact, Urgency, Source enums
│   │   │   ├── model.py                   SQLAlchemy Incident model
│   │   │   ├── schemas.py                 IncidentCreate, IncidentUpdate, IncidentResponse
│   │   │   ├── repository.py              All SQL queries
│   │   │   └── service.py                 Business logic + publishes IncidentCreatedEvent / IncidentStateChangedEvent
│   │   │
│   │   ├── work_notes/
│   │   │   ├── enums.py                   WorkNoteSourceType, WorkNoteActionType
│   │   │   ├── model.py                   IncidentWorkNote SQLAlchemy model
│   │   │   ├── schemas.py                 WorkNoteCreate, WorkNoteResponse
│   │   │   ├── repository.py              DB queries for work notes
│   │   │   └── service.py                 add_note() — persists note, publishes WorkNoteAddedEvent, handles auto-activation
│   │   │
│   │   ├── pending_cycles/
│   │   │   ├── model.py                   PendingCycle SQLAlchemy model
│   │   │   ├── repository.py              get_due_active_cycles(), CRUD
│   │   │   └── service.py                 create_cycle_if_not_exists(), increment_reminder(), complete_cycle(), cancel_active_cycle()
│   │   │
│   │   ├── shift_roster/                  ShiftRosterUpload, Engineer, ShiftRoster, ShiftRosterHistory
│   │   ├── context/                       AIContext builder — incident + engineer context for agents
│   │   │
│   │   └── agents/
│   │       ├── base/                      BaseAgent, AgentRequest, AgentResponse
│   │       ├── triage/                    TriageAgent + TriageService + AssignmentService
│   │       ├── acknowledgement/           AcknowledgementAgent + AcknowledgementService + TemplateRenderer
│   │       ├── pending/                   PendingAgent + PendingService + Scheduler + ReminderRenderer
│   │       └── resolution/                ResolutionAgent + ResolutionService + NotificationService
│   │
│   ├── ai_platform/
│   │   ├── llm/anthropic_client.py        Singleton AsyncAnthropic client
│   │   └── services/llm_service.py        LLMService.complete() — used by all four agents
│   │
│   ├── integrations/
│   │   └── notifications/                 NotificationService — simulated Teams + Email delivery
│   │
│   └── tests/
│       ├── conftest.py                    Test fixtures, in-memory SQLite, get_db override
│       ├── unit/                          280+ unit + property-based tests
│       └── api/                           API integration tests
│
├── docs/
│   ├── implementation.md                  This file
│   └── event_driven_orchestration.md      Full orchestration flow documentation
│
├── alembic/versions/                      DB migration scripts
├── pyproject.toml
├── pytest.ini
└── .env
```

---

# Phase 1 — Foundation ✅

Setup, config, logging, CORS, exception handling, API versioning, health endpoints, Swagger.

**Health endpoints:**
- `GET /v1/health` — app liveness
- `GET /v1/db-health` — PostgreSQL connectivity (SELECT 1)
- `GET /v1/ai-health` — Anthropic Claude LLM ping test
- `GET /v1/shift-status` — shows which shifts are active right now

---

# Phase 2 — Incident Module ✅

## Database: `incidents` table

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
| created_at / updated_at | DateTime | auto |

## Database: `incident_work_notes` table

Structured, queryable work note history. Replaces the flat `work_notes` text field.

| Field | Notes |
|---|---|
| id | UUID primary key |
| incident_id | FK → incidents |
| message | The note body |
| source_type | USER / ENGINEER / TRIAGE_AGENT / ACKNOWLEDGEMENT_AGENT / PENDING_AGENT / SYSTEM |
| source_name | Human-readable name |
| action_type | INCIDENT_CREATE / ASSIGN_ENGINEER / STATE_CHANGE / SEND_ACKNOWLEDGEMENT / SEND_REMINDER / etc. |
| created_at | Timestamp |

## REST Endpoints

| Method | URL | Description |
|---|---|---|
| POST | /v1/incidents | Create — event bus triggers Triage automatically |
| GET | /v1/incidents | List with pagination + filters |
| GET | /v1/incidents/search | Keyword search |
| GET | /v1/incidents/{id} | Get by UUID or INC number |
| PUT | /v1/incidents/{id} | Update |
| DELETE | /v1/incidents/{id} | Delete |

---

# Phase 3 — Shift Roster Module ✅

## Shift Codes

| Code | Label | Timing | Working |
|---|---|---|---|
| Shift1 | Shift 1 | 12:30 PM IST - 09:30 PM IST | ✅ |
| Shift2 | Shift 2 | 10:00 AM IST - 07:30 PM IST | ✅ |
| Shift3 | Shift 3 | 08:00 AM EST - 05:00 PM EST | ✅ |
| WO | Week Off | — | ❌ |
| PL | Planned Leave | — | ❌ |
| CH | Company Holiday | — | ❌ |
| RH | Restricted Holiday | — | ❌ |

## REST Endpoints

| Method | URL | Description |
|---|---|---|
| POST | /v1/shift-roster/upload | Upload .xlsx or .csv |
| GET | /v1/shift-roster/uploads | Upload history |
| GET | /v1/shift-roster/available | Engineers available on a date |
| GET | /v1/shift-roster/search | Search with filters |
| PUT | /v1/shift-roster/roster/{id} | Update daily entry |
| GET/PUT/DELETE | /v1/shift-roster/engineer/{email} | Engineer CRUD |

---

# Phase 4 — Event-Driven Orchestration ✅

Agents are coordinated by an **in-process async event bus**. No direct agent-to-agent calls.

## How It Works

```
Service Layer → publishes Event → EventBus → dispatches to Handler → runs Agent
```

## Event Subscriptions

| Event | Handler | Condition |
|-------|---------|-----------|
| `IncidentCreatedEvent` | `TriageHandler` | `state == "new"` |
| `IncidentStateChangedEvent` | `AcknowledgementHandler` | `current == "in_progress"` AND `changed_by == "TriageAgent"` |
| `IncidentStateChangedEvent` | `PendingHandler` | `current == "on_hold"` AND `changed_by != "PendingAgent"` |
| `IncidentStateChangedEvent` | `ResolutionHandler` | `previous == "on_hold"` AND `current == "in_progress"` AND `source == USER` |

See `docs/event_driven_orchestration.md` for the complete lifecycle flow.

## Loop Prevention

| Scenario | Mechanism |
|----------|-----------|
| Pending reminder → no new cycle | `changed_by="PendingAgent"` → PendingHandler skips |
| ACK agent sets ON_HOLD → no Resolution | `triggering_work_note_source != USER` → ResolutionHandler skips |
| Pending Agent SEND_REMINDER → no Resolution | `source=PENDING_AGENT` in `_NON_USER_SOURCES` |
| Duplicate PendingHandler calls | Idempotency gate: preserve existing active cycle |

---

# Phase 5 — Four AI Agents ✅

## Agent 1: Triage Agent

**Trigger:** `IncidentCreatedEvent(state="new")`

**Flow:**
1. LLM resolves assignment group → `GROUP_RESOLVED` work note
2. Build AIContext (incident + engineers for that group on today's date)
3. Round-robin select engineer → `update_incident_internal(assigned_to=eng.name)` ← no event
4. Write `ASSIGN_ENGINEER` work note ← committed BEFORE state change
5. `update_incident_internal(state="in_progress", changed_by="TriageAgent")` → fires ACK

**Work notes
 produced:**
```
INCIDENT_CREATE   (System)
GROUP_RESOLVED    (TriageAgent)
ASSIGN_ENGINEER   (TriageAgent)
```

---

## Agent 2: Acknowledgement Agent

**Trigger:** `IncidentStateChangedEvent(→in_progress, changed_by="TriageAgent")`

**Intent classification:**
- `STANDARD_INCIDENT` → state stays `in_progress`, no pending cycle
- `ACCESS_REQUEST` / `SERVICE_REQUEST` / `WRONG_REQUEST` / `SALESFORCE_INCORRECT_REQUEST` → state → `on_hold` → triggers Pending Agent

**Work notes produced:**
```
SEND_ACKNOWLEDGEMENT  (AcknowledgementAgent) — email content + intent info
```

---

## Agent 3: Pending Agent (Reminder Cycle)

**Trigger:** `IncidentStateChangedEvent(→on_hold, changed_by != "PendingAgent")`

**Initial call (force_reminder=False):**
- If active cycle exists → preserve (idempotency)
- Otherwise → create `PendingCycle(max_reminders=3)`, schedule Reminder 1

**Scheduler fires each due reminder (force_reminder=True):**

```
For each reminder (1/3, 2/3, 3/3):
  1. Render reminder email
  2. SEND_REMINDER work note (auto_activate=True)
       └── State: on_hold → in_progress (auto-activation, shows activity)
  3. update_incident_internal(state="on_hold", changed_by="PendingAgent")
       └── State restored: in_progress → on_hold
  4. STATE_CHANGE work note: "State restored to On Hold after reminder N sent"
  5. If NOT final: schedule next reminder
     If FINAL: complete_cycle() — no more reminders, incident stays on_hold
```

**Work notes produced per reminder:**
```
SEND_REMINDER   (PENDING AGENT)  — reminder email content
STATE_CHANGE    (System)         — "Incident automatically moved to In Progress"
STATE_CHANGE    (PENDING AGENT)  — "State restored to On Hold after reminder N sent"
```

**Configuration:** `REMINDER_INTERVAL_SECONDS = 20` (dev) / `3600` (prod)

**After all reminders exhausted:** Cycle COMPLETED. Incident stays `on_hold`. Manual engineer action required.

---

## Agent 4: Resolution Alert Agent

**Trigger:** `IncidentStateChangedEvent(previous=on_hold, current=in_progress, triggering_work_note_source=USER)`

This fires AFTER the state is already `in_progress` (correct audit order):
```
User adds work note → auto-activation: on_hold → in_progress → Resolution Agent triggers
```

**Flow:**
1. Validate: `previous=on_hold`, `current=active`, `source=USER`
2. Load triggering work note by ID (the user's note, not the SYSTEM audit note)
3. Cancel active `PendingCycle` (user responded — no more reminders needed)
4. LLM classifies user intent:
   - **Positive:** `ISSUE_RESOLVED` / `REQUEST_COMPLETED` / `REQUIRED_ACTION_COMPLETED`
   - **Non-positive:** `ESCALATION_REQUIRED` / `CLARIFICATION_NEEDED` / `REJECTED`
5. Check provenance:
   - Requires non-standard ACK template note
   - Blocks if ENGINEER note exists after ACK note
6. Send Teams → assigned engineer (always)
7. Send Email → assignment group (positive intent only)
8. If positive + provenance confirmed → `state = resolved`

**Work notes produced:**
```
SEND_ACKNOWLEDGEMENT  (ResolutionAgent)  — [TEAMS] notification
SEND_ACKNOWLEDGEMENT  (ResolutionAgent)  — [EMAIL] notification (if positive)
STATE_CHANGE          (ResolutionAgent)  — "Incident auto-resolved" (if positive + provenance)
SYSTEM_NOTE           (ResolutionAgent)  — reason if no auto-resolve
```

---

# AI Platform (Shared LLM Layer)

```
ai_platform/llm/anthropic_client.py    Singleton AsyncAnthropic client
ai_platform/services/llm_service.py    LLMService.complete(messages) → string
```

**LLM Provider:** Anthropic Claude 3.5 Sonnet  
**Max Tokens:** 1024 (configurable)  
Used by: TriageService, AcknowledgementAgent, PendingWorkNoteAnalyzer, ResolutionAgent

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
POST   /v1/incidents/bulk-import

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
| http://localhost:8000/v1/ai-health | Anthropic LLM test |
| http://localhost:8000/v1/shift-status | Active shifts now |

---

# Tests

```bash
pytest app/tests/unit/    # 250+ unit + property-based tests
pytest app/tests/api/     # API integration tests
pytest                    # all 280+
```

---

# Not Yet Implemented (Future Phases)

| Module | Location | Purpose |
|---|---|---|
| Users / Auth | modules/users/ | JWT authentication |
| Knowledge Base | modules/knowledge/ | Historical resolution data, FAQs |
| Analytics | modules/analytics/ | Dashboards, MTTR metrics |
| ServiceNow Integration | integrations/servicenow/ | Replace repository with ServiceNow API |
| Real Email/Teams | integrations/notifications/ | Live delivery (currently simulated) |
| Redis Event Bus | platform/events/ | Replace in-process bus for multi-instance deployments |
| Rate Limiting | — | API request throttling |
