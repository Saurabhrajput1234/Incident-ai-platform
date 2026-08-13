# Incident AI Platform — Database Documentation

---

## Overview

- Database: **PostgreSQL**
- ORM: **SQLAlchemy 2.0** (async)
- Migrations: **Alembic**
- All primary keys: **UUID (String 36)**
- All timestamps: **DateTime with timezone (UTC)**
- Shift roster enum columns: **plain String** (no PostgreSQL native enum types)
- Incident enum columns: **PostgreSQL native enum** (via SQLAlchemy SAEnum)

---

## Connection

```
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/incident_ai
```

---

## Migration History

| Version | File | What it creates |
|---|---|---|
| 78b5282e58c6 | create_incidents_table | incidents |
| 15fef2bf1df7 | create_shift_roster_table | (superseded) |
| 9092bd4e4a4f | normalized_shift_roster_schema | engineers, shift_roster_uploads, shift_roster, shift_roster_history |
| e67628208ea8 | add_assignment_rr_state_and_history | assignment_group_rr_state, assignment_history |
| 2dab1e1fa831 | fix_enum_values_lowercase | enum value fixes |
| 76deb7e985b5 | shift_roster_string_columns | converts shift roster enum columns to String |

Run all migrations:
```bash
alembic upgrade head
```

Rollback one step:
```bash
alembic downgrade -1
```

---

## Table Overview

```
incidents                    — IT incident records
engineers                    — engineer master records
shift_roster_uploads         — uploaded Excel/CSV file metadata
shift_roster                 — daily roster (one row per engineer per day)
shift_roster_history         — audit trail for roster changes
assignment_group_rr_state    — round-robin position per assignment group
assignment_history           — every engineer assignment ever made
```

---

## Table: incidents

**Purpose:** Stores all IT incident records. Central table of the platform.

**Model file:** `app/modules/incidents/model.py`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | VARCHAR(36) PK | No | UUID | Primary key |
| incident_number | VARCHAR(20) | No | — | INC0000001, unique, indexed |
| short_description | VARCHAR(255) | No | — | Required |
| description | TEXT | Yes | NULL | |
| priority | ENUM | No | 3 (Medium) | 1=Critical, 2=High, 3=Medium, 4=Low |
| state | ENUM | No | new | new, in_progress, on_hold, resolved, closed, cancelled |
| category | ENUM | Yes | NULL | network, hardware, software, database, security, access, email, vpn, application, other |
| subcategory | VARCHAR(100) | Yes | NULL | |
| impact | ENUM | No | 2 (Medium) | 1=High, 2=Medium, 3=Low |
| urgency | ENUM | No | 2 (Medium) | 1=High, 2=Medium, 3=Low |
| assignment_group | VARCHAR(100) | Yes | NULL | Set by Triage Agent |
| assigned_to | VARCHAR(100) | Yes | NULL | Set by Triage Agent |
| caller | VARCHAR(100) | Yes | NULL | Reporter name |
| configuration_item | VARCHAR(100) | Yes | NULL | CMDB CI reference |
| business_service | VARCHAR(100) | Yes | NULL | CMDB service reference |
| environment | ENUM | Yes | NULL | production, staging, development, dr |
| source | ENUM | No | manual | manual, monitoring, email, phone, self_service, api |
| work_notes | TEXT | Yes | NULL | Internal notes, updated by Triage Agent |
| comments | TEXT | Yes | NULL | |
| created_at | TIMESTAMPTZ | No | now() | |
| updated_at | TIMESTAMPTZ | No | now() | auto-updated on change |

**Indexes:**
- `ix_incidents_incident_number` (unique)

**Enum values stored in PostgreSQL:**

| Column | Enum Name | Values |
|---|---|---|
| priority | incidentpriority | 1, 2, 3, 4 |
| state | incidentstate | new, in_progress, on_hold, resolved, closed, cancelled |
| category | incidentcategory | network, hardware, software, database, security, access, email, vpn, application, other |
| impact | incidentimpact | 1, 2, 3 |
| urgency | incidenturgency | 1, 2, 3 |
| environment | incidentenvironment | production, staging, development, dr |
| source | incidentsource | manual, monitoring, email, phone, self_service, api |

**Lifecycle states:**
```
new → in_progress → resolved → closed
         ↓               ↑
      on_hold      (can return)
         ↓
     cancelled
```

---

## Table: engineers

**Purpose:** Master engineer records. Deduplicated by email. Upserted on every Excel upload.

