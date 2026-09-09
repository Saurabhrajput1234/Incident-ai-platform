# ⏳ Pending Agent & Resolution Alert Agent — Flow, Edge Cases & Best Implementation

---

## 📌 Foundation: How ServiceNow Actually Works

Before understanding the Pending Agent, we need to understand ServiceNow's automatic behavior because it directly affects every agent decision.

### Work Note Structure

Every work note entry has 4 fields:

| Field | Example | Purpose |
| :--- | :--- | :--- |
| **source_name** | `"Ravi Kumar"` / `"Ack Agent"` / `"Pending Agent"` | Who added this note |
| **message** | `"Please provide screenshots of the error"` | The actual content |
| **timestamp** | `2026-09-03T10:05:00Z` | When it was created |
| **incident_id** | `INC0000043` | Which ticket this belongs to |

### ServiceNow's Golden Rule

> **Any update to a ticket (work note added, comment added, field changed) → ServiceNow automatically moves the ticket state to Active.**

This is not optional. This is how SN works. Every agent we build must account for this behavior.

---

## 🔄 State Transition Map — Who Triggers What

### Active → Pending (3 possible sources)

| Who Changes It | When | What Happens Next |
| :--- | :--- | :--- |
| **Engineer** (manually) | Engineer investigated, needs info from user, clicks "Pending" | **Pending Agent triggers** |
| **Acknowledgement Agent** | Ack Agent classified ticket as wrong request / access request, sets to pending | **Pending Agent triggers** |
| **Pending Agent** (itself) | After adding a reminder work note, SN auto-activates the ticket, so Pending Agent pushes it back to pending | **Pending Agent recognizes its own action and does NOT retrigger** |

### Pending → Active (5 possible sources)

| Who Changes It | When | What Happens Next |
| :--- | :--- | :--- |
| **User replies** (comment/worknote) | User provides the info engineer asked for | **Resolution Alert Agent triggers** |
| **Pending Agent** (adds worknote) | Reminder worknote added → SN auto-activates | **Pending Agent pushes it back to pending (part of the loop)** |
| **Engineer** (manually) | Engineer decides to work on it without waiting for user | **Resolution Alert Agent triggers** |
| **Any person** updates worknote | Someone else adds a note | **Resolution Alert Agent triggers** |
| **Manual button click** | Someone manually clicks "Active" | **Resolution Alert Agent triggers** |

---

## 🟢 Pending Agent — Complete Flow (Step by Step)

### Trigger

Ticket state changes from **Active → Pending**.

### Step 1: Check Who Made the Ticket Pending (Source Identification)

The Pending Agent reads the **latest work note** and checks the `source_name` field.

**Three possible outcomes:**

| Latest Work Note Source | What It Means | Agent Decision |
| :--- | :--- | :--- |
| **source_name = Engineer** (e.g. "Ravi Kumar") | Engineer manually set ticket to pending after adding a note | ✅ Go to **Step 2A** — Analyze the work note via LLM |
| **source_name = Ack Agent** | Acknowledgement Agent classified this as wrong request and set to pending | ✅ Go to **Step 2B** — Skip analysis, direct email generation |
| **source_name = Pending Agent** | Pending Agent itself pushed ticket back to pending (part of reminder loop) | 🛑 **DISCARD** — Do nothing. This is the agent's own action cycling back. |

### Step 2A: Engineer Work Note → LLM Analysis

When an engineer sets a ticket to pending, the Pending Agent sends the latest work note to the LLM with the prompt:

> "Here is the latest work note from an engineer who set this ticket to Pending. Did the engineer ask the caller (end user) a question or request specific information? If yes, extract what they asked. If the engineer just wrote an internal note like 'Waiting for vendor patch' or 'Escalating to L3', this is NOT a question for the user."

**LLM decides one of two outcomes:**

- **"Yes, engineer asked the user something"** → Extract the question → Go to Step 3 (create pending cycle + generate reminder email)
- **"No, this is an internal note"** → **DISCARD**. No reminder cycle needed. The engineer set it to pending for internal reasons.

### Step 2B: Ack Agent Source → Direct Email Generation

When the Acknowledgement Agent is the source, we already know the classification (wrong request / access request / service request). No analysis needed.

- Directly generate the reminder email template based on the Ack Agent's original classification
- Go to Step 3

### Step 3: Create Pending Cycle & Send First Reminder

A **Pending Cycle** is created in PostgreSQL. This is the central tracking record for the entire reminder loop.

**Pending Cycle record contains:**

