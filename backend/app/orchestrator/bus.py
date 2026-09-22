"""
In-process async event bus.

- Handlers registered per event type.
- All handlers for one event run concurrently (asyncio.gather).
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

        logger.info("[EventBus] Publishing %s to %d handler(s)", type(event).__name__, len(handlers))
        results = await asyncio.gather(
            *[handler(event) for handler in handlers],
            return_exceptions=True,
        )
        for handler, result in zip(handlers, results):
            if isinstance(result, Exception):
                logger.error(
                    "[EventBus] Handler %s failed for %s: %s",
                    handler.__qualname__, type(event).__name__, result,
                    exc_info=result,
                )


# Singleton — imported everywhere
event_bus = EventBus()