**Model file:** `app/modules/shift_roster/model.py`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | VARCHAR(36) PK | No | UUID | |
| assignment_group | VARCHAR(200) | No | — | Indexed e.g. "Windows Support" |
| assigned_to | VARCHAR(100) | No | — | Engineer's full name, indexed |
| email | VARCHAR(150) | No | — | Unique, indexed — deduplication key |
| default_shift | VARCHAR(20) | Yes | NULL | From Excel "Shift" column |
| level | VARCHAR(10) | Yes | NULL | L1, L2, or L3, indexed |
| status | VARCHAR(20) | No | active | active or inactive, indexed |
| created_at | TIMESTAMPTZ | No | now() | |
| updated_at | TIMESTAMPTZ | No | now() | auto-updated |

**Indexes:**
- `ix_engineers_assignment_group`
- `ix_engineers_assigned_to`
- `ix_engineers_email` (unique)
- `ix_engineers_level`
- `ix_engineers_status`

**Upsert logic:**
- On upload: if engineer with same email exists → update their record
- If new email → insert new record
- Marking an engineer inactive does NOT delete historical roster data

---

## Table: shift_roster_uploads

**Purpose:** Metadata for every Excel/CSV file uploaded. One row per upload.

**Model file:** `app/modules/shift_roster/model.py`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | VARCHAR(36) PK | No | UUID | |
| file_name | VARCHAR(255) | No | — | Original filename |
| roster_start_date | DATE | No | — | From Excel header e.g. 2026-08-01 |
| roster_end_date | DATE | No | — | From Excel header e.g. 2026-08-30 |
| uploaded_by | VARCHAR(100) | Yes | NULL | Optional — provided as query param |
| uploaded_at | TIMESTAMPTZ | No | now() | |
| total_records | INTEGER | No | 0 | Engineer rows in file |
| imported_records | INTEGER | No | 0 | Successfully saved |
| failed_records | INTEGER | No | 0 | Skipped due to errors |
| upload_status | VARCHAR(20) | No | success | success, partial, or failed |

---

## Table: shift_roster

**Purpose:** One row per engineer per day. Normalized from Excel Day1..Day31 columns.
Primary query table for the Triage Agent availability check.

**Model file:** `app/modules/shift_roster/model.py`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | VARCHAR(36) PK | No | UUID | |
| upload_id | VARCHAR(36) FK | No | — | → shift_roster_uploads.id, indexed |
| engineer_id | VARCHAR(36) FK | No | — | → engineers.id, indexed |
| roster_date | DATE | No | — | The specific date, indexed |
| shift_code | VARCHAR(20) | No | — | Shift1, Shift2, Shift3, WO, PL, CH, RH, indexed |
| created_at | TIMESTAMPTZ | No | now() | |
| updated_at | TIMESTAMPTZ | No | now() | auto-updated |

**Indexes:**
- `ix_shift_roster_upload_id`
- `ix_shift_roster_engineer_id`
- `ix_shift_roster_roster_date`
- `ix_shift_roster_shift_code`

**Shift code values:**

| Code | Meaning | Working shift |
|---|---|---|
| Shift1 | 12:30 PM – 09:30 PM IST | Yes |
| Shift2 | 10:00 AM – 07:30 PM IST | Yes |
| Shift3 | 08:00 AM – 05:00 PM EST | Yes |
| WO | Week Off | No |
| PL | Planned Leave | No |
| CH | Company Holiday | No |
| RH | Restricted Holiday | No |

**Example query — get all engineers on Shift2 today:**
```sql
SELECT e.assigned_to, e.email, e.level, sr.shift_code
FROM shift_roster sr
JOIN engineers e ON sr.engineer_id = e.id
WHERE sr.roster_date = CURRENT_DATE
  AND sr.shift_code = 'Shift2'
  AND e.status = 'active';
```

---

## Table: shift_roster_history

**Purpose:** Audit trail for any manual changes to shift_roster entries after upload.
One row per change.

**Model file:** `app/modules/shift_roster/model.py`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | VARCHAR(36) PK | No | UUID | |
| roster_id | VARCHAR(36) FK | No | — | → shift_roster.id, indexed |
| engineer_id | VARCHAR(36) FK | No | — | → engineers.id, indexed |
| roster_date | DATE | No | — | The date that was changed |
| previous_shift | VARCHAR(20) | No | — | Shift code before change |
| new_shift | VARCHAR(20) | No | — | Shift code after change |
| changed_by | VARCHAR(100) | Yes | NULL | Who made the change |
| changed_at | TIMESTAMPTZ | No | now() | |
| reason | TEXT | Yes | NULL | Optional reason for change |

**Indexes:**
- `ix_shift_roster_history_roster_id`
- `ix_shift_roster_history_engineer_id`

---

## Table: assignment_group_rr_state

**Purpose:** Persists the round-robin index per assignment group for the Triage Agent.
Survives server restarts. One row per assignment group.

