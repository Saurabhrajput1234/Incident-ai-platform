"""
Pure LLM Ticket Intent Classifier.

All classification is prompted dynamically through LLM (openai/gpt-oss-120b).
Includes full ticket metadata (Assignment Group, Category, Subcategory, Description).
"""
import logging
import json
from app.ai_platform.services.llm_service import LLMService
from app.modules.agents.acknowledgement.schemas import IntentResult, IntentType

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert IT Support Intent Classifier for Salesforce Assignment Groups.
Analyze the full incoming IT incident context (Assignment Group, Category, Subcategory, Short Description, Description) and classify it into EXACTLY ONE of the following categories:

1. SALESFORCE_INCORRECT_REQUEST: The user is requesting Salesforce access, profile updates, role permissions, module mapping access, or is unable to download/access Salesforce.com GTS (EANZ) & GEM apps/modules via an Incident ticket form instead of an Application Access Request (RITM).
2. WRONG_REQUEST: The ticket is submitted under an incorrect assignment group, wrong org (e.g. EMEA org sandbox, staging), or wrong system environment.
3. ACCESS_REQUEST: General non-Salesforce system permission, SAP role, or DB access authorization request.
4. SERVICE_REQUEST: Hardware order, software license installation, or service catalog item request.
5. STANDARD_INCIDENT: Standard technical break/fix issue, system outage, blue screen crash, or infrastructure disruption requiring engineer manual investigation.

Respond ONLY with a valid JSON object in this format:
{
  "intent": "SALESFORCE_INCORRECT_REQUEST" | "WRONG_REQUEST" | "ACCESS_REQUEST" | "SERVICE_REQUEST" | "STANDARD_INCIDENT",
  "confidence": 0.95,
  "reasoning": "Clear 1-sentence technical explanation of why this category was selected based on ticket context"
}
"""


class IntentClassifier:
    def __init__(self):
        self.llm = LLMService()

    async def classify_intent(
        self,
        short_description: str,
        description: str | None = None,
        assignment_group: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
    ) -> IntentResult:
        """
        Classifies ticket intent purely via LLM prompt evaluation using full ticket context.
        """
        logger.info(f"[IntentClassifier] Executing LLM intent classification for: '{short_description}' (Group: '{assignment_group}', Category: '{category}')")
        
        user_prompt = (
            f"Assignment Group: {assignment_group or 'None'}\n"
            f"Category: {category or 'None'}\n"
            f"Subcategory: {subcategory or 'None'}\n"
            f"Short Description: {short_description}\n"
            f"Description: {description or 'None'}"
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            raw_response = await self.llm.complete(messages=messages)
            clean_json = raw_response.strip()
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()

            parsed = json.loads(clean_json)
            intent_val = parsed.get("intent", "STANDARD_INCIDENT")

            if intent_val in IntentType.__members__:
                intent_enum = IntentType(intent_val)
            else:
                intent_enum = IntentType.STANDARD_INCIDENT

            return IntentResult(
                intent=intent_enum,
                confidence=float(parsed.get("confidence", 0.95)),
                reasoning=parsed.get("reasoning", "Classified dynamically by LLM prompt evaluation"),
            )
        except Exception as e:
            logger.warning(f"[IntentClassifier] LLM classification error: {e}. Defaulting to STANDARD_INCIDENT")
            return IntentResult(
                intent=IntentType.STANDARD_INCIDENT,
                confidence=0.80,
                reasoning=f"Default standard incident fallback due to error: {str(e)}",
            )
