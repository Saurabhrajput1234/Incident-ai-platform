# 🤖 Pending Agent — Simplified Workflow & Database Specification

## 1. Overview & Core Purpose

The **Pending Agent** automates the follow-up reminder cycle when an incident is placed in **Pending** (or `on_hold`) awaiting user action:

1. **Trigger**: Executes when an incident moves to **`Pending`** state.
2. **Reads Previous Work Note**: Inspects the latest work note added by the engineer or acknowledgement agent.
3. **LLM Analysis**: Analyzes whether user action/clarification is needed.
4. **Sends Reminders (3 Times Max)**: Sends up to 3 reminders before the cycle ends.
5. **Work Note Update**: Appends a work note containing the reminder status + the **full email sent to the user**.
6. **State Reset to Pending**: Counteracts ServiceNow's auto-activation rule by immediately resetting the ticket state back to **`Pending`**.

---

## 2. Step-by-Step Flow

```text
[Incident Transitions to PENDING]
                │
                ▼
1. Check Active Cycle
   ├── If active cycle already exists in DB ➔ PRESERVE cycle (skip duplicate creation).
   └── If NO active cycle exists ➔ PROCEED to Step 2.
                │
                ▼
2. Read Previous Work Note
   └── Fetch latest entry from `incident_work_notes` (message, source_name, created_at).
                │
                ▼
3. LLM Work Note Analysis
   └── Groq LLM evaluates: "Is user action/clarification required?"
       ├── NO (internal note)  ➔ Discard & stop (no cycle created).
       └── YES (user response needed) ➔ Create new pending cycle & proceed.
                │
                ▼
4. Send Reminder Email (Reminder #1)
   └── Generate email based on the work note analysis using standard template.
   └── Simulated delivery (`email_sent = True`, `delivery_status = "simulated_success"`).
                │
                ▼
5. Update Work Note with Full Email
   └── Append new entry in `incident_work_notes`:
       • source_name: "PENDING AGENT"
       • message: Contains status (Reminder 1/3) + FULL email content sent to user.
                │
                ▼
6. State Reset: ACTIVE ➔ PENDING
   └── Work note insertion causes ServiceNow to auto-move ticket to ACTIVE.
   └── Pending Agent immediately forces state back to PENDING.
                │
                ▼
7. Loop via Scheduler (Up to 3 Times)
   ├── Reminder #2 (+24 hours later): Send reminder, log work note with full email, reset to PENDING.
   ├── Reminder #3 (+48 hours later): Send final reminder, log work note with full email, reset to PENDING.
   └── After Reminder #3 (+72 hours): Mark cycle COMPLETED (No more reminders sent).
```

---

## 3. Database Specification

We use the **same existing PostgreSQL database** (`incident_ai`). We do **NOT** create a separate database.

Only **ONE new table** is formed: **`pending_cycles`**.

### Table Name: `pending_cycles`

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | PRIMARY KEY | Unique cycle ID (e.g. `PC-001` or UUID) |
| `incident_id` | `VARCHAR(36)` | FOREIGN KEY (`incidents.id`) | Links directly to the incident record |
| `incident_number` | `VARCHAR(20)` | NOT NULL | e.g. `INC0000064` |
| `status` | `VARCHAR(20)` | NOT NULL, DEFAULT `'ACTIVE'` | Cycle status: `ACTIVE`, `COMPLETED`, `CANCELLED` |
| `reminder_count` | `INTEGER` | NOT NULL, DEFAULT `0` | Current reminder count (`1`, `2`, or `3`) |
| `max_reminders` | `INTEGER` | NOT NULL, DEFAULT `3` | Maximum reminders allowed (fixed at `3`) |
| `source_type` | `VARCHAR(50)` | NOT NULL | Initiator: `ENGINEER` or `ACKNOWLEDGEMENT_AGENT` |
| `next_reminder_at` | `TIMESTAMP WITH TIME ZONE` | NULLABLE | Next scheduled reminder execution time (`NOW() + 24h`) |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL, DEFAULT `NOW()` | Timestamp when cycle was started |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL, DEFAULT `NOW()` | Timestamp when cycle/reminder was last updated |

---

## 4. What Gets Updated in the Work Note

Following the same standard established by the Acknowledgement Agent, the work note logged by the Pending Agent will record:

```text
Pending Agent: Reminder 1 of 3 sent to user.
• Awaiting: Error screenshot / clarification requested by engineer.
• Next Follow-up: 09/09/2026, 08:30 UTC
• State: Maintained in Pending

==================== EMAIL SENT TO USER ====================
Subject: Follow-up Reminder (1/3) - INC0000064

Hello Tina,

This is a follow-up reminder regarding your incident INC0000064: "Unable to access Salesforce due to SAML authentication error".

Our engineer, Aman Mourya, is awaiting additional details from you to proceed with resolving your ticket:
- Please provide the screenshot of the error message when opening GTS EANZ.

Please reply to this email or update your ticket in the portal so we can assist you promptly.

View Ticket: https://servicenow.corp.internal/nav_to.do?uri=incident.do?sys_id=INC0000064

Regards,
IT Support Team
============================================================
```

---

## 5. ServiceNow State Bounce Behavior

* **The Problem**: In ServiceNow, inserting *any* work note automatically transitions the incident from **`Pending ➔ Active`**.
* **The Solution**: 
  1. Pending Agent adds the reminder work note (`source_name = "PENDING AGENT"`).
  2. ServiceNow auto-switches state to `Active`.
  3. Pending Agent immediately resets the state back to **`Pending`**.
  4. The cycle check ensures that when the state becomes `Pending`, it recognizes the existing active cycle `PC-001` and does not spawn a new cycle.
