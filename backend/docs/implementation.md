# Incident AI Platform — Complete Implementation Documentation

---

## Project Overview

Production-ready AI Incident Management Platform built with FastAPI.
Architecture follows Clean Architecture principles:

```
API Layer → Service Layer → Repository Layer → Database
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
| openpyxl | 3.1.2 | Excel file parsing |
| python-multipart | 0.0.9 | File upload support |
| pytest | 7.4.4 | Testing |
| pytest-asyncio | 0.23.3 | Async test support |
| httpx | 0.26.0 | HTTP client for tests |
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
│   │       └── shift_roster.py
│   ├── core/
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   ├── app.py
│   │   │   ├── database.py
│   │   │   ├── logging.py
│   │   │   ├── security.py
│   │   │   └── settings.py
│   │   ├── lifecycle.py
│   │   ├── logging.py
│   │   └── middleware.py
│   ├── common/
│   │   ├── constants/app.py
│   │   ├── enums/base.py
│   │   ├── exceptions/
│   │   │   ├── base.py
│   │   │   └── handlers.py
│   │   ├── responses/base.py
│   │   ├── schemas/pagination.py
│   │   ├── utils/datetime.py
│   │   ├── utils/uuid.py
│   │   └── validators/common.py
│   ├── database/
│   │   └── postgres/
│   │       ├── base.py
│   │       └── session.py
│   ├── modules/
│   │   ├── incidents/
│   │   │   ├── enums.py
│   │   │   ├── model.py
│   │   │   ├── schemas.py
│   │   │   ├── repository.py
│   │   │   └── service.py
│   │   └── shift_roster/
│   │       ├── enums.py
│   │       ├── model.py
│   │       ├── schemas.py
│   │       ├── repository.py
│   │       ├── service.py
│   │       └── parser.py
│   ├── platform/
│   │   ├── caching/ events/ execution/ messaging/
│   │   ├── registry/ scheduler/ telemetry/ workers/
│   ├── ai_platfrom/
│   ├── integrations/
│   ├── workers/
│   └── tests/
│       ├── conftest.py
│       ├── api/test_incidents_api.py
│       └── unit/test_incident_service.py
├── alembic/
│   └── versions/
│       ├── 78b5282e58c6_create_incidents_table.py
│       ├── 15fef2bf1df7_create_shift_roster_table.py
│       └── 9092bd4e4a4f_normalized_shift_roster_schema.py
├── scripts/
│   └── seed_incidents.py
├── docs/
├── alembic.ini
├── pyproject.toml
├── pytest.ini
├── .env / .env.example
└── README.md
```

---

# Phase 1 — Foundation ✅

| Task | Status |
|---|---|
| Project folder structure | ✅ |
| Virtual environment | ✅ |
| Dependency management | ✅ |
| Configuration (.env) | ✅ |
| FastAPI application | ✅ |
| Logging | ✅ |
| CORS Middleware | ✅ |
| Exception handling | ✅ |
| API versioning | ✅ |
| Health APIs | ✅ |
| Swagger / OpenAPI | ✅ |
| README | ✅ |
| Git repository | ⏸️ Deferred |

