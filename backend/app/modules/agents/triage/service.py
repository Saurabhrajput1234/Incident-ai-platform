"""
Triage Service — orchestrates the full triage flow.

Flow:
  1. LLM resolves assignment group (if common queue or missing)
  2. Build AIContext (incident + engineers for that group + date)
  3. TriageAgent confirms group and counts availability
  4. AssignmentService picks engineer via persistent round-robin
  5. IncidentService updates incident with assigned engineer

Responsibilities:
  TriageAgent       → determines/confirms assignment group
  AssignmentService → selects engineer (round-robin, availability only)
  IncidentService   → persists assignment to PostgreSQL
"""
import logging
from datetime import date, datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_platform.services.llm_service import LLMService
from app.modules.agents.base.request import AgentRequest
from app.modules.agents.base.response import AgentResponse
from app.modules.agents.triage.agent import TriageAgent
from app.modules.agents.triage.assignment_service import AssignmentService, NO_AVAILABLE_ENGINEER
from app.modules.agents.triage.prompts import build_assignment_group_messages, ASSIGNMENT_GROUPS, is_common_queue
from app.modules.agents.triage.schemas import TriageResult
from app.modules.context.service import ContextService
from app.modules.incidents.service import IncidentService
from app.modules.incidents.schemas import IncidentUpdate

logger = logging.getLogger(__name__)


