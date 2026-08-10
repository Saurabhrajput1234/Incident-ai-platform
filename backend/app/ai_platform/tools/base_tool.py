"""
Base Tool — reusable foundation for all AI tools.

Every tool (IncidentTool, ShiftRosterTool, etc.) inherits from BaseTool.
Tools act as the abstraction layer between AI agents and business services.

Rules:
  - Agents call tools, never services or repositories directly
  - Tools call services only, never repositories
  - Tools validate input and return standardized output
"""
import logging
from abc import ABC, abstractmethod
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ToolResult(BaseModel):
    """Standardized output returned by every tool."""
    success: bool
    tool_name: str
    data: dict = {}
    error: str | None = None


class BaseTool(ABC):
    """Abstract base class for all AI tools."""

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Unique name of this tool."""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool action. Implemented by each subclass."""
        ...

    async def run(self, **kwargs) -> ToolResult:
        """
        Entry point with error handling.
        Wraps execute() and catches all exceptions into ToolResult.
        """
        logger.info(f"[{self.tool_name}] Running with params: {list(kwargs.keys())}")
        try:
            result = await self.execute(**kwargs)
            return result
        except Exception as e:
            logger.error(f"[{self.tool_name}] Error: {e}")
            return ToolResult(
                success=False,
                tool_name=self.tool_name,
                error=str(e),
            )
