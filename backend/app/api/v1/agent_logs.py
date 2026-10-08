"""
Agent Execution Logs API.

Returns a unified log combining:
  1. agent_executions table rows  (all agents)
  2. SEND_REMINDER work notes from incident_work_notes (PendingAgent reminders)
     — these are virtual rows so every reminder appears as its own log entry

GET /v1/agent-logs       — paginated unified list with filters
GET /v1/agent-logs/stats — summary counts per agent/status
"""
import re
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres.session import get_db

router = APIRouter(prefix="/agent-logs", tags=["agent-logs"])


# ── helpers ────────────────────────────────────────────────────────────────────

def _duration(started_at, completed_at) -> float | None:
    if started_at and completed_at:
        return round((completed_at - started_at).total_seconds(), 2)
    return None


def _extract_reminder_number(message: str) -> str:
    """Pull 'Reminder X of Y' from a SEND_REMINDER work note message."""
    m = re.search(r"Reminder\s+(\d+)\s+of\s+(\d+)", message or "", re.IGNORECASE)
    if m:
        return f"Reminder {m.group(1)}/{m.group(2)} Sent"
    return "Reminder Sent"


# ── main list endpoint ─────────────────────────────────────────────────────────

@router.get("")
async def list_agent_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    agent_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    incident_number: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns agent_executions rows merged with SEND_REMINDER work notes.
    Sorted by started_at DESC.  Paginated.
    """
    # ── 1. Build agent_executions query ───────────────────────────────────────
    ae_where_parts = ["1=1"]
    ae_params: dict = {}

    # Filter: agent_name — skip reminder rows when filtering for non-PendingAgent
    include_reminders = True
    if agent_name:
        ae_where_parts.append("ae.agent_name = :agent_name")
        ae_params["agent_name"] = agent_name
        if agent_name != "PendingAgent":
            include_reminders = False

    if status:
        s = status.lower()
        if s in ("failed", "error"):
            ae_where_parts.append("ae.status IN ('failed', 'error')")
            include_reminders = False  # reminders don't have failed status tracked
        elif s in ("success", "completed"):
            ae_where_parts.append("ae.status IN ('success', 'completed')")
        elif s in ("running", "started"):
            ae_where_parts.append("ae.status IN ('running', 'started')")
            include_reminders = False
        else:
            ae_where_parts.append("ae.status = :status")
            ae_params["status"] = status

    if incident_number:
        inc = incident_number.upper().strip()
        ae_where_parts.append("i.incident_number ILIKE :incident_number")
        ae_params["incident_number"] = f"%{inc}%"

    ae_where = "WHERE " + " AND ".join(ae_where_parts)

    ae_q = f"""
        SELECT
            ae.id,
            ae.incident_id,
            i.incident_number,
            ae.agent_name,
            ae.triggering_event_type,
            ae.status,
            ae.attempt_count,
            ae.started_at,
            ae.completed_at,
            ae.error,
            ae.correlation_id
        FROM agent_executions ae
        LEFT JOIN incidents i ON i.id = ae.incident_id
        {ae_where}
    """

    ae_result = await db.execute(text(ae_q), ae_params)
    ae_rows = ae_result.mappings().all()

    # ── 2. Fetch SEND_REMINDER work notes ─────────────────────────────────────
    reminder_rows = []
    if include_reminders:
        wn_params: dict = {
            "source_type": "PENDING_AGENT",
            "action_type": "SEND_REMINDER",
        }
        wn_where_extra = ""
        if incident_number:
            wn_where_extra += " AND i.incident_number ILIKE :wn_incident_number"
            wn_params["wn_incident_number"] = f"%{incident_number.upper().strip()}%"

        wn_q = f"""
            SELECT
                wn.id,
                wn.incident_id,
                i.incident_number,
                wn.message,
                wn.created_at
            FROM incident_work_notes wn
            LEFT JOIN incidents i ON i.id = wn.incident_id
            WHERE wn.source_type = :source_type
              AND wn.action_type = :action_type
              {wn_where_extra}
        """
        wn_result = await db.execute(text(wn_q), wn_params)
        reminder_rows = wn_result.mappings().all()

    # ── 3. Build unified list ──────────────────────────────────────────────────
    items = []

    for row in ae_rows:
        items.append({
            "id": row["id"],
            "incident_id": row["incident_id"],
            "incident_number": row["incident_number"],
            "agent_name": row["agent_name"],
            "triggering_event_type": row["triggering_event_type"],
            "status": row["status"],
            "attempt_count": row["attempt_count"],
            "started_at": row["started_at"].isoformat() if row["started_at"] else None,
            "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
            "duration_seconds": _duration(row["started_at"], row["completed_at"]),
            "error": row["error"],
            "correlation_id": row["correlation_id"],
            "log_type": "execution",
        })

    for row in reminder_rows:
        event_label = _extract_reminder_number(row["message"])
        items.append({
            "id": f"reminder-{row['id']}",
            "incident_id": row["incident_id"],
            "incident_number": row["incident_number"],
            "agent_name": "PendingAgent",
            "triggering_event_type": event_label,
            "status": "success",
            "attempt_count": 1,
            "started_at": row["created_at"].isoformat() if row["created_at"] else None,
            "completed_at": row["created_at"].isoformat() if row["created_at"] else None,
            "duration_seconds": None,
            "error": None,
            "correlation_id": None,
            "log_type": "reminder",
        })

    # ── 4. Sort merged list by started_at DESC ────────────────────────────────
    items.sort(key=lambda x: x["started_at"] or "", reverse=True)

    # ── 5. Paginate in memory ─────────────────────────────────────────────────
    total = len(items)
    offset = (page - 1) * page_size
    paged = items[offset: offset + page_size]

    return {
        "items": paged,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": -(-total // page_size) if total else 1,
    }


# ── stats endpoint ─────────────────────────────────────────────────────────────

@router.get("/stats")
async def agent_log_stats(db: AsyncSession = Depends(get_db)):
    """Summary counts by agent + status, including reminder counts for PendingAgent."""

    # agent_executions stats
    ae_q = text("""
        SELECT
            agent_name,
            status,
            COUNT(*) AS count,
            AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) AS avg_duration_seconds
        FROM agent_executions
        WHERE started_at IS NOT NULL
        GROUP BY agent_name, status
        ORDER BY agent_name, status
    """)
    ae_result = await db.execute(ae_q)
    ae_rows = ae_result.mappings().all()

    by_agent: dict = {}
    for row in ae_rows:
        name = row["agent_name"] or "unknown"
        if name not in by_agent:
            by_agent[name] = {
                "agent_name": name, "total": 0, "success": 0,
                "failed": 0, "running": 0, "reminders_sent": 0,
                "avg_duration_seconds": None,
            }
        count = row["count"]
        by_agent[name]["total"] += count
        s = (row["status"] or "").lower()
        if s in ("success", "completed"):
            by_agent[name]["success"] += count
        elif s in ("failed", "error"):
            by_agent[name]["failed"] += count
        elif s in ("running", "started"):
            by_agent[name]["running"] += count
        if row["avg_duration_seconds"] is not None:
            by_agent[name]["avg_duration_seconds"] = round(row["avg_duration_seconds"], 2)

    # reminder counts from work notes
    reminder_q = text("""
        SELECT COUNT(*) AS cnt
        FROM incident_work_notes
        WHERE source_type = 'PENDING_AGENT'
          AND action_type = 'SEND_REMINDER'
    """)
    r = await db.execute(reminder_q)
    reminder_count = r.scalar() or 0

    if "PendingAgent" not in by_agent:
        by_agent["PendingAgent"] = {
            "agent_name": "PendingAgent", "total": 0, "success": 0,
            "failed": 0, "running": 0, "reminders_sent": 0,
            "avg_duration_seconds": None,
        }
    by_agent["PendingAgent"]["reminders_sent"] = reminder_count

    # overall totals
    total_q = text("""
        SELECT COUNT(*),
               COUNT(*) FILTER (WHERE status IN ('success','completed'))
        FROM agent_executions
    """)
    t = await db.execute(total_q)
    t_row = t.fetchone()

    return {
        "total_executions": (t_row[0] if t_row else 0) + reminder_count,
        "total_success": (t_row[1] if t_row else 0) + reminder_count,
        "by_agent": list(by_agent.values()),
    }