## Environment Variables

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
ACCESS_TOKEN_EXPIRE_MINUTES=30
ALGORITHM=HS256
```

## Health Endpoints

| Method | URL | Description |
|---|---|---|
| GET | /v1/health | App liveness |
| GET | /v1/db-health | DB connectivity |

---

# Phase 2 — Database Foundation ✅

| Task | Status |
|---|---|
| PostgreSQL connection | ✅ |
| SQLAlchemy async engine | ✅ |
| Alembic setup + versions folder | ✅ |
| Database session dependency | ✅ |
| Base model | ✅ |
| DB Health API | ✅ |

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

---

# Phase 2 — Incident Module ✅

## Architecture
```
API → Service → Repository → PostgreSQL
```

## Files
| File | Purpose |
|---|---|
| enums.py | Priority, State, Category, Impact, Urgency, Environment, Source |
| model.py | SQLAlchemy Incident model (incidents table) |
| schemas.py | IncidentCreate, IncidentUpdate, IncidentResponse, IncidentListResponse |
| repository.py | DB-only: create, get, list, update, delete, search |
| service.py | Business logic, validation, error handling |

## REST Endpoints

| Method | URL | Description |
|---|---|---|
| POST | /v1/incidents | Create incident (201) |
| GET | /v1/incidents | List with pagination + filters |
| GET | /v1/incidents/search | Keyword search |
| GET | /v1/incidents/{id} | Get by ID |
| PUT | /v1/incidents/{id} | Update |
| DELETE | /v1/incidents/{id} | Delete (204) |

### List Query Params
`page`, `page_size`, `priority`, `state`, `category`, `assignment_group`, `sort_by`, `sort_order`

### Search Query Params
`q` (min 2 chars), `page`, `page_size`, `priority`, `state`, `category`, `assignment_group`

## Seed Data
```bash
python scripts/seed_incidents.py   # inserts 100 realistic incidents
```

## Tests
```bash
pytest app/tests/unit/   # 9 unit tests (service layer with mocks)
pytest app/tests/api/    # 14 integration tests (full HTTP via SQLite)
pytest                   # all 23
```

---

# Phase 3 — Shift Roster Module ✅

## Objective
Store and query monthly/weekly engineer shift schedules uploaded via Excel (.xlsx) or CSV.
Provides the Triage Agent with engineer availability data.

## Source Data (Excel format)
```
Sheet: Roster
Columns: Assignment Group | Assigned To | Email | Shift | 2026-07-01 to 2026-07-31 | Level | 1 | 2 | ... | 31
Values:  Shift1 | Shift2 | Shift3 | WO | PL | CH | RH
```

## Shift Code Definitions (constant in enums.py)

| Code | Label | Timing | Working |
|---|---|---|---|
| Shift1 | Shift 1 | 12:30 PM IST - 09:30 PM IST | ✅ |
| Shift2 | Shift 2 | 10:00 AM IST - 07:30 PM IST | ✅ |
| Shift3 | Shift 3 | 08:00 AM EST - 05:00 PM EST | ✅ |
| WO | Week Off | — | ❌ |
| PL | Planned Leave | — | ❌ |
| CH | Company Holiday | — | ❌ |
| RH | Restricted Holiday | — | ❌ |

Import in code:
```python
from app.modules.shift_roster.enums import SHIFT_DEFINITIONS, WORKING_SHIFTS, NON_WORKING_CODES
```

## Normalized Database Design (4 tables)

```
shift_roster_uploads  ──► shift_roster ◄── engineers
                                │
                                ▼
                      shift_roster_history
```

### Table 1: shift_roster_uploads
Metadata for every uploaded file.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| file_name | String | uploaded filename |
| roster_start_date | Date | from Excel header |
| roster_end_date | Date | from Excel header |
| uploaded_by | String | optional |
| uploaded_at | DateTime | auto |
| total_records | Int | rows in file |
| imported_records | Int | successfully saved |
| failed_records | Int | skipped rows |
| upload_status | Enum | success / partial / failed |

### Table 2: engineers
Master engineer records. Email is unique — used for deduplication.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| assignment_group | String | indexed |
| assigned_to | String | indexed |
| email | String | unique, indexed |
| default_shift | String | from Excel |
| level | Enum | L1/L2/L3, indexed |
| status | Enum | active/inactive, indexed |
| created_at / updated_at | DateTime | auto |

### Table 3: shift_roster
One row per engineer per day — normalized from Day1..Day31.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| upload_id | FK | → shift_roster_uploads |
| engineer_id | FK | → engineers |
| roster_date | Date | indexed |
| shift_code | Enum | Shift1/WO/PL etc., indexed |
| created_at / updated_at | DateTime | auto |

### Table 4: shift_roster_history
Audit trail for post-upload changes.

| Field | Type | Notes |
|---|---|---|
| id | UUID | PK |
| roster_id | FK | → shift_roster |
| engineer_id | FK | → engineers |
| roster_date | Date | |
| previous_shift | Enum | |
| new_shift | Enum | |
| changed_by | String | optional |
| changed_at | DateTime | auto |
| reason | Text | optional |

## Import Process

```
Upload file (.xlsx / .csv)
    ↓
