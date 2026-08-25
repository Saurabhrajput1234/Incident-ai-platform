# 📘 Acknowledgement Agent — Complete Final Workflow & Architectural Specification

## Executive Overview

The **Acknowledgement Agent** is the second autonomous agent in the **ServiceNow Incident AI Platform**. It triggers automatically after an incident is triaged and assigned (`state = in_progress`).

Its primary responsibility is to:
1. Ingest incident metadata and context from PostgreSQL.
2. Evaluate ticket intent using a **Hybrid Classifier** (Fast Keyword Regex Engine `<1ms` + Groq LLM Fallback) into **6 distinct branches**:
   - `SALESFORCE_INCORRECT_REQUEST` (Targeted for `HCL Apps Run-SFDC` assignment group)
   - `STANDARD_INCIDENT`
   - `INFORMATION_REQUEST`
   - `ACCESS_REQUEST`
   - `SERVICE_REQUEST`
   - `WRONG_REQUEST`
3. Render brand-compliant **Jinja2 HTML Email Templates** for each branch, including corporate template [salesforce_incorrect_request.html](file:///Users/jalajbalodi/PROJECT/backend/app/modules/agents/acknowledgement/templates/salesforce_incorrect_request.html).
4. Deliver notifications (SMTP / Simulated logger) and log audit events.
5. Update non-standard ticket statuses to **Pending** (`on_hold` in DB) and format PostgreSQL `work_notes` into structured bullet points.

---

## 📑 Salesforce Incorrect Request Flow (`HCL Apps Run-SFDC`)

When a ticket is assigned to `HCL Apps Run-SFDC` (or Salesforce assignment groups) and is classified as an access / profile update / permission request:

- **Template Rendered**: `salesforce_incorrect_request.html`
- **Email Subject**: `[Salesforce Request Notice] INC... - Application Access Request Required`
- **Portal Link**: `https://sbdkproduction.service-now.com/esc`
- **Support Contact**: `aman.mourya@sbdinc.com`
- **Work Notes Added**:
  ```text
  Acknowledgement Agent executed successfully.
  • Incident classified as Salesforce Access / Update Request.
  • Request submitted under incorrect form for Salesforce.com GTS (EANZ) & GEM.
  • User notified to submit 'Application Access Request' RITM via IT Central.
  • Incident status updated to Pending.
  ```

---

## 📂 Code Module Architecture

- **[salesforce_incorrect_request.html](file:///Users/jalajbalodi/PROJECT/backend/app/modules/agents/acknowledgement/templates/salesforce_incorrect_request.html)**: Corporate HTML template matching exact wording and 5 steps provided for SBD IT Support Team / HCL Apps Run-SFDC.
- **[schemas.py](file:///Users/jalajbalodi/PROJECT/backend/app/modules/agents/acknowledgement/schemas.py)**: Defines `IntentType` enum (`SALESFORCE_INCORRECT_REQUEST`, `STANDARD_INCIDENT`, `INFORMATION_REQUEST`, `ACCESS_REQUEST`, `SERVICE_REQUEST`, `WRONG_REQUEST`).
- **[intent_classifier.py](file:///Users/jalajbalodi/PROJECT/backend/app/modules/agents/acknowledgement/intent_classifier.py)**: Fast Regex Rule Engine (`<1ms`) + Groq LLM (`qwen/qwen3.6-27b`) Fallback.
- **[agent.py](file:///Users/jalajbalodi/PROJECT/backend/app/modules/agents/acknowledgement/agent.py)**: Evaluates intent and maps templates.
- **[email_delivery.py](file:///Users/jalajbalodi/PROJECT/backend/app/modules/agents/acknowledgement/email_delivery.py)**: Renders Jinja2 HTML templates, delivers emails, and logs audit events to `ack_logs.json`.
- **[service.py](file:///Users/jalajbalodi/PROJECT/backend/app/modules/agents/acknowledgement/service.py)**: Master orchestrator updating PostgreSQL state to `pending` (`on_hold`) and formatting structured bulleted work notes.