| Field | Value | Purpose |
| :--- | :--- | :--- |
| cycle_id | `PC-001` | Unique identifier |
| incident_id | `INC0000043` | Which ticket |
| status | `ACTIVE` | Lifecycle: ACTIVE / COMPLETED / CANCELLED |
| reminder_count | `0` | Starts at 0, increments with each email sent |
| max_reminders | `3` | Hard cap |
| engineer_query | `"Please provide screenshots of the error"` | What the engineer asked (from LLM) |
| source_type | `ENGINEER` or `ACK_AGENT` | Who triggered this cycle |
| next_reminder_at | `NOW + 24 hours` | When the next reminder should fire |
| created_at | `2026-09-03T10:05:00Z` | When cycle started |

**Then:**
1. Generate personalized reminder email via LLM (or use Ack Agent template directly)
2. Send Reminder #1 to the user
3. Add a work note: `"Pending Agent: Reminder 1/3 sent to user. Question: [engineer's question]"` (source_name = "Pending Agent")
4. Set `reminder_count = 1`, `next_reminder_at = NOW + 24h`

### Step 4: The Automatic State Bounce (SN Behavior)

After Step 3, this happens automatically:

```
Pending Agent adds work note
    ↓
ServiceNow detects ticket was updated
    ↓
SN automatically changes state: Pending → Active
    ↓
Pending Agent sees "Active → Pending" is needed
    ↓
Pending Agent pushes state back to Pending
    ↓
(source_name on this action = "Pending Agent")
```

**This is expected behavior.** The next time Pending Agent triggers (because state went Active → Pending), it checks Step 1 and sees `source_name = "Pending Agent"` → **DISCARD**. The loop does not retrigger.

### Step 5: 24-Hour Wait & Reminder Loop

A background scheduler (cron job) polls PostgreSQL every 5 minutes looking for pending cycles where `next_reminder_at <= NOW()` and `status = ACTIVE`.

**When the 24-hour timer fires:**

1. Check: Is the cycle still ACTIVE? (Maybe it was already cancelled by the Resolution Alert Agent)
2. Check: Is `reminder_count < 3`?
3. If both YES:
   - Increment `reminder_count`
   - Generate Reminder N/3 email via LLM
   - Send email
   - Add work note (source_name = "Pending Agent")
   - SN auto-activates the ticket → Pending Agent pushes back to pending (same bounce as Step 4)
   - Set `next_reminder_at = NOW + 24h`
4. If `reminder_count == 3`:
   - Set cycle `status = COMPLETED`
   - Add final work note: `"Pending Agent: Maximum reminders (3/3) reached. No response from caller. Cycle completed."`
   - **Stop.** No more emails.

### Pending Agent Flow — Summary Diagram

```
Active → Pending (trigger)
    │
    ▼
Check latest work note source_name
    │
    ├── source = "Pending Agent" ──→ 🛑 DISCARD (own action)
    │
    ├── source = "Ack Agent" ──→ Direct email generation (skip analysis)
    │                               │
    │                               ▼
    │                         Create Pending Cycle
    │                               │
    ├── source = "Engineer" ──→ LLM analyzes work note
    │                               │
    │                         ┌─────┴─────┐
    │                         │            │
    │                    Caller action   Internal note
    │                    required        (no question)
    │                         │            │
    │                         ▼            ▼
    │                   Create Pending   🛑 DISCARD
    │                   Cycle
    │                         │
    └─────────────────────────┤
                              ▼
                    Send Reminder 1/3
                              │
                              ▼
                    Add work note (source = "Pending Agent")
                              │
                              ▼
                    SN auto-activates ticket
                              │
                              ▼
                    Pending Agent pushes back to Pending
                              │
                              ▼
                    Wait 24 hours (DB scheduler)
                              │
                              ▼
                    ┌─────────┴──────────┐
                    │                    │
              Cycle still active?   Cycle cancelled?
              reminder_count < 3?   (by Resolution Alert Agent)
                    │                    │
                    ▼                    ▼
              Send Reminder N/3     🛑 STOP (cycle broken)
              Loop back to wait
                    │
                    ▼
              reminder_count == 3?
                    │
                    ▼
              🛑 CYCLE COMPLETED (max reminders)
```

---

## 🔵 Resolution Alert Agent — The Cycle Breaker (4th Agent)

### Trigger

Ticket state changes from **Pending → Active**.

### Why This Agent Exists

When a ticket goes from Pending to Active, *something happened*. The Resolution Alert Agent figures out *what* happened and takes the right action.

### Step 1: Analyze Who/What Made the Ticket Active

Read the latest work note and check `source_name`:

| Source | Meaning | Action |
| :--- | :--- | :--- |
| **User** (caller name) | User replied with the information engineer asked for | ✅ Go to Step 2 |
| **Pending Agent** | Pending Agent added a reminder work note → SN auto-activated | 🛑 **DISCARD** — Pending Agent will push it back to pending. Not a real activation. |
| **Engineer** | Engineer manually reactivated the ticket | ✅ Go to Step 3 |
| **Any other person** | Someone else updated the ticket | ✅ Go to Step 3 |

