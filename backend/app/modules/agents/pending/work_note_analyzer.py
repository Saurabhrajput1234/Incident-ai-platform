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
Your job is to analyze the recent work notes (the latest work note and the previous note below it, plus any recent context notes) added to an incident and determine what information, clarification, error screenshots, or action is needed from the CALLER (the end user).

The incident has been placed in ON HOLD / PENDING status, which means work is paused awaiting information or action from the caller.

Return ONLY valid JSON matching this exact structure:
{
  "is_caller_action_required": true,
  "reasoning": "A concise summary of what is awaited from the caller (e.g., 'Error screenshot of GTS EANZ', 'Manager approval email and employee ID', 'Confirmation if issue persists after reboot', or 'Awaiting caller confirmation regarding [issue] to proceed').",
  "confidence": float between 0.0 and 1.0
}

Key Guidelines:
- Inspect BOTH notes provided (the latest work note and the previous note below it) along with any context note and incident description.
- When an incident is placed in on_hold/pending, always identify what is awaited from the caller so a clear reminder can be sent.
- If an engineer note or prior note explicitly asks for details (screenshots, approvals, employee ID, confirmation), summarize that exact request in 'reasoning'.
- If the latest notes are system state changes (e.g. 'State changed to: on_hold'), use the incident description and prior context to summarize what confirmation or input is needed from the user.
- Always set is_caller_action_required: true for tickets in on_hold/pending status.
- Output only raw JSON without Markdown fences or extra commentary.
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
