# 🚨 Agent Collision Problem: Pending Agent vs Resolution Alert Agent

## The Core Problem

When a ticket is in **Pending** state and the Pending Agent does its job (sends a reminder email and adds a work note), ServiceNow's automatic behavior creates a dangerous situation:

```
Pending Agent adds work note: "Reminder 1/3 sent to user"
        ↓
ServiceNow sees ticket was updated
        ↓
SN automatically changes state: Pending → Active
        ↓
Resolution Alert Agent detects: "Pending → Active happened!"
        ↓
Resolution Alert Agent reads latest work note...
        ↓
💥 THE PROBLEM: The latest work note is from Pending Agent, NOT from the user.
   But Resolution Alert Agent just sees "ticket went Active" and starts working.
```

**If the Resolution Alert Agent is not careful, it will:**
- Think someone responded to the ticket
- Break the pending reminder cycle
- Ping the engineer saying "user replied!" when they didn't
- The Pending Agent's reminder loop gets killed for no reason

---

## Why This Is Dangerous

This collision happens **every single time** the Pending Agent sends a reminder. It's not a rare edge case — it happens 3 times per pending cycle (once per reminder). If we don't solve it, the Pending Agent can never complete a single reminder cycle because the Resolution Alert Agent will break it every time.

### The Chaos Timeline (What Goes Wrong Without a Fix)

```
TIME        WHAT HAPPENS                                    PROBLEM
─────────── ────────────────────────────────────────────── ──────────────────────────
10:00 AM    Engineer sets ticket to Pending                 ✅ Fine
10:00 AM    Pending Agent creates cycle, sends Reminder 1   ✅ Fine
10:00 AM    Pending Agent adds work note                    ✅ Fine
10:01 AM    SN auto-activates ticket (Pending → Active)     ⚠️ Here it begins...
10:01 AM    Resolution Alert Agent triggers                 💥 WRONG!
            Reads work note: "Reminder 1/3 sent"
            Thinks: "Ticket is active, let me check 
            pending cycles..."
            Finds cycle PC-001 → BREAKS THE CYCLE
            Pings engineer: "Ticket reactivated!"
            
10:01 AM    Pending Agent tries to push back to Pending     💥 CONFLICT
            But cycle is already CANCELLED by Resolution 
            Alert Agent
            
RESULT:     Reminder 2/3 and 3/3 never sent.
            Engineer gets a false "user replied" notification.
            User never gets reminded. Ticket rots in limbo.
```

This exact sequence repeats every time a reminder is sent. The Pending Agent's reminder loop is effectively **impossible** without addressing this.

---

## The Solution: source_name Gating

The fix is straightforward: **the Resolution Alert Agent must check WHO caused the ticket to go Active before doing anything.**

### How It Works

Every work note has a `source_name` field. When the Resolution Alert Agent triggers on Pending → Active, it reads the latest work note's `source_name` and makes a decision:

| Latest Work Note source_name | What It Means | Resolution Alert Agent Decision |
| :--- | :--- | :--- |
| **"Pending Agent"** | The Pending Agent just added a reminder work note. SN auto-activated. This is NOT a real human activation. | 🛑 **IMMEDIATELY DISCARD. Do nothing.** Let the Pending Agent push ticket back to Pending. |
| **User's name** (e.g. "Tina Sharma") | The actual user/caller replied with information. This IS a real activation. | ✅ **PROCEED.** Check pending_cycles → break cycle → ping engineer. |
| **Engineer's name** (e.g. "Ravi Kumar") | Engineer manually reactivated the ticket. They decided to work on it. | ✅ **PROCEED.** Check pending_cycles → break cycle if exists. |
| **"Ack Agent"** | Acknowledgement Agent updated the ticket. Not a user action. | 🛑 **DISCARD.** Similar to Pending Agent — system action, not human. |
| **Any other system name** | Another automated system updated the ticket. | 🛑 **DISCARD** unless confirmed as a human action. |

### The Fixed Timeline (With source_name Check)

```
TIME        WHAT HAPPENS                                    RESULT
─────────── ────────────────────────────────────────────── ──────────────────────────
10:00 AM    Engineer sets ticket to Pending                 ✅ Pending Agent triggers
10:00 AM    Pending Agent creates cycle, sends Reminder 1   ✅ Cycle PC-001 created
10:00 AM    Pending Agent adds work note                    ✅ source_name = "Pending Agent"
10:01 AM    SN auto-activates ticket (Pending → Active)     

10:01 AM    Resolution Alert Agent triggers                 
            Reads latest work note source_name              
            source_name = "Pending Agent"                   
            → 🛑 DISCARD. Not a real activation.            ✅ No false action taken

10:01 AM    Pending Agent pushes ticket back to Pending     ✅ Cycle continues normally

Day 1       24hr timer fires. Reminder 2/3 sent.            ✅ Same bounce happens
10:00 AM    Resolution Alert Agent fires and DISCARDs       ✅ Cycle still alive
            again (source = "Pending Agent")                

Day 1       USER ACTUALLY REPLIES                           
3:00 PM     User adds comment, SN activates ticket          
            Resolution Alert Agent triggers                 
            source_name = "Tina Sharma" (User)              
            → ✅ PROCEED. Real user reply!                  
            Check pending_cycles → PC-001 exists            
            BREAK CYCLE → Cancel remaining reminders        
            Ping engineer Ravi                              ✅ Correct action taken
```

