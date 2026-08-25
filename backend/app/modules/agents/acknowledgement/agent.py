"""
Acknowledgement Agent implementation.

Responsibility:
  1. Check if assignment_group is a Salesforce/SFDC group.
  2. If non-Salesforce group: Always send simple standard acknowledgement template (standard_ack.html).
  3. If Salesforce group: Pass full ticket context (group, category, subcategory, descriptions) to LLM to evaluate intent and select template.
"""
import logging
from app.modules.agents.base.base_agent import BaseAgent
from app.modules.agents.base.response import AgentResponse
from app.modules.context.schemas import AIContext
from app.modules.agents.acknowledgement.schemas import IntentResult, IntentType
from app.modules.agents.acknowledgement.intent_classifier import IntentClassifier

logger = logging.getLogger(__name__)

SALESFORCE_GROUPS = ["salesforce", "sfdc", "hcl apps run-sfdc", "salesforce support"]


def is_salesforce_group(group_name: str | None) -> bool:
    if not group_name:
        return False
    clean_name = group_name.lower()
    return any(g in clean_name for g in SALESFORCE_GROUPS)


class AcknowledgementAgent(BaseAgent):
    def __init__(self):
        self.intent_classifier = IntentClassifier()

    @property
    def agent_name(self) -> str:
        return "AcknowledgementAgent"

    async def reason(self, context: AIContext) -> AgentResponse:
        incident = context.incident
        group_name = incident.assignment_group

        # Check if assignment group is Salesforce
        if not is_salesforce_group(group_name):
            logger.info(f"[AcknowledgementAgent] Non-Salesforce group '{group_name}'. Sending simple standard template.")
            intent_info = IntentResult(
                intent=IntentType.STANDARD_INCIDENT,
                confidence=1.0,
                reasoning="Non-Salesforce assignment group — sending simple standard acknowledgement template.",
            )
            template_name = "standard_ack.html"
            reasoning_msg = f"Non-Salesforce assignment group '{group_name}'. Selected simple standard template '{template_name}'."
        else:
            # Salesforce group — classify intent using full ticket context
            intent_info = await self.intent_classifier.classify_intent(
                short_description=incident.short_description,
                description=incident.description,
                assignment_group=incident.assignment_group,
                category=incident.category,
                subcategory=incident.subcategory,
            )

            template_mapping = {
                IntentType.SALESFORCE_INCORRECT_REQUEST: "salesforce_incorrect_request.html",
                IntentType.STANDARD_INCIDENT: "standard_ack.html",
                IntentType.ACCESS_REQUEST: "wrong_ticket_access.html",
                IntentType.SERVICE_REQUEST: "wrong_ticket_service_catalog.html",
                IntentType.WRONG_REQUEST: "wrong_org_environment.html",
            }
            template_name = template_mapping.get(intent_info.intent, "standard_ack.html")
            reasoning_msg = f"Classified Salesforce intent as '{intent_info.intent.value}' (confidence: {intent_info.confidence:.2f}). Selected template '{template_name}'."

        result_data = {
            "incident_id": incident.incident_id,
            "incident_number": incident.incident_number,
            "caller": incident.caller or "Valued Employee",
            "assigned_to": incident.assigned_to,
            "assignment_group": incident.assignment_group,
            "intent_info": intent_info.model_dump(),
            "template_used": template_name,
            "reasoning": reasoning_msg,
        }

        return AgentResponse(
            success=True,
            agent_name=self.agent_name,
            reasoning=reasoning_msg,
            confidence=intent_info.confidence,
            result=result_data,
        )
