# Incident AI Platform — Complete Implementation Documentation

---

## Project Overview

Production-ready AI Incident Management Platform built with FastAPI.
Architecture follows Clean Architecture principles:

```
API Layer → Service Layer → Repository Layer → Database
```

Business logic never lives in API routes.
Database can be replaced (e.g. PostgreSQL → ServiceNow) by swapping only the repository layer.

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
| python-dotenv | 1.0.0 | .env loading |
| pytest | 7.4.4 | Testing |
| pytest-asyncio | 0.23.3 | Async test support |
| httpx | 0.26.0 | HTTP client for tests |
| aiosqlite | — | In-memory SQLite for tests |

---

## Full Project Structure

```
backend/
├── app/
│   ├── main.py                            # FastAPI app bootstrap
│   ├── __init__.py
│   │
│   ├── api/
│   │   ├── router.py                      # Central router — registers all versioned routers
│   │   ├── dependencies.py                # Shared API dependencies (placeholder)
│   │   └── v1/
│   │       ├── health.py                  # GET /v1/health
│   │       ├── db_health.py               # GET /v1/db-health
│   │       └── incidents.py               # Incident REST endpoints
│   │
│   ├── core/
│   │   ├── config/
│   │   │   ├── __init__.py                # Exports settings singleton
│   │   │   ├── app.py                     # App name, version, CORS, prefix
│   │   │   ├── database.py                # DATABASE_URL
│   │   │   ├── logging.py                 # LOG_LEVEL
│   │   │   ├── security.py                # SECRET_KEY, JWT config
│   │   │   └── settings.py                # Merges all config → settings instance
│   │   ├── lifecycle.py                   # Startup / shutdown events
│   │   ├── logging.py                     # Logger configuration
│   │   └── middleware.py                  # CORS middleware registration
│   │
│   ├── common/
│   │   ├── constants/
│   │   │   └── app.py                     # DEFAULT_PAGE_SIZE, date formats
│   │   ├── enums/
│   │   │   └── base.py                    # Environment, Status enums
│   │   ├── exceptions/
│   │   │   ├── base.py                    # NotFoundError, BadRequestError, etc.
│   │   │   └── handlers.py                # HTTP, validation, 500 exception handlers
│   │   ├── responses/
│   │   │   └── base.py                    # SuccessResponse[T], ErrorResponse
│   │   ├── schemas/
│   │   │   └── pagination.py              # PaginationParams, PaginatedResponse[T]
│   │   ├── security/                      # Placeholder — auth utilities (future)
│   │   ├── types/                         # Placeholder — custom types (future)
│   │   ├── utils/
│   │   │   ├── datetime.py                # utcnow(), format_datetime()
│   │   │   └── uuid.py                    # generate_uuid(), is_valid_uuid()
│   │   └── validators/
│   │       └── common.py                  # is_valid_email(), is_non_empty_string()
│   │
│   ├── database/
│   │   └── postgres/
│   │       ├── base.py                    # SQLAlchemy declarative Base
│   │       └── session.py                 # Async engine + session factory + get_db()
│   │
│   ├── modules/
│   │   ├── incidents/                     # ✅ Implemented (Phase 2)
│   │   │   ├── __init__.py
│   │   │   ├── enums.py                   # Priority, State, Category, Impact, etc.
│   │   │   ├── model.py                   # SQLAlchemy Incident model
│   │   │   ├── schemas.py                 # Pydantic schemas (Create/Update/Response)
│   │   │   ├── repository.py              # DB operations only
│   │   │   └── service.py                 # Business logic layer
│   │   ├── agents/                        # Placeholder — future AI agents
│   │   │   ├── triage/
│   │   │   ├── acknowledgement/
│   │   │   ├── pending/
│   │   │   └── resolution/
│   │   ├── analytics/                     # Placeholder
│   │   ├── audit/                         # Placeholder
│   │   ├── knowledge/                     # Placeholder
│   │   ├── orchestrator/                  # Placeholder
│   │   ├── settings/                      # Placeholder
│   │   └── users/                         # Placeholder
│   │
│   ├── platform/                          # Infrastructure platform layer (future)
│   │   ├── caching/
│   │   ├── events/
│   │   ├── execution/
│   │   ├── messaging/
│   │   ├── registry/
│   │   ├── scheduler/
│   │   ├── telemetry/
│   │   └── workers/
│   │
│   ├── ai_platfrom/                       # AI platform integrations (future)
│   ├── integrations/                      # External integrations e.g. ServiceNow (future)
│   ├── workers/                           # Background workers (future)
│   └── tests/
│       ├── conftest.py                    # Fixtures, test DB setup
│       ├── api/
│       │   └── test_incidents_api.py      # 14 integration tests
│       ├── unit/
│       │   └── test_incident_service.py   # 9 unit tests
│       └── integration/                   # Placeholder
│
├── alembic/
│   ├── env.py                             # Migration environment
│   ├── script.py.mako                     # Migration file template
│   └── versions/
│       └── 78b5282e58c6_create_incidents_table.py
│
├── scripts/
│   └── seed_incidents.py                  # Seeds 100 realistic incidents
│
├── docs/
│   └── implementation.md                  # This file
│
├── docker/                                # Docker configs (future)
├── alembic.ini                            # Alembic configuration
├── pyproject.toml                         # Project dependencies
├── pytest.ini                             # Test configuration
├── .env                                   # Local environment (not committed)
├── .env.example                           # Environment template
├── .gitignore
└── README.md
```