---

## But What If source_name Is Not Reliable?

There are scenarios where `source_name` alone might not be enough. Let's address each:

### Problem A: What if ServiceNow doesn't give us source_name?

**Situation**: The SN webhook/API only tells us "state changed to Active" but doesn't include who did it.

**Fallback Solution**: Use a **time-based guard**. When the Pending Agent adds a work note, it records the exact timestamp in the `pending_cycles` table as `last_agent_action_at`. When the Resolution Alert Agent triggers, it checks:

```
IF (NOW - last_agent_action_at) < 60 seconds
    → This activation was likely caused by the Pending Agent's work note
    → DISCARD
ELSE
    → This is a real human activation
    → PROCEED
```

The logic: if the ticket went Pending → Active within 60 seconds of the Pending Agent's last action, it's almost certainly the SN auto-activation bounce. Real human replies take much longer.

### Problem B: What if two events happen at the same time?

**Situation**: The Pending Agent adds a work note at 10:00:00 AM, and the user also replies at 10:00:02 AM (2 seconds apart). Both cause the ticket to go Active. Which one does the Resolution Alert Agent respond to?

**Solution**: When the Resolution Alert Agent triggers, don't just read the LATEST work note — read **all work notes added in the last 2 minutes** and check each `source_name`:

- If ANY work note in that window has `source_name = User` → it's a real user reply → PROCEED and break cycle
- If ALL work notes are from "Pending Agent" → DISCARD

**The user reply always takes priority.** Even if the Pending Agent also acted in the same window, the user's reply is the important event.

### Problem C: What if the Pending Agent crashes mid-action?

**Situation**: Pending Agent adds work note (SN activates ticket) but crashes before it can push ticket back to Pending. Now the ticket is stuck in Active, the cycle is still ACTIVE in the DB, but no one is pushing it back.

**Solution**: The background scheduler handles this. On its next poll (every 5 minutes), it checks:

```
Is the cycle ACTIVE?  → YES
Is next_reminder_at overdue?  → Check
Is the ticket currently in Active state (not Pending)?  → YES (stuck!)
Was last_agent_action_at > 2 minutes ago?  → YES (agent crashed)
→ Push ticket back to Pending and continue the cycle
```

The scheduler acts as a self-healing mechanism for incomplete bounces.

---

## Decision Matrix: When Does Each Agent Act vs Discard?

### Pending Agent (Active → Pending trigger)

| Check | Action |
| :--- | :--- |
| source_name = "Pending Agent" | 🛑 DISCARD (own action bouncing back) |
| source_name = "Ack Agent" | ✅ PROCEED (create cycle, direct email) |
| source_name = Engineer name | ✅ PROCEED (analyze work note via LLM) |
| Active cycle already exists for this incident | 🛑 DISCARD (don't create duplicate cycle) |

### Resolution Alert Agent (Pending → Active trigger)

| Check | Action |
| :--- | :--- |
| source_name = "Pending Agent" | 🛑 DISCARD (auto-activation from reminder, not real) |
| source_name = "Ack Agent" | 🛑 DISCARD (system action, not human) |
| source_name = User/Caller name | ✅ PROCEED (real reply → break cycle → ping engineer) |
| source_name = Engineer name | ✅ PROCEED (manual reactivation → break cycle if exists) |
| (NOW - last_agent_action_at) < 60s | 🛑 DISCARD (fallback guard if source_name unavailable) |

---

## Summary: The Three Layers of Protection

To completely prevent the Pending Agent vs Resolution Alert Agent collision:

### Layer 1: source_name Check (Primary)
Read who wrote the latest work note. If it's "Pending Agent" or "Ack Agent" (system agents), discard. Only act on human sources (User, Engineer).

### Layer 2: Time-Based Guard (Fallback)
If source_name is unavailable or unreliable, check the time gap between the Pending Agent's last action and the state change. Under 60 seconds = system bounce, not human.

### Layer 3: Pending Cycle Awareness (Safety Net)
Before breaking a cycle, the Resolution Alert Agent double-checks the `pending_cycles` table. It verifies:
- The cycle is still ACTIVE (not already completed/cancelled)
- The latest work note is genuinely from a human, not a system agent
- The ticket state actually changed due to an external event

All three layers together ensure zero false cycle breaks and zero false engineer notifications.
