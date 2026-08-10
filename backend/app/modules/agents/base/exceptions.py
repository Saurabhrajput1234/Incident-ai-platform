"""Exceptions for the agent framework."""
from app.common.exceptions.base import BadRequestError


class AgentError(Exception):
    """Base exception for all agent errors."""
    pass


class ContextValidationError(AgentError):
    """Raised when the agent receives an invalid or incomplete context."""
    pass


class AgentReasoningError(AgentError):
    """Raised when the agent fails during reasoning."""
    pass