---

# Phase 1 — Foundation ✅

## Status

| Task | Status |
|---|---|
| Project folder structure | ✅ |
| Virtual environment | ✅ |
| Dependency management (pyproject.toml) | ✅ |
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

## Setup

```bash
# 1. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux/Mac

# 2. Install dependencies
pip install -e .

# 3. Create environment file
copy .env.example .env         # then edit with your values

# 4. Run server
uvicorn app.main:app --reload
```

## Environment Variables (.env)

```env
# Application
APP_NAME=Incident AI Platform
APP_VERSION=0.1.0
ENVIRONMENT=development
DEBUG=true

# API
API_V1_PREFIX=/v1
ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:8000"]

# Logging
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/incident_ai

# Security
SECRET_KEY=changeme
ACCESS_TOKEN_EXPIRE_MINUTES=30
ALGORITHM=HS256
```

> ALLOWED_ORIGINS must be a valid JSON array string.
> If your password contains special characters, URL-encode them: @ → %40, # → %23

## Configuration (app/core/config/)

Config is split into focused files and merged in settings.py:

| File | Responsibility |
|---|---|
| app.py | APP_NAME, VERSION, ENVIRONMENT, DEBUG, API_V1_PREFIX, ALLOWED_ORIGINS |
| database.py | DATABASE_URL |
| logging.py | LOG_LEVEL |
| security.py | SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM |
| settings.py | Merges all into single Settings class → singleton `settings` |
| __init__.py | Exports `settings` for use across the app |

Import usage:
```python
from app.core.config import settings
```

## Application Entry Point (app/main.py)

Registers in order:
1. CORS Middleware via `register_middlewares(app)`
2. Exception handlers from `common/exceptions/handlers.py`
3. API router with `/v1` prefix from settings
4. FastAPI lifespan for startup/shutdown

## Logging (app/core/logging.py)

Outputs to stdout. Format:
```
2026-07-30 12:00:00,000 - name - INFO - message
```
Level controlled by `LOG_LEVEL` in .env.

## CORS Middleware (app/core/middleware.py)

`register_middlewares(app)` registers CORS with `ALLOWED_ORIGINS` from settings.
Allows all methods and headers with credentials enabled.

## Exception Handlers (app/common/exceptions/handlers.py)

| Handler | Trigger | HTTP Status |
|---|---|---|
| http_exception_handler | Any HTTPException | varies |
| validation_exception_handler | Invalid request body/params | 422 |
| general_exception_handler | Unhandled exceptions | 500 |

Response format:
```json
{"detail": "...", "status_code": 404}
```

## Custom Exception Classes (app/common/exceptions/base.py)

