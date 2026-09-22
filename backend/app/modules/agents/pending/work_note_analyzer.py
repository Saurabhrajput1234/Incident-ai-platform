"""
Work Note Analyzer for Pending Agent.
Uses Groq LLM to analyze the recent work notes (latest note and the note below it)
to determine if caller/user action or clarification is requested.
"""
import json
import logging
from app.ai_platform.services.llm_service import LLMService
from app.modules.agents.pending.schemas import PendingWorkNoteAnalysis

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert IT Service Management (ITSM) classifier for ServiceNow incidents.

An engineer has added a work note to an incident and then placed it in ON HOLD / PENDING status.
Your job is to read the engineer's work note and determine whether the CALLER (the end user who raised the ticket) needs to take any action to move this ticket forward.

CALLER action IS required when the engineer's note explicitly asks the caller to:
- Provide information, screenshots, logs, or error details
- Confirm whether an issue is resolved or still occurring
- Perform a specific action (e.g. re-login, test something, reboot)
- Provide credentials, employee IDs, or personal details

CALLER action is NOT required when the engineer is:
- Waiting for internal approval from another team, authority, or manager
- Forwarding or escalating the ticket to another engineer or team
- Waiting for a change window, maintenance, or internal process
- Performing internal investigation or checks themselves
- Waiting for a vendor, third party, or backend system

Return ONLY valid JSON:
{
  "is_caller_action_required": true or false,
  "reasoning": "One sentence explaining what is being waited for and why caller action is or is not required.",
  "confidence": float between 0.0 and 1.0
}

Be strict: only set is_caller_action_required=true when the caller themselves must do something.
Internal waits, approvals, and escalations must return false.
Output only raw JSON without Markdown fences.
"""


class PendingWorkNoteAnalyzer:
    def __init__(self):
        self.llm = LLMService()

    async def analyze(
        self,
        latest_work_note: str,
        source_name: str,
        incident_context: str | None = None,
    ) -> PendingWorkNoteAnalysis:
        """
        Analyzes the recent work notes to determine if a pending reminder should be started.
        """
        # Fast path: Acknowledgement Agent already requested user redirection
        if "AcknowledgementAgent" in source_name or "Acknowledgement Agent" in latest_work_note:
            return PendingWorkNoteAnalysis(
                is_caller_action_required=True,
                reasoning="Application Access Request RITM submission required via IT Central.",
                confidence=1.0,
            )

        user_content = f"RECENT WORK NOTES (LATEST & BELOW IT):\nAuthor / Source: {source_name}\n\n{latest_work_note}"
        if incident_context:
            user_content = f"INCIDENT CONTEXT:\n{incident_context}\n\n{user_content}"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        logger.info(f"[WorkNoteAnalyzer] === SENDING TO GROQ LLM ===\n{user_content}\n=============================")
        try:
            raw_response = await self.llm.complete(messages=messages)
            logger.info(f"[WorkNoteAnalyzer] === GROQ LLM RESPONSE ===\n{raw_response}\n=============================")
            cleaned = raw_response.strip().strip("`").replace("json\n", "").replace("json", "").strip()
            data = json.loads(cleaned)
            return PendingWorkNoteAnalysis(
                is_caller_action_required=bool(data.get("is_caller_action_required", True)),
                reasoning=data.get("reasoning", "Awaiting caller response to proceed with troubleshooting."),
                confidence=float(data.get("confidence", 0.9)),
            )
        except Exception as e:
            logger.warning(f"[PendingWorkNoteAnalyzer] LLM analysis failed: {e}. Falling back to default.")
            # Default to True so a pending ticket awaiting info gets reminder
            return PendingWorkNoteAnalysis(
                is_caller_action_required=True,
                reasoning="Awaiting caller response and clarification to continue investigation.",
                confidence=0.8,
            )
