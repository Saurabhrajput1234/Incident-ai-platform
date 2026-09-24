"""
In-process async event bus.

- Handlers registered per event type.
- All handlers for one event are fired as background asyncio tasks.
- The caller returns immediately — handlers run concurrently without blocking.
- One handler failing does NOT block the others.
- No external infrastructure required.
"""
import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable) -> None:
        self._handlers[event_type].append(handler)
        logger.debug("[EventBus] Subscribed %s → %s", event_type.__name__, handler.__qualname__)

    async def publish(self, event: Any) -> None:
        handlers = self._handlers.get(type(event), [])
        if not handlers:
            logger.debug("[EventBus] No handlers for %s", type(event).__name__)
            return

        logger.info("[EventBus] Publishing %s to %d handler(s) (fire-and-forget)", type(event).__name__, len(handlers))

        # Fire each handler as a background task so the caller returns immediately.
        # This ensures the API response is not blocked by agent execution.
        for handler in handlers:
            asyncio.ensure_future(_run_handler(handler, event))


async def _run_handler(handler: Callable, event: Any) -> None:
    """Run a single handler and log any exceptions."""
    try:
        await handler(event)
    except Exception as exc:
        logger.error(
            "[EventBus] Handler %s failed for %s: %s",
            handler.__qualname__, type(event).__name__, exc,
            exc_info=True,
        )


# Singleton — imported everywhere
event_bus = EventBus()