| Class | Status Code |
|---|---|
| NotFoundError | 404 |
| BadRequestError | 400 |
| UnauthorizedError | 401 |
| ForbiddenError | 403 |
| ConflictError | 409 |

## Health Endpoints

| Method | URL | Description |
|---|---|---|
| GET | /v1/health | App liveness check |
| GET | /v1/db-health | Database connectivity check |

GET /v1/health response:
```json
{"status": "healthy"}
```

GET /v1/db-health success:
```json
{"status": "healthy", "database": "connected"}
```

GET /v1/db-health failure:
```json
{"status": "unhealthy", "database": "disconnected", "error": "..."}
```

## Swagger / OpenAPI

Auto-generated by FastAPI:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Common Shared Components

### responses/base.py
```python
SuccessResponse[T]    # success, message, data
ErrorResponse         # success=False, message, detail, status_code
```

### schemas/pagination.py
```python
PaginationParams      # page, page_size, offset property
PaginatedResponse[T]  # items, total, page, page_size, pages
```

### constants/app.py
```python
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
```

### enums/base.py
```python
Environment   # development, staging, production, dr
Status        # active, inactive, deleted
```

### utils/datetime.py
```python
utcnow()              # current UTC datetime
utcnow_iso()          # current UTC as ISO string
format_datetime(dt)   # format datetime to string
```

### utils/uuid.py
```python
generate_uuid()       # new UUID4 string
is_valid_uuid(value)  # validate UUID string
```

### validators/common.py
```python
is_valid_email(email)        # regex email validation
is_non_empty_string(value)   # non-blank string check
```

---

# Phase 2 — Database Foundation ✅

## Status

| Task | Status |
|---|---|
| PostgreSQL connection | ✅ |
| SQLAlchemy async engine | ✅ |
| Alembic setup | ✅ |
| Database session dependency | ✅ |
| Base model | ✅ |
| DB Health API | ✅ |

## PostgreSQL Setup

1. Create database in pgAdmin or psql:
```sql
CREATE DATABASE incident_ai;
```

2. Update `.env` with credentials:
```
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/incident_ai
```

## SQLAlchemy Base (app/database/postgres/base.py)

All future models inherit from `Base`:
```python
from app.database.postgres.base import Base

class MyModel(Base):
    __tablename__ = "my_table"
    ...
```

## Async Session (app/database/postgres/session.py)

- Creates async engine from DATABASE_URL
- `echo=DEBUG` prints SQL in development
- `expire_on_commit=False` keeps objects accessible after commit
- `get_db()` is a FastAPI dependency yielding one session per request

Usage:
```python
@router.get("/example")
async def example(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MyModel))
```

## Alembic Migrations

Configuration in `alembic.ini` + `alembic/env.py`.
`env.py` reads DATABASE_URL from settings automatically.
Add new model imports to `env.py` before generating migrations.

```bash
# Generate migration after adding/changing models
alembic revision --autogenerate -m "description"

# Apply all pending migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1

# View migration history
alembic history
```

---

# Phase 2 — Incident Module ✅

## Architecture Flow

```
HTTP Request
    ↓
api/v1/incidents.py    (HTTP routing only, no logic)
    ↓
modules/incidents/service.py    (business logic, validation, error handling)
    ↓
modules/incidents/repository.py    (SQL queries only)
    ↓
PostgreSQL (incidents table)
```

## Enums (modules/incidents/enums.py)

Values are string-compatible with ServiceNow field values for future integration.

| Enum | Values |
|---|---|
| IncidentPriority | 1 (Critical), 2 (High), 3 (Medium), 4 (Low) |
| IncidentState | new, in_progress, on_hold, resolved, closed, cancelled |
| IncidentCategory | network, hardware, software, database, security, access, email, vpn, application, other |
| IncidentImpact | 1 (High), 2 (Medium), 3 (Low) |
| IncidentUrgency | 1 (High), 2 (Medium), 3 (Low) |
| IncidentEnvironment | production, staging, development, dr |
| IncidentSource | manual, monitoring, email, phone, self_service, api |

## Database Model (modules/incidents/model.py)

Table: `incidents`