### Step 2: User Replied — Check Pending Cycle & Break It

1. Query PostgreSQL: Does this incident have an **ACTIVE** pending cycle?
2. **If YES** (pending cycle exists):
   - Set cycle `status = CANCELLED`, `cancellation_reason = "user_replied"`
   - The reminder loop is now broken. No more emails will be sent.
   - Add work note: `"Resolution Alert Agent: User replied. Pending reminder cycle cancelled."`
   - **Ping the engineer**: Notify the assigned engineer that the user has responded and the ticket is back to Active.
   - (Future: Could analyze the user's reply to check if it actually answers the engineer's question)
3. **If NO** (no pending cycle):
   - This ticket went Pending → Active without a reminder cycle (maybe engineer manually set it to pending and user replied quickly before any cycle was created)
   - Still ping the engineer about the state change

### Step 3: Engineer or Other Person Reactivated — Check Pending Cycle

1. Query PostgreSQL: Does this incident have an **ACTIVE** pending cycle?
2. **If YES**:
   - Set cycle `status = CANCELLED`, `cancellation_reason = "engineer_reactivated"` or `"manual_reactivation"`
   - The reminder loop is broken.
   - Add work note: `"Resolution Alert Agent: Ticket manually reactivated. Pending reminder cycle cancelled."`
3. **If NO**:
   - Normal state change, log it and move on.

### Resolution Alert Agent Flow — Summary

```
Pending → Active (trigger)
    │
    ▼
Check latest work note source_name
    │
    ├── source = "Pending Agent" ──→ 🛑 DISCARD
    │                                 (auto-activation from reminder, not real)
    │
    ├── source = User ──→ Check pending_cycles table
    │                         │
    │                    ┌────┴────┐
    │                    │         │
    │               Cycle exists  No cycle
    │                    │         │
    │                    ▼         ▼
    │              BREAK CYCLE   Log & continue
    │              Cancel reminders
    │              Ping engineer
    │                    
    └── source = Engineer / Other ──→ Check pending_cycles table
                                          │
                                     ┌────┴────┐
                                     │         │
                                Cycle exists  No cycle
                                     │         │
                                     ▼         ▼
                               BREAK CYCLE   Log & continue
                               Cancel reminders
```

---

## 🔗 How Both Agents Work Together — Complete Chain Example

**Scenario**: Engineer Ravi sets INC0000043 to Pending after asking "Please provide error screenshots"

```
TIME        EVENT                                          AGENT ACTION
─────────── ────────────────────────────────────────────── ────────────────────────────
Day 0       Engineer Ravi adds work note:                  
10:00 AM    "Please provide error screenshots"             
            Sets ticket: Active → Pending                  

Day 0       State change detected: Active → Pending        PENDING AGENT triggers
10:00 AM    Check source_name = "Ravi Kumar" (Engineer)    
            LLM analyzes: "Yes, engineer asked for         
            screenshots" → is_caller_action_required=True  
            Create Pending Cycle PC-001                    
            Send Reminder 1/3 email to user                
            Add work note (source = "Pending Agent")       
            SN auto-activates ticket                       

Day 0       State change: Pending → Active                 RESOLUTION ALERT AGENT triggers
10:01 AM    Check source_name = "Pending Agent"            DISCARD (not a real activation)

Day 0       Pending Agent pushes ticket back to Pending    
10:01 AM    State change: Active → Pending                 PENDING AGENT triggers
            Check source_name = "Pending Agent"            DISCARD (own action)

Day 1       24hr timer fires                               PENDING AGENT scheduler
10:00 AM    Cycle PC-001 still ACTIVE, reminder_count=1    
            Send Reminder 2/3 email                        
            Add work note (source = "Pending Agent")       
            SN auto-activates → agent pushes back          
            (same bounce cycle, both agents discard)       

Day 1       USER REPLIES: "Here are the screenshots"       
3:00 PM     User adds comment → SN auto-activates          
            State: Pending → Active                        

Day 1       State change: Pending → Active                 RESOLUTION ALERT AGENT triggers
3:00 PM     Check source_name = "Tina (User)"             
            Query pending_cycles: PC-001 exists (ACTIVE)   
            → BREAK CYCLE: status = CANCELLED              
            → reason = "user_replied"                      
            → Ping engineer Ravi: "User responded!"        
            → No more reminder emails will be sent         
```

---

## ⚠️ Edge Cases & How to Handle Them

### Edge Case 1: Engineer Sets Pending But Writes an Internal Note

**Situation**: Engineer changes ticket to Pending and writes "Escalating to L3 team, waiting for their feedback" — this is NOT a question for the user.

**How we handle it**: The LLM in Step 2A analyzes the work note and determines `is_caller_action_required = False`. The Pending Agent **discards** — no cycle created, no emails sent. The ticket stays pending quietly.