**Model file:** `app/modules/agents/triage/models.py`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| assignment_group | VARCHAR(200) PK | No | — | e.g. "Windows Support" |
| last_index | INTEGER | No | 0 | Last engineer index used in round-robin |
| updated_at | TIMESTAMPTZ | No | now() | auto-updated on every assignment |

**How it's used:**
```sql
-- Read with row lock (prevents concurrent duplicate assignments)
SELECT * FROM assignment_group_rr_state
WHERE assignment_group = 'Windows Support'
FOR UPDATE;

-- After assignment, save new index
UPDATE assignment_group_rr_state
SET last_index = 3, updated_at = now()
WHERE assignment_group = 'Windows Support';
```

**Reset round-robin for a group:**
```sql
UPDATE assignment_group_rr_state SET last_index = 0
WHERE assignment_group = 'Windows Support';
```

---

## Table: assignment_history

**Purpose:** Full audit trail of every engineer assignment made by the Triage Agent.
One row per incident assignment.

**Model file:** `app/modules/agents/triage/models.py`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| id | VARCHAR(36) PK | No | UUID | |
| incident_id | VARCHAR(36) | No | — | Incident UUID, indexed |
| incident_number | VARCHAR(20) | No | — | e.g. INC0000001 |
| assignment_group | VARCHAR(200) | No | — | Group assigned to, indexed |
| engineer_id | VARCHAR(36) | No | — | Engineer UUID, indexed |
| engineer_name | VARCHAR(100) | No | — | Engineer full name |
| engineer_email | VARCHAR(150) | No | — | Engineer email |
| shift_code | VARCHAR(20) | Yes | NULL | Their shift at time of assignment |
| roster_date | VARCHAR(10) | Yes | NULL | Date of assignment (YYYY-MM-DD) |
| assigned_at | TIMESTAMPTZ | No | now() | Exact time of assignment |
| llm_resolved_group | BOOLEAN | No | false | True if Groq LLM determined the group |
| notes | TEXT | Yes | NULL | Round-robin index, fallback info |

**Indexes:**
- `ix_assignment_history_incident_id`
- `ix_assignment_history_assignment_group`
- `ix_assignment_history_engineer_id`

**Query recent assignments:**
```sql
SELECT incident_number, engineer_name, assignment_group,
       shift_code, assigned_at, llm_resolved_group, notes
FROM assignment_history
ORDER BY assigned_at DESC
LIMIT 20;
```

---

## Relationships Diagram

```
shift_roster_uploads
        │ 1
        │
        ▼ N
   shift_roster ◄────────────── engineers
        │                           │
        │ 1                         │ 1
        │                           │
        ▼ N                         ▼ N
shift_roster_history        assignment_history

assignment_group_rr_state   (standalone — one row per group)
```

---

## Quick Reference Queries

**Count incidents by state:**
```sql
SELECT state, COUNT(*) FROM incidents GROUP BY state ORDER BY 2 DESC;
```

**Find unassigned new incidents:**
```sql
SELECT incident_number, short_description, priority, created_at
FROM incidents
WHERE state = 'new' AND assigned_to IS NULL
ORDER BY priority, created_at;
```

**Today's engineer availability:**
```sql
SELECT e.assigned_to, e.assignment_group, e.level, sr.shift_code
FROM shift_roster sr
JOIN engineers e ON sr.engineer_id = e.id
WHERE sr.roster_date = CURRENT_DATE
  AND e.status = 'active'
ORDER BY e.assignment_group, sr.shift_code;
```

**Engineers on leave today:**
```sql
SELECT e.assigned_to, e.assignment_group, sr.shift_code
FROM shift_roster sr
JOIN engineers e ON sr.engineer_id = e.id
WHERE sr.roster_date = CURRENT_DATE
  AND sr.shift_code IN ('WO', 'PL', 'CH', 'RH');
```

**Assignment history for an incident:**
```sql
SELECT engineer_name, shift_code, assigned_at, llm_resolved_group, notes
FROM assignment_history
WHERE incident_number = 'INC0000001';
```

**Upload history:**
```sql
SELECT file_name, roster_start_date, roster_end_date,
       imported_records, failed_records, upload_status, uploaded_at
FROM shift_roster_uploads
ORDER BY uploaded_at DESC;
```

---

## Database Commands

```bash
# Apply all pending migrations
alembic upgrade head

# Generate new migration after model changes
alembic revision --autogenerate -m "description"

# View migration history
alembic history

# Rollback one migration
alembic downgrade -1

# Check current migration version
alembic current
```

**Clear all data (development only):**
```sql
TRUNCATE incidents RESTART IDENTITY CASCADE;
TRUNCATE shift_roster, shift_roster_history, engineers, shift_roster_uploads RESTART IDENTITY CASCADE;
TRUNCATE assignment_history, assignment_group_rr_state RESTART IDENTITY CASCADE;
```
