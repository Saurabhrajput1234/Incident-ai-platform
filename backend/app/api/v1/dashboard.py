"""
Dashboard API — aggregated metrics for the business dashboard.

GET /v1/dashboard/stats            — KPI summary counts
GET /v1/dashboard/trends           — Incidents created per day (last 30 days)
GET /v1/dashboard/by-group         — Incidents per assignment group
GET /v1/dashboard/by-priority      — Incidents per priority
GET /v1/dashboard/by-state         — Incidents per state
GET /v1/dashboard/triage-stats     — Triage agent analytics (success/fail, avg time to assign)
GET /v1/dashboard/triage-logs      — Recent triage activity
GET /v1/dashboard/ack-stats        — Acknowledgement agent analytics (template breakdown)
GET /v1/dashboard/ack-logs         — Recent acknowledgement activity
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, cast, Date, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres.session import get_db
from app.modules.incidents.model import Incident
from app.modules.agents.triage.models import AssignmentHistory

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    total = await db.scalar(select(func.count()).select_from(Incident))
    new = await db.scalar(select(func.count()).select_from(Incident).where(Incident.state == "new"))
    active = await db.scalar(select(func.count()).select_from(Incident).where(Incident.state == "in_progress"))
    on_hold = await db.scalar(select(func.count()).select_from(Incident).where(Incident.state == "on_hold"))
    resolved = await db.scalar(select(func.count()).select_from(Incident).where(Incident.state == "resolved"))
    closed = await db.scalar(select(func.count()).select_from(Incident).where(Incident.state == "closed"))
    unassigned = await db.scalar(
        select(func.count()).select_from(Incident)
        .where(Incident.assigned_to == None)
        .where(Incident.state.in_(["new", "in_progress"]))
    )
    critical = await db.scalar(
        select(func.count()).select_from(Incident).where(Incident.priority == "1")
    )
    return {
        "total": total or 0, "new": new or 0, "active": active or 0,
        "on_hold": on_hold or 0, "resolved": resolved or 0, "closed": closed or 0,
        "unassigned": unassigned or 0, "critical": critical or 0,
    }


@router.get("/trends")
async def get_trends(db: AsyncSession = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=29)
    result = await db.execute(
        select(cast(Incident.created_at, Date).label("day"), func.count().label("count"))
        .where(Incident.created_at >= since)
        .group_by("day").order_by("day")
    )
    return [{"date": str(r.day), "count": r.count} for r in result.all()]


@router.get("/by-group")
async def get_by_group(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Incident.assignment_group.label("group"), func.count().label("count"))
        .where(Incident.assignment_group != None)
        .group_by(Incident.assignment_group)
        .order_by(func.count().desc()).limit(15)
    )
    return [{"group": r.group, "count": r.count} for r in result.all()]


@router.get("/by-priority")
async def get_by_priority(db: AsyncSession = Depends(get_db)):
    labels = {"1": "Critical", "2": "High", "3": "Medium", "4": "Low"}
    result = await db.execute(
        select(Incident.priority, func.count().label("count"))
        .group_by(Incident.priority).order_by(Incident.priority)
    )
    return [{"priority": labels.get(r.priority, r.priority), "count": r.count} for r in result.all()]


@router.get("/by-state")
async def get_by_state(db: AsyncSession = Depends(get_db)):
    labels = {
        "new": "New", "in_progress": "Active", "on_hold": "On Hold",
        "resolved": "Resolved", "closed": "Closed", "cancelled": "Cancelled"
    }
    result = await db.execute(
        select(Incident.state, func.count().label("count"))
        .group_by(Incident.state).order_by(func.count().desc())
    )
    return [{"state": labels.get(r.state, r.state), "count": r.count} for r in result.all()]


@router.get("/triage-stats")
async def get_triage_stats(db: AsyncSession = Depends(get_db)):
    """
    Triage agent analytics:
    - Total assignments, success rate
    - Avg time from incident creation to assignment (minutes)
    - LLM-resolved vs direct group assignments
    - Assignments per group
    - Fallback usage
    """
    total_assignments = await db.scalar(select(func.count()).select_from(AssignmentHistory))

    # Assigned = has assigned_to, Unassigned = no engineer found
    assigned_count = await db.scalar(
        select(func.count()).select_from(Incident)
        .where(Incident.assigned_to != None)
        .where(Incident.work_notes.ilike("%[Triage%"))
    )
    failed_count = await db.scalar(
        select(func.count()).select_from(Incident)
        .where(Incident.assigned_to == None)
        .where(Incident.work_notes.ilike("%[Triage%"))
    )

    # Avg time to assign: difference between created_at and updated_at for triaged+assigned
    avg_result = await db.execute(
        select(
            func.avg(
                func.extract("epoch", Incident.updated_at) - func.extract("epoch", Incident.created_at)
            ).label("avg_seconds")
        )
        .where(Incident.assigned_to != None)
        .where(Incident.work_notes.ilike("%[Triage Agent]%"))
    )
    avg_seconds = avg_result.scalar() or 0
    avg_minutes = round(avg_seconds / 60, 1)

    # LLM-resolved group vs direct
    llm_resolved = await db.scalar(
        select(func.count()).select_from(AssignmentHistory).where(AssignmentHistory.llm_resolved_group == True)
    )
    direct = (total_assignments or 0) - (llm_resolved or 0)

    # Fallback usage
    fallback = await db.scalar(
        select(func.count()).select_from(AssignmentHistory)
        .where(AssignmentHistory.notes.ilike("%FALLBACK%"))
    )

    # Assignments per group (top 10)
    group_result = await db.execute(
        select(AssignmentHistory.assignment_group, func.count().label("count"))
        .group_by(AssignmentHistory.assignment_group)
        .order_by(func.count().desc()).limit(10)
    )

    # Recent assignments
    recent_result = await db.execute(
        select(AssignmentHistory)
        .order_by(AssignmentHistory.assigned_at.desc())
        .limit(20)
    )
    recent = recent_result.scalars().all()

    return {
        "total_assignments": total_assignments or 0,
        "assigned_count": assigned_count or 0,
        "failed_count": failed_count or 0,
        "avg_time_to_assign_minutes": avg_minutes,
        "llm_resolved_count": llm_resolved or 0,
        "direct_group_count": direct,
        "fallback_used_count": fallback or 0,
        "assignments_by_group": [
            {"group": r.assignment_group, "count": r.count} for r in group_result.all()
        ],
        "recent_assignments": [
            {
                "incident_number": r.incident_number,
                "assignment_group": r.assignment_group,
                "engineer_name": r.engineer_name,
                "engineer_email": r.engineer_email,
                "shift_code": r.shift_code,
                "llm_resolved": r.llm_resolved_group,
                "notes": r.notes,
                "assigned_at": r.assigned_at.isoformat() if r.assigned_at else None,
            }
            for r in recent
        ],
    }


@router.get("/triage-logs")
async def get_triage_logs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            Incident.incident_number, Incident.short_description,
            Incident.assignment_group, Incident.assigned_to,
            Incident.state, Incident.priority,
            Incident.work_notes, Incident.created_at, Incident.updated_at,
        )
        .where(Incident.work_notes.ilike("%[Triage%"))
        .order_by(Incident.updated_at.desc()).limit(50)
    )
    rows = result.all()
    return [
        {
            "incident_number": r.incident_number,
            "short_description": r.short_description,
            "assignment_group": r.assignment_group,
            "assigned_to": r.assigned_to,
            "state": r.state,
            "priority": r.priority,
            "work_notes": r.work_notes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            # Time to assign in minutes
            "minutes_to_assign": round(
                (r.updated_at - r.created_at).total_seconds() / 60, 1
            ) if r.assigned_to and r.updated_at and r.created_at else None,
        }
        for r in rows
    ]


@router.get("/ack-stats")
async def get_ack_stats(db: AsyncSession = Depends(get_db)):
    """
    Acknowledgement agent analytics derived from work_notes:
    - Total ack runs, success/fail counts
    - Template breakdown (Standard Incident, Wrong Request, Access Request, Service Request, Salesforce)
    - On Hold count (non-standard classifications)
    """
    # Total ack processed
    total_ack = await db.scalar(
        select(func.count()).select_from(Incident)
        .where(Incident.work_notes.ilike("%Acknowledgement Agent%"))
    )

    # Template breakdown from work_notes content
    standard = await db.scalar(
        select(func.count()).select_from(Incident)
        .where(Incident.work_notes.ilike("%Standard Incident%"))
    )
    wrong_request = await db.scalar(
        select(func.count()).select_from(Incident)
        .where(Incident.work_notes.ilike("%Wrong Request%"))
    )
    access_request = await db.scalar(
        select(func.count()).select_from(Incident)
        .where(Incident.work_notes.ilike("%Access Request%"))
    )
    service_request = await db.scalar(
        select(func.count()).select_from(Incident)
        .where(Incident.work_notes.ilike("%Service Request%"))
    )
    salesforce = await db.scalar(
        select(func.count()).select_from(Incident)
        .where(Incident.work_notes.ilike("%Salesforce%"))
    )

    # On Hold incidents (set by ack agent)
    on_hold_by_ack = await db.scalar(
        select(func.count()).select_from(Incident)
        .where(Incident.state == "on_hold")
        .where(Incident.work_notes.ilike("%Acknowledgement Agent%"))
    )

    # Recent ack logs
    recent_result = await db.execute(
        select(
            Incident.incident_number, Incident.short_description,
            Incident.state, Incident.priority,
            Incident.assignment_group, Incident.assigned_to,
            Incident.work_notes, Incident.updated_at,
        )
        .where(Incident.work_notes.ilike("%Acknowledgement Agent%"))
        .order_by(Incident.updated_at.desc()).limit(30)
    )

    def detect_template(work_notes: str) -> str:
        if not work_notes:
            return "Unknown"
        wn = work_notes.lower()
        if "salesforce" in wn:
            return "Salesforce Request"
        if "wrong request" in wn:
            return "Wrong Request"
        if "access request" in wn:
            return "Access Request"
        if "service request" in wn:
            return "Service Request"
        if "standard incident" in wn:
            return "Standard Incident"
        return "Unknown"

    recent_rows = recent_result.all()

    return {
        "total_processed": total_ack or 0,
        "on_hold_count": on_hold_by_ack or 0,
        "template_breakdown": [
            {"template": "Standard Incident", "count": standard or 0, "color": "#22c55e"},
            {"template": "Wrong Request", "count": wrong_request or 0, "color": "#f97316"},
            {"template": "Access Request", "count": access_request or 0, "color": "#3b82f6"},
            {"template": "Service Request", "count": service_request or 0, "color": "#8b5cf6"},
            {"template": "Salesforce Request", "count": salesforce or 0, "color": "#ec4899"},
        ],
        "recent_logs": [
            {
                "incident_number": r.incident_number,
                "short_description": r.short_description,
                "state": r.state,
                "priority": r.priority,
                "assignment_group": r.assignment_group,
                "assigned_to": r.assigned_to,
                "template": detect_template(r.work_notes or ""),
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in recent_rows
        ],
    }



@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """High-level KPI counts."""
    total = await db.scalar(select(func.count()).select_from(Incident))
    new = await db.scalar(select(func.count()).select_from(Incident).where(Incident.state == "new"))
    active = await db.scalar(select(func.count()).select_from(Incident).where(Incident.state == "in_progress"))
    on_hold = await db.scalar(select(func.count()).select_from(Incident).where(Incident.state == "on_hold"))
    resolved = await db.scalar(select(func.count()).select_from(Incident).where(Incident.state == "resolved"))
    closed = await db.scalar(select(func.count()).select_from(Incident).where(Incident.state == "closed"))
    unassigned = await db.scalar(
        select(func.count()).select_from(Incident)
        .where(Incident.assigned_to == None)
        .where(Incident.state.in_(["new", "in_progress"]))
    )
    critical = await db.scalar(
        select(func.count()).select_from(Incident).where(Incident.priority == "1")
    )
    return {
        "total": total or 0,
        "new": new or 0,
        "active": active or 0,
        "on_hold": on_hold or 0,
        "resolved": resolved or 0,
        "closed": closed or 0,
        "unassigned": unassigned or 0,
        "critical": critical or 0,
    }


@router.get("/trends")
async def get_trends(db: AsyncSession = Depends(get_db)):
    """Incidents created per day for the last 30 days."""
    since = datetime.now(timezone.utc) - timedelta(days=29)
    result = await db.execute(
        select(
            cast(Incident.created_at, Date).label("day"),
            func.count().label("count"),
        )
        .where(Incident.created_at >= since)
        .group_by("day")
        .order_by("day")
    )
    rows = result.all()
    return [{"date": str(r.day), "count": r.count} for r in rows]


@router.get("/by-group")
async def get_by_group(db: AsyncSession = Depends(get_db)):
    """Incident count per assignment group."""
    result = await db.execute(
        select(
            Incident.assignment_group.label("group"),
            func.count().label("count"),
        )
        .where(Incident.assignment_group != None)
        .group_by(Incident.assignment_group)
        .order_by(func.count().desc())
        .limit(15)
    )
    rows = result.all()
    return [{"group": r.group, "count": r.count} for r in rows]


@router.get("/by-priority")
async def get_by_priority(db: AsyncSession = Depends(get_db)):
    """Incident count per priority."""
    labels = {"1": "Critical", "2": "High", "3": "Medium", "4": "Low"}
    result = await db.execute(
        select(Incident.priority, func.count().label("count"))
        .group_by(Incident.priority)
        .order_by(Incident.priority)
    )
    rows = result.all()
    return [{"priority": labels.get(r.priority, r.priority), "count": r.count} for r in rows]


@router.get("/by-state")
async def get_by_state(db: AsyncSession = Depends(get_db)):
    """Incident count per state."""
    labels = {
        "new": "New", "in_progress": "Active", "on_hold": "On Hold",
        "resolved": "Resolved", "closed": "Closed", "cancelled": "Cancelled"
    }
    result = await db.execute(
        select(Incident.state, func.count().label("count"))
        .group_by(Incident.state)
        .order_by(func.count().desc())
    )
    rows = result.all()
    return [{"state": labels.get(r.state, r.state), "count": r.count} for r in rows]


@router.get("/triage-logs")
async def get_triage_logs(db: AsyncSession = Depends(get_db)):
    """Recent incidents that were processed by triage (have triage work notes)."""
    result = await db.execute(
        select(
            Incident.incident_number,
            Incident.short_description,
            Incident.assignment_group,
            Incident.assigned_to,
            Incident.state,
            Incident.priority,
            Incident.work_notes,
            Incident.updated_at,
        )
        .where(Incident.work_notes.ilike("%[Triage%"))
        .order_by(Incident.updated_at.desc())
        .limit(50)
    )
    rows = result.all()
    return [
        {
            "incident_number": r.incident_number,
            "short_description": r.short_description,
            "assignment_group": r.assignment_group,
            "assigned_to": r.assigned_to,
            "state": r.state,
            "priority": r.priority,
            "work_notes": r.work_notes,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]
