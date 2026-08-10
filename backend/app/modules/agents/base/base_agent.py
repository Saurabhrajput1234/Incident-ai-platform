"""
Base Agent — reusable foundation for all AI agents.

Every agent (Triage, Acknowledgement, Pending, Resolution) inherits from BaseAgent.
The lifecycle is:
  1. receive(request)  → validate context
  2. reason(context)   → agent-specific logic (implemented by subclass)
  3. return response

Rules:
  - BaseAgent never queries the database
  - BaseAgent never calls repositories
  - BaseAgent never updates incidents
  - Only reasoning and response formatting belong here
"""
import logging
from abc import ABC, abstractmethod

from app.modules.agents.base.request import AgentRequest
from app.modules.agents.base.response import AgentResponse
from app.modules.agents.base.exceptions import ContextValidationError, AgentReasoningError
from app.modules.context.schemas import AIContext

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all AI agents.
    Subclasses must implement: agent_name and reason().
    """

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Unique name of this agent."""
        ...

    @abstractmethod
    async def reason(self, context: AIContext) -> AgentResponse:
        """
        Core reasoning logic — implemented by each agent.
        Receives only the AIContext. Must never touch DB or services.
        """
        ...

    def validate_context(self, context: AIContext) -> None:
        """
        Validate the context before reasoning.
        Override in subclasses to add agent-specific validation.
        """
        if not context:
            raise ContextValidationError("Context is required")
        if not context.incident:
            raise ContextValidationError("Incident is missing from context")

    async def run(self, request: AgentRequest) -> AgentResponse:
        """
        Main entry point. Validates context then calls reason().
        Catches and wraps all errors into AgentResponse.
        """
        logger.info(f"[{self.agent_name}] Starting — incident: {request.context.incident.incident_number}")

        try:
            self.validate_context(request.context)
            response = await self.reason(request.context)
            logger.info(f"[{self.agent_name}] Completed — success: {response.success}")
            return response

        except ContextValidationError as e:
            logger.warning(f"[{self.agent_name}] Context validation failed: {e}")
            return AgentResponse(
                success=False,
                agent_name=self.agent_name,
                errors=[str(e)],
            )
        except AgentReasoningError as e:
            logger.error(f"[{self.agent_name}] Reasoning error: {e}")
            return AgentResponse(
                success=False,
                agent_name=self.agent_name,
                errors=[str(e)],
            )
        except Exception as e:
            logger.error(f"[{self.agent_name}] Unexpected error: {e}")
            return AgentResponse(
                success=False,
                agent_name=self.agent_name,
                errors=[f"Unexpected error: {str(e)}"],
            )
