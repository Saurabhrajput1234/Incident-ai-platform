"""Exceptions specific to the Context Builder."""
from app.common.exceptions.base import BadRequestError


class ContextBuildError(BadRequestError):
    """Raised when the context builder cannot assemble a complete context."""
    def __init__(self, detail: str = "Failed to build AI context"):
        super().__init__(detail=detail)