class TriageService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.incident_service = IncidentService(db)
        self.context_service = ContextService(db)
        self.assignment_service = AssignmentService(db)
        self.llm = LLMService()
        self.agent = TriageAgent()

    async def _resolve_assignment_group(self, incident_id: str) -> tuple[str | None, bool]:
        """
        Returns (assignment_group, llm_was_used).

        Step 1: If group is already a specific (non-common-queue) group, use it as-is.
        Step 2: Otherwise use LLM to resolve from the full ASSIGNMENT_GROUPS list.
                Always uses the hardcoded list so resolution works even before any
                roster is uploaded. The DB group list is only used to enrich if available.
        Step 3: Persist the resolved group onto the incident immediately.
        """
        incident = await self.incident_service.get_incident(incident_id)

        if incident.assignment_group and not is_common_queue(incident.assignment_group):
            logger.info(f"Assignment group already set to specific group: '{incident.assignment_group}'")
            return incident.assignment_group, False

        logger.info(
            f"Resolving group for {incident.incident_number} via LLM "
            f"(current: '{incident.assignment_group}')"
        )

        # Always resolve from the hardcoded ASSIGNMENT_GROUPS list only
        # No DB dependency — roster upload state does not affect group resolution
        available_groups = ASSIGNMENT_GROUPS
        logger.info(f"Available groups for LLM resolution: {available_groups}")

        messages = build_assignment_group_messages(
            short_description=incident.short_description,
            description=incident.description,
            work_notes=incident.work_notes,
            available_groups=available_groups,
        )

        try:
            raw = await self.llm.complete(messages=messages)
            resolved = raw.strip().strip(".,!? \"'")
            logger.info(f"LLM raw response: '{raw}' → stripped: '{resolved}'")

            # Case-insensitive match
            groups_lower = {g.lower(): g for g in available_groups}
            canonical = groups_lower.get(resolved.lower())

            if resolved.upper() == "UNKNOWN" or not canonical:
                logger.warning(f"LLM returned unrecognized group: '{resolved}'")
                return None, True

            resolved = canonical
            logger.info(f"LLM resolved group: '{resolved}' for {incident.incident_number}")

            # Persist resolved group immediately — independent of engineer availability
            await self.incident_service.update_incident(
                incident_id,
                IncidentUpdate(
                    assignment_group=resolved,
                    work_notes=f"[Triage] Assignment group resolved by AI: {resolved}",
                ),
            )
            return resolved, True

        except Exception as e:
            logger.error(f"LLM group resolution failed: {e}")
            return None, True

    async def run_triage(
        self,
        incident_id: str,
        context_date: date | None = None,
        apply_recommendation: bool = True,
        force: bool = False,
    ) -> AgentResponse:
        """
        Full triage flow.
        By default only runs for incidents with no assigned_to.
        Pass force=True to re-assign even if an engineer is already set.
        """
        if context_date is None:
            context_date = datetime.now(timezone.utc).date()

        # Guard: only triage new or in_progress incidents
        incident = await self.incident_service.get_incident(incident_id)
        if incident.state not in ("new", "in_progress"):
            return AgentResponse(
                success=False,
                agent_name="TriageAgent",
                reasoning=f"Incident is in state '{incident.state}' — triage only runs for new or in_progress incidents",
                errors=[f"Invalid state for triage: {incident.state}"],
            )
        if incident.assigned_to and not force:
            return AgentResponse(
                success=False,
                agent_name="TriageAgent",
                reasoning=f"Incident already assigned to '{incident.assigned_to}' — skipping triage",
                errors=["Incident already has an assigned engineer"],
            )

        # Step 1: Resolve assignment group
        group, llm_used = await self._resolve_assignment_group(incident_id)

        if not group:
            return AgentResponse(
                success=False,
                agent_name="TriageAgent",
                reasoning="Could not determine a specific assignment group from the incident description. Please set the assignment group manually.",
                errors=["Assignment group could not be resolved by AI"],
            )

        # Step 2: Build AIContext — may have zero engineers if roster not uploaded
        try:
            context = await self.context_service.build_for_incident(
                incident_id=incident_id,
                context_date=context_date,
            )
        except Exception as e:
            # Group was resolved and saved, but no engineers in roster for this group/date
            logger.warning(f"[TriageService] Context build failed for {incident_id}: {e}")
            # Clear assigned_to so UI shows empty, not a stale old value
            await self.incident_service.update_incident(
                incident_id,
                IncidentUpdate(assigned_to=None),
            )
            return AgentResponse(
                success=False,
                agent_name="TriageAgent",
                reasoning=(
                    f"Assignment group resolved to '{group}' but no engineers are available "
                    f"in the shift roster for {context_date}. "
                    f"Please upload a shift roster for '{group}'."
                ),
                errors=[f"No engineers found in '{group}' for {context_date}"],
            )

        # Step 3: Run TriageAgent (confirms group, counts availability)
        if not context.engineers:
            # Clear assigned_to so UI shows empty, not a stale old value
            await self.incident_service.update_incident(
                incident_id,
                IncidentUpdate(assigned_to=None),
            )
            return AgentResponse(
                success=False,
                agent_name="TriageAgent",
                reasoning=(
                    f"Assignment group resolved to '{group}' but no engineers are available "
                    f"on {context_date}. Please upload a shift roster for '{group}'."
                ),
                errors=[f"No engineers available in '{group}' on {context_date}"],
            )
        request = AgentRequest(context=context)
        agent_response = await self.agent.run(request)

        if not agent_response.success:
            return agent_response

        # Step 4: AssignmentService selects engineer via round-robin
        incident = await self.incident_service.get_incident(incident_id)

        assignment = await self.assignment_service.assign_engineer(
            incident_id=incident.id,
            incident_number=incident.incident_number,
            assignment_group=group,
            engineers=context.engineers,
            roster_date_str=str(context_date),
            llm_resolved_group=llm_used,
        )

        if not assignment.success:
            # Clear assigned_to — no engineer available, don't show stale value
            await self.incident_service.update_incident(
                incident_id,
                IncidentUpdate(assigned_to=None),
            )
            agent_response.success = False
            agent_response.errors.append(NO_AVAILABLE_ENGINEER)
            agent_response.reasoning = (
                f"No available engineers in '{group}' on {context_date}. "
                f"All engineers are on WO/PL/CH/RH."
            )
            logger.warning(
                f"[TriageService] {incident.incident_number}: {NO_AVAILABLE_ENGINEER} "
                f"in group '{group}' on {context_date}"
            )
            return agent_response

        # Step 5: Update incident via IncidentService
        if apply_recommendation:
            eng = assignment.engineer
            await self.incident_service.update_incident(
                incident.id,
                IncidentUpdate(
                    assigned_to=eng.name,
                    state="in_progress",                    work_notes=(
                        f"[Triage Agent] Assigned to {eng.name} "
                        f"(shift={eng.current_shift}, active_now={eng.is_shift_active}, "
                        f"group={group}). "
                        f"{'Group resolved by LLM. ' if llm_used else ''}"
                        f"{assignment.reason}"
                    ),
                ),
            )
            logger.info(
                f"[TriageService] {incident.incident_number} assigned to "
                f"{eng.name} (group={group}, shift={eng.current_shift})"
            )

        # Build final response
        triage_result = TriageResult(**agent_response.result)
        eng = assignment.engineer
        agent_response.reasoning = assignment.reason
        agent_response.result = {
            **triage_result.model_dump(),
            "assigned_engineer": {
                "name": eng.name,
                "email": eng.email,
                "shift": eng.current_shift,
                "is_shift_active": eng.is_shift_active,
                "group": group,
                "fallback_used": assignment.fallback_used,
            },
            "llm_resolved_group": llm_used,
        }

        return agent_response