| Column | Type | Notes |
|---|---|---|
| id | String(36) | UUID primary key |
| incident_number | String(20) | Unique, indexed e.g. INC0000001 |
| short_description | String(255) | Required |
| description | Text | Optional |
| priority | Enum | Default: MEDIUM |
| state | Enum | Default: NEW |
| category | Enum | Optional |
| subcategory | String(100) | Optional |
| impact | Enum | Default: MEDIUM |
| urgency | Enum | Default: MEDIUM |
| assignment_group | String(100) | Optional |
| assigned_to | String(100) | Optional |
| caller | String(100) | Optional |
| configuration_item | String(100) | CMDB reference |
| business_service | String(100) | CMDB reference |
| environment | Enum | Optional |
| source | Enum | Default: MANUAL |
| work_notes | Text | Optional |
| comments | Text | Optional |
| created_at | DateTime(tz) | Auto-set on create |
| updated_at | DateTime(tz) | Auto-set on create + update |

## Pydantic Schemas (modules/incidents/schemas.py)

| Schema | Purpose |
|---|---|
| IncidentCreate | POST request body — only short_description required |
| IncidentUpdate | PUT request body — all fields optional |
| IncidentResponse | Single incident API response |
| IncidentListResponse | Paginated list response with metadata |

`use_enum_values=True` — serialises enums as strings in Create/Update.
`from_attributes=True` — allows building IncidentResponse from SQLAlchemy model.

## Repository Layer (modules/incidents/repository.py)

No business logic. Only database operations.

| Method | Description |
|---|---|
| create(data) | Insert incident, auto-generate incident_number |
| get_by_id(id) | Fetch by primary key |
| get_by_number(number) | Fetch by INC number |
| get_all(...) | Paginated, filtered, sorted list |
| update(id, data) | Partial update, auto-sets updated_at |
| delete(id) | Hard delete, returns bool |
| search(query, ...) | ilike search across 5 fields with optional filters |

To replace PostgreSQL with ServiceNow: create `ServiceNowIncidentRepository`
with the same method signatures and swap via dependency injection.

## Service Layer (modules/incidents/service.py)

Business logic only. No SQL queries.

| Method | Business Rules |
|---|---|
| create_incident | Calls repo.create, logs creation |
| get_incident | Raises NotFoundError if not found |
| list_incidents | Converts page to offset, calculates total pages |
| update_incident | Raises NotFoundError if not found, skips if no fields provided |
| delete_incident | Raises NotFoundError before deleting |
| search_incidents | Validates min 2 char query, raises BadRequestError |

## REST API Endpoints (api/v1/incidents.py)

Base path: `/v1/incidents`

| Method | Path | Description | Status |
|---|---|---|---|
| POST | /v1/incidents | Create incident | 201 |
| GET | /v1/incidents | List incidents | 200 |
| GET | /v1/incidents/search | Search incidents | 200 |
| GET | /v1/incidents/{id} | Get by ID | 200 |
| PUT | /v1/incidents/{id} | Update incident | 200 |
| DELETE | /v1/incidents/{id} | Delete incident | 204 |

> /search is declared before /{id} to prevent FastAPI matching "search" as a path parameter.

### GET /v1/incidents — Query Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| page | int | 1 | Page number |
| page_size | int | 20 | Results per page (max 100) |
| priority | str | null | Filter by priority |
| state | str | null | Filter by state |
| category | str | null | Filter by category |
| assignment_group | str | null | Filter by assignment group |
| sort_by | str | created_at | Sort field |
| sort_order | str | desc | asc or desc |

### GET /v1/incidents/search — Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| q | str | yes (min 2 chars) | Search keyword |
| page | int | no | Page number |
| page_size | int | no | Results per page |
| priority | str | no | Filter by priority |
| state | str | no | Filter by state |
| category | str | no | Filter by category |
| assignment_group | str | no | Filter by group |

Searches across: incident_number, short_description, description, caller, assigned_to.

### Error Responses

