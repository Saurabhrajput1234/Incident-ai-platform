# Acknowledgement Agent — Documentation

---

## Overview

The Acknowledgement Agent (Agent 2) processes incidents after the Triage Agent assigns an engineer. Its job is to classify the incident intent and notify the caller with the appropriate acknowledgement template.

It distinguishes between standard incidents (which proceed normally) and misrouted requests (which are redirected to the correct channel and put on hold).

---

## Trigger

```
POST /v1/acknowledgement/{incident_id}
```

Can be triggered manually or chained after triage. Returns an `AgentResponse` with full classification details.

---

## Decision Flow

```
AcknowledgementService.process_acknowledgement(incident_id)
         ↓
Step 1: Fetch incident + build AIContext
         ↓
Step 2: AcknowledgementAgent.run(AIContext)
         ↓
    Is assignment_group a Salesforce group?
    ├── NO  → IntentType = STANDARD_INCIDENT (no LLM call)
    │         template = standard_ack.html
    │         confidence = 1.0
    └── YES → IntentClassifier.classify_intent() via LLM
              analyzes: short_description, description, assignment_group, category, subcategory
              returns IntentType + confidence + reasoning
         ↓
Step 3: Determine state change + work note
    STANDARD_INCIDENT          → state unchanged,  standard note
    WRONG_REQUEST              → state = on_hold,  wrong request note
    ACCESS_REQUEST             → state = on_hold,  access portal note
    SERVICE_REQUEST            → state = on_hold,  service catalog note
    SALESFORCE_INCORRECT_REQUEST → state = on_hold, IT Central RITM note
         ↓
Step 4: _append_work_note(existing, new_note)
    Prepends timestamped block to existing work_notes
    Never overwrites — full history preserved
         ↓
Step 5: IncidentService.update_incident(state, work_notes)
         ↓
Step 6: Return AcknowledgementResult
```

---

## Salesforce Group Detection

```python
# agent.py
SALESFORCE_GROUPS = ["salesforce", "sfdc", "hcl apps run-sfdc", "salesforce support"]

def is_salesforce_group(group_name: str | None) -> bool:
    if not group_name:
        return False
    clean_name = group_name.lower()
    return any(g in clean_name for g in SALESFORCE_GROUPS)
```

Any assignment group containing these keywords triggers the LLM classification path.

---

## Intent Types

| Intent | Description | State Change | Template |
|---|---|---|---|
| `STANDARD_INCIDENT` | Normal IT incident | None | standard_ack.html |
| `WRONG_REQUEST` | Wrong assignment group / wrong form | on_hold | wrong_org_environment.html |
| `ACCESS_REQUEST` | Access/permission request via incident | on_hold | wrong_ticket_access.html |
| `SERVICE_REQUEST` | Hardware/software order via incident | on_hold | wrong_ticket_service_catalog.html |
| `SALESFORCE_INCORRECT_REQUEST` | Salesforce RITM submitted as incident | on_hold | salesforce_incorrect_request.html |

---

## Work Note Format

Each run appends a timestamped block. Previous notes are preserved below a separator.

```
[2026-08-27 14:32:10 UTC]
Acknowledgement Agent executed successfully.
• Incident classified as Standard Incident.
• Ticket assigned to Priya Sharma (Apps Run-SAP - BASIS).
• User notified with assignment details.

────────────────────────────────────────

[2026-08-27 14:30:05 UTC]
[Triage Agent] Assigned to Priya Sharma (shift=Shift1, active_now=True, group=Apps Run-SAP - BASIS).
```

---

## Schemas

```python
# schemas.py

class IntentType(str, Enum):
    STANDARD_INCIDENT = "STANDARD_INCIDENT"
    ACCESS_REQUEST = "ACCESS_REQUEST"
    SERVICE_REQUEST = "SERVICE_REQUEST"
    WRONG_REQUEST = "WRONG_REQUEST"
    SALESFORCE_INCORRECT_REQUEST = "SALESFORCE_INCORRECT_REQUEST"

class IntentResult(BaseModel):
    intent: IntentType
    confidence: float      # 0.0 – 1.0
    reasoning: str         # LLM explanation

class AcknowledgementResult(BaseModel):
    incident_id: str
    incident_number: str
    caller: str | None
    assigned_to: str | None
    assignment_group: str | None
    intent_info: IntentResult
    template_used: str         # HTML template filename
    email_sent: bool           # True (simulated for now)
    delivery_status: str       # "simulated_success"
    work_notes_added: str      # Full updated work_notes string
    timestamp: datetime
```

---

## File Structure

```
modules/agents/acknowledgement/
├── agent.py              AcknowledgementAgent — Salesforce check, template selection
├── service.py            AcknowledgementService — orchestration, state update, work notes
├── intent_classifier.py  IntentClassifier — LLM-based classification for Salesforce group
├── schemas.py            IntentType, IntentResult, AcknowledgementResult, EmailDeliveryLog
├── kb_search_engine.py   Knowledge base search (future use)
├── templates/            Jinja2 HTML email templates
│   ├── standard_ack.html
│   ├── salesforce_incorrect_request.html
│   ├── wrong_org_environment.html
│   ├── wrong_ticket_access.html
│   └── wrong_ticket_service_catalog.html
└── dummy_data/
    └── ack_logs.json     Simulated delivery audit logs
```

---

## Audit Logs

```
GET /v1/acknowledgement/logs
```

Returns all entries from `ack_logs.json` (simulated delivery log). Each entry records:
- Incident number
- Caller name + email
- Intent classification
- Template used
- Delivery status + timestamp

---

## Dashboard Analytics

The Acknowledgement Agent tab on the dashboard shows:

- **Total processed** — incidents with "Acknowledgement Agent" in work_notes
- **On Hold count** — non-standard incidents moved to on_hold
- **Template breakdown** — bar chart of Standard / Wrong Request / Access Request / Service Request / Salesforce
- **Activity log table** — per incident: template badge (color coded), group, assigned to, state, timestamp

---

## Future Enhancements

- Real email delivery via SMTP or SendGrid
- Multi-language template support
- Per-caller delivery tracking in PostgreSQL (replace JSON file)
- Automatic trigger after triage completes (chain agents)
