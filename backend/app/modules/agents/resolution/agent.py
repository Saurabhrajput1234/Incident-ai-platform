"""
Resolution Agent — pure reasoning layer.

Responsibilities
~~~~~~~~~~~~~~~~
* Receive an AIContext with injected metadata.
* Call the LLM to classify the user's latest response intent.
* Return a structured AgentResponse containing LLMAnalysis.

Rules (inherited from BaseAgent contract)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* MUST NOT access the database.
* MUST NOT call repositories.
* MUST NOT update incidents.
* MUST NOT send notifications.
* All of those responsibilities belong to ResolutionService.
"""
from __future__ import annotations

import json
import logging

from app.ai_platform.services.llm_service import LLMService
from app.modules.agents.base.base_agent import BaseAgent
from app.modules.agents.base.response import AgentResponse
from app.modules.agents.resolution.prompts import SYSTEM_PROMPT, build_user_prompt
from app.modules.agents.resolution.schemas import LLMAnalysis, ResolutionIntent, RESOLUTION_POSITIVE_INTENTS
from app.modules.context.schemas import AIContext

logger = logging.getLogger(__name__)


class ResolutionAgent(BaseAgent):
    """
    Classifies a user's response to an incident that transitioned ON_HOLD → ACTIVE.

    The agent uses the LLM to produce:
        - intent                (ResolutionIntent enum value)
        - positive_resolution   (bool — derived from intent)
        - confidence            (float)
        - summary               (str)
        - next_best_action      (str)

    These are returned inside AgentResponse.result["llm_analysis"].
    The caller (ResolutionService) is responsible for acting on the result.
    """

    def __init__(self) -> None:
        self._llm = LLMService()

    @property
    def agent_name(self) -> str:
        return "ResolutionAgent"

    async def reason(self, context: AIContext) -> AgentResponse:
        """
        Analyse the incident context and return structured LLM output.

        The service layer injects metadata via object.__setattr__:
            _user_response_text      : the triggering USER work note message
            _acknowledgement_context : summary of what was requested from user
            _pending_reminder_count  : how many reminders were sent
        """
        incident = context.incident

        user_response = getattr(context, "_user_response_text", None)
        if not user_response:
            user_response = incident.description or incident.short_description

        acknowledgement_context = getattr(context, "_acknowledgement_context", None)
        pending_reminder_count = getattr(context, "_pending_reminder_count", None)

        user_prompt = build_user_prompt(
            incident_number=incident.incident_number,
            short_description=incident.short_description,
            user_response=user_response,
            assigned_to=incident.assigned_to,
            assignment_group=incident.assignment_group,
            acknowledgement_context=acknowledgement_context,
            pending_reminder_count=pending_reminder_count,
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ]

        try:
            raw = await self._llm.complete(messages=messages)
            analysis = self._parse_llm_response(raw)
        except Exception as exc:
            logger.error("[ResolutionAgent] LLM call failed: %s", exc)
            return AgentResponse(
                success=False,
                agent_name=self.agent_name,
                errors=[f"LLM analysis failed: {exc}"],
                result={"llm_failed": True, "llm_error": str(exc)},
            )

        return AgentResponse(
            success=True,
            agent_name=self.agent_name,
            reasoning=analysis.summary,
            confidence=analysis.confidence,
            result={"llm_analysis": analysis.model_dump()},
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_llm_response(self, raw: str) -> LLMAnalysis:
        """
        Parse and validate LLM JSON output.

        On any parse / validation error falls back to a safe
        UNCLEAR non-positive result rather than propagating the exception.
        """
        clean = raw.strip()

        # Strip markdown code fences if present
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()

        try:
            parsed = json.loads(clean)
        except json.JSONDecodeError as exc:
            logger.warning("[ResolutionAgent] JSON parse failed: %s | raw=%r", exc, raw[:200])
            return LLMAnalysis(
                intent=ResolutionIntent.UNCLEAR,
                positive_resolution=False,
                confidence=0.0,
                summary="Unable to parse LLM response.",
                next_best_action="Manual engineer review required.",
            )

        try:
            # Parse intent — default to UNCLEAR on unknown value
            raw_intent = str(parsed.get("intent", "UNCLEAR")).upper()
            try:
                intent = ResolutionIntent(raw_intent)
            except ValueError:
                logger.warning(
                    "[ResolutionAgent] Unknown intent value %r — defaulting to UNCLEAR",
                    raw_intent,
                )
                intent = ResolutionIntent.UNCLEAR

            # Derive positive_resolution from intent (authoritative source)
            positive_resolution = intent in RESOLUTION_POSITIVE_INTENTS

            return LLMAnalysis(
                intent=intent,
                positive_resolution=positive_resolution,
                confidence=float(parsed.get("confidence", 0.0)),
                summary=str(parsed.get("summary", "No summary available.")),
                next_best_action=str(parsed.get("next_best_action", "No recommendation available.")),
            )
        except Exception as exc:
            logger.warning("[ResolutionAgent] LLMAnalysis construction failed: %s", exc)
            return LLMAnalysis(
                intent=ResolutionIntent.UNCLEAR,
                positive_resolution=False,
                confidence=0.0,
                summary="Unable to validate LLM output.",
                next_best_action="Manual engineer review required.",
            )
