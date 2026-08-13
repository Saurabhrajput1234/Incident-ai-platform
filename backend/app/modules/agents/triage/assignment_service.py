"""
Engineer Assignment Service.

Responsibilities:
  1. Filter engineers to those on a currently ACTIVE shift (time window check)
  2. Fallback to any working-shift engineer if no active window match
  3. Select via persistent round-robin (DB-backed, concurrency safe)
  4. Record assignment in assignment_history
  5. Return result — caller (TriageService) updates the incident

No skills, experience, workload, or AI scoring.
Only shift activity and round-robin order matter.
"""
import logging
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agents.triage.models import AssignmentGroupRRState, AssignmentHistory
from app.modules.context.schemas import EngineerContext
from app.modules.shift_roster.enums import WORKING_SHIFTS
from app.modules.shift_roster.shift_time_checker import is_shift_active_now

logger = logging.getLogger(__name__)

NO_AVAILABLE_ENGINEER = "NO_AVAILABLE_ENGINEER"


class AssignmentResult:
    """Result returned by the Assignment Service."""
    def __init__(
        self,
        success: bool,
        engineer: EngineerContext | None = None,
        reason: str = "",
        fallback_used: bool = False,
    ):
        self.success = success
        self.engineer = engineer
        self.reason = reason
        self.fallback_used = fallback_used


class AssignmentService:
    """
    Assigns engineers to incidents using persistent round-robin.
    Only shift availability matters — no scoring, no AI logic.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def assign_engineer(
        self,
        incident_id: str,
        incident_number: str,
        assignment_group: str,
        engineers: list[EngineerContext],
        roster_date_str: str | None = None,
        llm_resolved_group: bool = False,
    ) -> AssignmentResult:
        """
        Select the next available engineer via round-robin.

        Priority:
          1. Engineers whose shift is currently active (time window check)
          2. Fallback: any engineer on a working shift today (if none in active window)
          3. NO_AVAILABLE_ENGINEER if no working-shift engineers at all
        """

        # Step 1: Prefer engineers in an active shift window right now
        active_now = [
            e for e in engineers
            if e.is_shift_active  # set by context builder using shift_time_checker
        ]

        # Step 2: Fallback — any engineer on a working shift today
        working_today = [
            e for e in engineers
            if e.is_available and not e.is_shift_active
        ]

        fallback_used = False
        if active_now:
            candidates = active_now
            logger.info(
                f"[AssignmentService] {incident_number}: "
                f"{len(candidates)} engineers in active shift window"
            )
        elif working_today:
            candidates = working_today
            fallback_used = True
            logger.warning(
                f"[AssignmentService] {incident_number}: "
                f"No active shift window. Fallback to {len(candidates)} working-shift engineers."
            )
        else:
            logger.warning(
                f"[AssignmentService] {incident_number}: "
                f"{NO_AVAILABLE_ENGINEER} in '{assignment_group}'"
            )
            return AssignmentResult(success=False, reason=NO_AVAILABLE_ENGINEER)

        # Step 3: Get/create rr_state with row-level lock (concurrency safe)
        result = await self.db.execute(
            select(AssignmentGroupRRState)
            .where(AssignmentGroupRRState.assignment_group == assignment_group)
            .with_for_update()
        )
        rr_state = result.scalar_one_or_none()

        if rr_state is None:
            # First assignment for this group — start at index 0
            rr_state = AssignmentGroupRRState(
                assignment_group=assignment_group,
                last_index=0,
            )
            self.db.add(rr_state)
            await self.db.flush()
            next_index = 0
        else:
            next_index = (rr_state.last_index + 1) % len(candidates)

        # Step 4: Select engineer
        selected = candidates[next_index]

        # Step 5: Persist new rr index
        await self.db.execute(
            update(AssignmentGroupRRState)
            .where(AssignmentGroupRRState.assignment_group == assignment_group)
            .values(last_index=next_index, updated_at=datetime.now(timezone.utc))
        )

        # Step 6: Record in assignment_history
        history = AssignmentHistory(
            id=str(uuid.uuid4()),
            incident_id=incident_id,
            incident_number=incident_number,
            assignment_group=assignment_group,
            engineer_id=selected.engineer_id,
            engineer_name=selected.name,
            engineer_email=selected.email,
            shift_code=selected.current_shift,
            roster_date=str(roster_date_str) if roster_date_str else None,
            llm_resolved_group=llm_resolved_group,
            notes=(
                f"{'[FALLBACK] ' if fallback_used else ''}"
                f"Round-robin index {next_index}/{len(candidates)-1}. "
                f"Shift: {selected.current_shift}, "
                f"Active now: {selected.is_shift_active}"
            ),
        )
        self.db.add(history)
        await self.db.commit()

        reason = (
            f"{'[FALLBACK — no active shift window] ' if fallback_used else ''}"
            f"Assigned {selected.name} via round-robin "
            f"(index {next_index}/{len(candidates)-1}, "
            f"shift={selected.current_shift}, "
            f"active_now={selected.is_shift_active})"
        )

        logger.info(
            f"[AssignmentService] {incident_number} → {selected.name} "
            f"(rr={next_index}, shift={selected.current_shift}, "
            f"active={selected.is_shift_active}, group={assignment_group})"
        )

        return AssignmentResult(
            success=True,
            engineer=selected,
            reason=reason,
            fallback_used=fallback_used,
        )
