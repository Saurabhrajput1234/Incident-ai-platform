"""
Triage Service — orchestrates the full triage flow.

Flow:
  1. LLM resolves assignment group (if common queue or missing)
  2. Build AIContext (incident + engineers for that group + date)
  3. TriageAgent confirms group and counts availability
  4. AssignmentService picks engineer via persistent round-robin
  5. IncidentService updates incident with assigned engineer
  6. WorkNoteService records structured work notes for every action
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
from app.modules.work_notes.service import WorkNoteService
from app.modules.work_notes.enums import WorkNoteSourceType, WorkNoteActionType

logger = logging.getLogger(__name__)


class TriageService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.incident_service = IncidentService(db)
        self.context_service = ContextService(db)
        self.assignment_service = AssignmentService(db)
        self.work_note_svc = WorkNoteService(db)
        self.llm = LLMService()
        self.agent = TriageAgent()

    async def _resolve_assignment_group(self, incident_id: str) -> tuple[str | None, bool]:
        """
        Returns (assignment_group, llm_was_used).
        If group is already specific (non-common-queue), use it directly.
        Otherwise use LLM to pick from ASSIGNMENT_GROUPS hardcoded list.
        Persists the resolved group and records a work note.
        """
        incident = await self.incident_service.get_incident(incident_id)

        if incident.assignment_group and not is_common_queue(incident.assignment_group):
            logger.info(f"Assignment group already set: '{incident.assignment_group}'")
            return incident.assignment_group, False

        logger.info(
            f"Resolving group for {incident.incident_number} via LLM "
            f"(current: '{incident.assignment_group}')"
        )

        available_groups = ASSIGNMENT_GROUPS
        messages = build_assignment_group_messages(
            short_description=incident.short_description,
            description=incident.description,
            work_notes=None,  # don't pass old flat notes to LLM
            available_groups=available_groups,
        )

        try:
            raw = await self.llm.complete(messages=messages)
            resolved = raw.strip().strip(".,!? \"'")
            logger.info(f"LLM raw response: '{raw}' → stripped: '{resolved}'")

            groups_lower = {g.lower(): g for g in available_groups}
            canonical = groups_lower.get(resolved.lower())

            if resolved.upper() == "UNKNOWN" or not canonical:
                logger.warning(f"LLM returned unrecognized group: '{resolved}'")
                return None, True

            resolved = canonical
            logger.info(f"LLM resolved group: '{resolved}' for {incident.incident_number}")

            # Persist resolved group
            await self.incident_service.update_incident_internal(
                incident_id,
                IncidentUpdate(assignment_group=resolved),
            )

            # Structured work note
            # auto_activate=False: triage already set state via update_incident_internal;
            # this note is a record of the group resolution, not a user communication.
            await self.work_note_svc.add_note(
                incident_id=incident_id,
                message=f"Assignment group resolved by AI to: {resolved}",
                source_type=WorkNoteSourceType.TRIAGE_AGENT,
                source_name="TriageAgent",
                action_type=WorkNoteActionType.GROUP_RESOLVED,
                auto_activate=False,
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
        auto_acknowledge: bool = True,
    ) -> AgentResponse:
        """
        Full triage flow.
        Pass force=True to re-assign even if an engineer is already set.
        """
        if context_date is None:
            context_date = datetime.now(timezone.utc).date()

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

        # Step 2: Build AIContext
        try:
            context = await self.context_service.build_for_incident(
                incident_id=incident_id,
                context_date=context_date,
            )
        except Exception as e:
            logger.warning(f"[TriageService] Context build failed for {incident_id}: {e}")
            await self.incident_service.update_incident_internal(incident_id, IncidentUpdate(assigned_to=None))
            await self.work_note_svc.add_note(
                incident_id=incident_id,
                message=f"Triage failed: assignment group resolved to '{group}' but no shift roster found for {context_date}. Please upload a shift roster for '{group}'.",
                source_type=WorkNoteSourceType.TRIAGE_AGENT,
                source_name="TriageAgent",
                action_type=WorkNoteActionType.SYSTEM_NOTE,
                auto_activate=False,  # failure audit note — no state activation
            )
            return AgentResponse(
                success=False,
                agent_name="TriageAgent",
                reasoning=f"Assignment group resolved to '{group}' but no engineers are available in the shift roster for {context_date}.",
                errors=[f"No engineers found in '{group}' for {context_date}"],
            )

        # Step 3: TriageAgent validation
        if not context.engineers:
            await self.incident_service.update_incident_internal(incident_id, IncidentUpdate(assigned_to=None))
            await self.work_note_svc.add_note(
                incident_id=incident_id,
                message=f"Triage failed: no engineers available in '{group}' on {context_date}. Please upload a shift roster for this group.",
                source_type=WorkNoteSourceType.TRIAGE_AGENT,
                source_name="TriageAgent",
                action_type=WorkNoteActionType.SYSTEM_NOTE,
                auto_activate=False,  # failure audit note — no state activation
            )
            return AgentResponse(
                success=False,
                agent_name="TriageAgent",
                reasoning=f"Assignment group resolved to '{group}' but no engineers are available on {context_date}.",
                errors=[f"No engineers available in '{group}' on {context_date}"],
            )

        request = AgentRequest(context=context)
        agent_response = await self.agent.run(request)
        if not agent_response.success:
            return agent_response

        # Step 4: Round-robin assignment
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
            await self.incident_service.update_incident_internal(incident_id, IncidentUpdate(assigned_to=None))
            await self.work_note_svc.add_note(
                incident_id=incident_id,
                message=f"No available engineers in '{group}' on {context_date}. All engineers are on WO/PL/CH/RH.",
                source_type=WorkNoteSourceType.TRIAGE_AGENT,
                source_name="TriageAgent",
                action_type=WorkNoteActionType.SYSTEM_NOTE,
                auto_activate=False,  # assignment failure — no activation
            )
            agent_response.success = False
            agent_response.errors.append(NO_AVAILABLE_ENGINEER)
            agent_response.reasoning = f"No available engineers in '{group}' on {context_date}. All engineers are on WO/PL/CH/RH."
            return agent_response

        # Step 5: Update incident + structured work note
        ack_data = None
        if apply_recommendation:
            eng = assignment.engineer
            await self.incident_service.update_incident_internal(
                incident.id,
                IncidentUpdate(assigned_to=eng.name, state="in_progress"),
            )

            await self.work_note_svc.add_note(
                incident_id=incident.id,
                message=(
                    f"Assigned to {eng.name} "
                    f"(shift={eng.current_shift}, active_now={eng.is_shift_active}, group={group}). "
                    f"{'Group resolved by LLM. ' if llm_used else ''}"
                    f"{assignment.reason}"
                ),
                source_type=WorkNoteSourceType.TRIAGE_AGENT,
                source_name="TriageAgent",
                source_id=eng.engineer_id,
                action_type=WorkNoteActionType.ASSIGN_ENGINEER,
                auto_activate=False,  # state already set to in_progress by update_incident_internal above
            )

            logger.info(f"[TriageService] {incident.incident_number} assigned to {eng.name}")

            if auto_acknowledge:
                try:
                    from app.modules.agents.acknowledgement.service import AcknowledgementService
                    ack_service = AcknowledgementService(self.db)
                    ack_resp = await ack_service.process_acknowledgement(incident.id)
                    if ack_resp.success:
                        ack_data = ack_resp.result
                        logger.info(f"[TriageService] Auto-acknowledgement succeeded for {incident.incident_number}")
                except Exception as e:
                    logger.error(f"[TriageService] Auto-acknowledgement failed: {e}")

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
            "acknowledgement": ack_data,
        }

        return agent_response