---

### Edge Case 2: User Replies Before First Reminder (Within 24 Hours)

**Situation**: Pending cycle created at 10:00 AM with `next_reminder_at = 10:00 AM tomorrow`. User replies at 2:00 PM the same day.

**How we handle it**: User's reply triggers Pending → Active. Resolution Alert Agent fires, sees user replied, finds the ACTIVE pending cycle, cancels it. When the scheduler polls at the next 5-minute mark, it finds the cycle is CANCELLED and skips it. No reminder ever sent.

---

### Edge Case 3: Two Work Notes Added Rapidly (Race Condition)

**Situation**: Engineer adds a note AND changes state to pending almost simultaneously. Two events fire within milliseconds.

**How we handle it**: Before creating a pending cycle, always check: "Does an ACTIVE cycle already exist for this incident?" If yes, don't create a duplicate. One incident = one active cycle at a time.

---

### Edge Case 4: Ack Agent Sets Ticket to Pending (Wrong Request Classification)

**Situation**: The Acknowledgement Agent classifies INC0000050 as a "Wrong Request" and sets it to Pending. The Pending Agent triggers.

**How we handle it**: Pending Agent checks `source_name = "Ack Agent"`. Since we know the Ack Agent already classified the intent, we skip LLM analysis and directly generate the reminder email from the Ack Agent's classification. The reminder says something like "Your ticket was submitted under the wrong form. Please resubmit using the correct request type."

---

### Edge Case 5: Server Restarts During the 24-Hour Wait

**Situation**: Server crashes at hour 12 of the 24-hour wait. In-memory timers are lost.

**How we handle it**: All timers are stored in PostgreSQL as `next_reminder_at` timestamps. The background scheduler is a cron that polls the DB every 5 minutes. When the server restarts, the cron starts again and picks up any overdue reminders on the next poll. Worst case: the reminder is delayed by up to 5 minutes.

---

### Edge Case 6: Multiple State Bounces Cause Agent Confusion

**Situation**: Pending Agent adds work note → SN activates → Resolution Alert Agent triggers → Pending Agent pushes back to pending → Pending Agent triggers again. Is this an infinite loop?

**How we handle it**: No. Both agents check `source_name` on the latest work note.
- Resolution Alert Agent sees source = "Pending Agent" → **DISCARD**
- Pending Agent sees source = "Pending Agent" → **DISCARD**
- The bounce resolves in 2 automatic discards. No infinite loop.

---

### Edge Case 7: Engineer Manually Reactivates Ticket While Reminders Are Running

**Situation**: Reminder 1/3 was sent. Engineer decides to work on it without waiting for user. Engineer clicks Active.

**How we handle it**: Pending → Active triggers Resolution Alert Agent. Source = Engineer. Cycle exists → BREAK CYCLE. Remaining reminders (2/3, 3/3) are never sent.

---

### Edge Case 8: All 3 Reminders Sent, User Never Replies

**Situation**: 72 hours pass. 3/3 reminders sent. User silent.

**How we handle it**: After sending reminder 3/3, the cycle status is set to `COMPLETED`. Final work note added: "Maximum reminders (3/3) reached. No response from caller." The ticket stays in Pending state. The engineer or a manager must decide what to do next (escalate, close, etc.). The Pending Agent's job is done.

---

## 💡 Best Approach for Implementation

### The Key Insight: source_name Is Everything

The entire design revolves around one simple check — **who wrote the latest work note?** This single field (`source_name`) eliminates the need for complex recursion guards, action ID tracking, or hash comparison. Both agents just ask "who did this?" and decide accordingly.

### Recommended Architecture

1. **Keep it simple** — Don't over-engineer. The `source_name` check replaces all the complex recursion guard logic from the previous spec.

2. **One table** — A single `pending_cycles` table is enough. No need for a separate `agent_actions` table. The cycle record itself tracks everything (status, reminder_count, next_reminder_at).

3. **Two LLM calls total** per cycle initiation:
   - Call 1: Analyze engineer's work note → is_caller_action_required? + extract question
   - Call 2: Generate the personalized reminder email HTML
   - Subsequent reminders (2/3, 3/3) can reuse the extracted question without re-analyzing.

4. **DB-backed scheduler** — A simple polling loop that runs every 5 minutes. No external task queue (Celery/Redis) needed at this stage.

5. **Both agents share the same pending_cycles table** — Pending Agent writes to it, Resolution Alert Agent reads from it to check if a cycle should be broken.

### Agent Trigger Mapping

| State Transition | Agent That Triggers | Primary Action |
| :--- | :--- | :--- |
| Active → Pending | **Pending Agent** | Analyze work note, create cycle, send reminders |
| Pending → Active | **Resolution Alert Agent** | Check if real activation, break cycle if needed, ping engineer |
