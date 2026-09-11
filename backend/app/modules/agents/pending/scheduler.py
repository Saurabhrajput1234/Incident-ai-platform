"""
Background reminder scheduler for Pending Agent.

Periodically polls for active pending cycles whose next_reminder_at is due
and triggers the next reminder tier via PendingService.
"""
import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.modules.pending_cycles.repository import PendingCycleRepository
from app.modules.agents.pending.service import PendingService

logger = logging.getLogger(__name__)


async def start_pending_reminder_scheduler(poll_interval_seconds: int = 20) -> None:
    """
    Infinite background loop that runs during the app lifespan.
    Checks for due reminders every poll_interval_seconds.
    Uses the canonical PendingCycleRepository for the due-cycle query.
    """
    logger.info(
        "[PendingScheduler] Background reminder scheduler started "
        "(polling every %ds)", poll_interval_seconds
    )
    engine = create_async_engine(settings.DATABASE_URL, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        while True:
            try:
                async with session_factory() as db:
                    repo = PendingCycleRepository(db)
                    due_cycles = await repo.get_due_active_cycles()
                    for cycle in due_cycles:
                        target_tier = cycle.reminder_count + 1
                        logger.info(
                            "[PendingScheduler] Cycle %s for incident %s "
                            "is due for Reminder %d/%d. Triggering...",
                            cycle.id, cycle.incident_id,
                            target_tier, cycle.max_reminders,
                        )
                        service = PendingService(db)
                        await service.process_pending_transition(
                            incident_id=cycle.incident_id,
                            force_reminder=True,
                        )
            except asyncio.CancelledError:
                logger.info("[PendingScheduler] Scheduler task cancelled.")
                break
            except Exception as exc:
                logger.error(
                    "[PendingScheduler] Error in reminder scheduler loop: %s",
                    exc, exc_info=True,
                )

            await asyncio.sleep(poll_interval_seconds)
    finally:
        await engine.dispose()