| Scenario | Status | Body |
|---|---|---|
| Incident not found | 404 | `{"detail": "...", "status_code": 404}` |
| Validation error | 422 | `{"detail": [...errors], "status_code": 422}` |
| Search query too short | 400 | `{"detail": "...", "status_code": 400}` |
| Unhandled error | 500 | `{"detail": "Internal server error", "status_code": 500}` |

## Seed Data (scripts/seed_incidents.py)

Inserts 100 realistic incidents into PostgreSQL.

Run from `backend/` with venv activated:
```bash
python scripts/seed_incidents.py
```

Covers categories: email, VPN, database, application, network, hardware, security, access, software.
Randomises: priority, state, impact, urgency, environment, source, assignment groups, callers, dates (0–90 days ago).

## Database Migration

Migration file: `alembic/versions/78b5282e58c6_create_incidents_table.py`

```bash
# Apply migration (creates incidents table)
alembic upgrade head
```

---

# Testing

## Test Infrastructure

- In-memory SQLite via `aiosqlite` — no PostgreSQL needed for tests
- `conftest.py` creates schema from models and overrides `get_db` dependency
- Tests are isolated per test function via fresh session

## Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest app/tests/unit/ -v

# API integration tests only
pytest app/tests/api/ -v

# With output
pytest -v -s
```

## Test Coverage

### Unit Tests (app/tests/unit/test_incident_service.py) — 9 tests

| Test | Covers |
|---|---|
| test_create_incident | Service creates and returns incident |
| test_get_incident_not_found | Raises NotFoundError |
| test_get_incident_found | Returns IncidentResponse |
| test_update_incident_not_found | Raises NotFoundError |
| test_update_incident_success | Updates and returns updated incident |
| test_delete_incident_not_found | Raises NotFoundError |
| test_delete_incident_success | Calls repo.delete |
| test_search_short_query | Raises BadRequestError for < 2 chars |
| test_list_incidents | Returns IncidentListResponse |

### API Integration Tests (app/tests/api/test_incidents_api.py) — 14 tests

| Test | Covers |
|---|---|
| test_create_incident | POST returns 201, incident_number set |
| test_create_incident_validation_error | short_description < 5 chars → 422 |
| test_create_incident_missing_required | Missing short_description → 422 |
| test_get_incident | GET by ID returns correct incident |
| test_get_incident_not_found | Unknown ID → 404 |
| test_list_incidents | GET returns items and total |
| test_list_incidents_pagination | page_size limits results |
| test_list_incidents_filter_by_state | state filter applied correctly |
| test_update_incident | PUT updates state |
| test_update_incident_not_found | Unknown ID → 404 |
| test_delete_incident | DELETE returns 204, GET returns 404 |
| test_delete_incident_not_found | Unknown ID → 404 |
| test_search_incidents | q matches short_description |
| test_search_incidents_short_query | q=1 char → 422 |

Total: 23 tests, all passing.

---

# Not Yet Implemented (Future Phases)

| Phase | Module | Description |
|---|---|---|
| 3 | Authentication | JWT, users, roles |
| 3 | Users module | User management |
| 4 | AI Platform | LLM integration |
| 4 | Agents — Triage | Auto-triage incidents |
| 4 | Agents — Acknowledgement | Auto-acknowledge |
| 4 | Agents — Pending | Handle pending state |
| 4 | Agents — Resolution | Auto-resolve |
| 4 | Orchestrator | Coordinate agents |
| 5 | ServiceNow Integration | Replace repository layer |
| 5 | Knowledge module | Knowledge base |
| 5 | Analytics module | Dashboards, metrics |
| 5 | Audit module | Audit trail |
| 6 | Platform — Events | Event bus |
| 6 | Platform — Messaging | Message queue |
| 6 | Platform — Caching | Redis cache |
| 6 | Platform — Scheduler | Job scheduler |
| 6 | Platform — Telemetry | Observability |
| 6 | Background Workers | Async job processing |

---

# Running URLs

| URL | Purpose |
|---|---|
| http://localhost:8000/v1/health | App health check |
| http://localhost:8000/v1/db-health | Database health check |
| http://localhost:8000/v1/incidents | Incident list |
| http://localhost:8000/v1/incidents/search?q=vpn | Search incidents |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/redoc | ReDoc |