Validate file type + sheet name
    ↓
Parse rows → extract engineer + daily shifts
    ↓
For each engineer:
    Email exists? → Update master record
    Email new?   → Insert new engineer
    ↓
Delete existing roster for same date range
    ↓
Convert Day1..Day31 → daily shift_roster rows
    ↓
Bulk insert + commit
    ↓
Update upload summary (imported / failed / status)
```

## Files

| File | Purpose |
|---|---|
| enums.py | ShiftCode, EngineerLevel, EngineerStatus, UploadStatus, SHIFT_DEFINITIONS |
| model.py | 4 SQLAlchemy models |
| schemas.py | UploadSummary, EngineerResponse, EngineerUpdate, ShiftRosterResponse, ShiftRosterUpdate, EngineerAvailability, RosterHistoryResponse |
| parser.py | parse_excel() + parse_csv() → ParsedRoster |
| repository.py | All DB operations — no business logic |
| service.py | Business logic — no SQL queries |

## REST Endpoints

| Method | URL | Description |
|---|---|---|
| POST | /v1/shift-roster/upload | Upload .xlsx or .csv file |
| GET | /v1/shift-roster/uploads | Upload history |
| GET | /v1/shift-roster/available | Triage Agent — engineers on a date |
| GET | /v1/shift-roster/search | Search engineers with optional date |
| PUT | /v1/shift-roster/roster/{roster_id} | Update daily entry + log history |
| GET | /v1/shift-roster/engineer/{email} | Engineer details |
| PUT | /v1/shift-roster/engineer/{email} | Update engineer |
| DELETE | /v1/shift-roster/engineer/{email} | Mark inactive |
| GET | /v1/shift-roster/engineer/{email}/roster | Roster for date range |
| GET | /v1/shift-roster/engineer/{email}/history | Change audit trail |

### GET /v1/shift-roster/available
Required: `roster_date`
Optional: `shift_code`, `assignment_group`, `level`

### GET /v1/shift-roster/search
Optional: `assignment_group`, `level`, `name`, `email`, `status`, `roster_date`, `shift_code`

Without `roster_date` → returns engineer info only
With `roster_date` → returns engineer + their shift on that day

## Triage Agent Integration

The `/available` and `/search` endpoints are the primary interfaces for the Triage Agent:

```python
# Who is working Shift1 in Database team today?
GET /v1/shift-roster/available?roster_date=2026-07-15&shift_code=Shift1&assignment_group=Database

# Who is on leave today?
GET /v1/shift-roster/available?roster_date=2026-07-15&shift_code=PL

# All L2 engineers and their shift today
GET /v1/shift-roster/search?level=L2&roster_date=2026-07-15
```

---

# Running the Application

```bash
# Activate venv
venv\Scripts\activate

# Install dependencies
pip install -e .

# Apply all migrations
alembic upgrade head

# Seed incidents
python scripts/seed_incidents.py

# Run server
uvicorn app.main:app --reload
```

| URL | Purpose |
|---|---|
| http://localhost:8000/v1/health | App health |
| http://localhost:8000/v1/db-health | DB health |
| http://localhost:8000/v1/incidents | Incident list |
| http://localhost:8000/v1/shift-roster/search | Engineer search |
| http://localhost:8000/v1/shift-roster/available | Triage availability |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/redoc | ReDoc |

---

# Not Yet Implemented (Future Phases)

| Phase | Module |
|---|---|
| 4 | Authentication / JWT |
| 4 | Users module |
| 5 | AI Platform / LLM integration |
| 5 | Agents: Triage, Acknowledgement, Pending, Resolution |
| 5 | Orchestrator |
| 6 | ServiceNow integration (swap repository layer) |
| 6 | Knowledge base |
| 6 | Analytics / Audit |
| 7 | Platform: Events, Messaging, Caching, Scheduler, Telemetry |
| 7 | Background Workers |
