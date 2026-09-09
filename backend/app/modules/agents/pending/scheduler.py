"""
Background reminder scheduler for Pending Agent.
Periodically polls for active pending cycles whose next_reminder_at is due (e.g. 1 min elapsed)
and triggers the next reminder tier.
"""
import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.modules.agents.pending.repository import PendingCycleRepository
from app.modules.agents.pending.service import PendingService

logger = logging.getLogger(__name__)


async def start_pending_reminder_scheduler(poll_interval_seconds: int = 10) -> None:
    """
    Infinite background loop that runs during the app lifespan.
    Checks for due reminders every poll_interval_seconds.
    """
    logger.info(f"[PendingScheduler] Background reminder scheduler started (polling every {poll_interval_seconds}s)")
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
                            f"[PendingScheduler] Cycle {cycle.id} for {cycle.incident_number} "
                            f"is due for Reminder {target_tier}/{cycle.max_reminders}. Triggering..."
                        )
                        service = PendingService(db)
                        await service.process_pending_transition(
                            incident_id=cycle.incident_id,
                            force_reminder=True,
                        )
            except asyncio.CancelledError:
                logger.info("[PendingScheduler] Scheduler task cancelled.")
                break
            except Exception as e:
                logger.error(f"[PendingScheduler] Error in reminder scheduler loop: {e}", exc_info=True)

            await asyncio.sleep(poll_interval_seconds)
    finally:
        await engine.dispose()
