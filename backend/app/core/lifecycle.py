"""
Application lifecycle manager.

Handles startup and shutdown events using FastAPI's lifespan context.
Startup tasks run before yield, shutdown tasks after yield.
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.logging import logger
from app.modules.agents.pending.scheduler import start_pending_reminder_scheduler
from app.orchestrator.bus import event_bus
from app.orchestrator.registry import register_all_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    register_all_handlers(event_bus)
    scheduler_task = asyncio.create_task(start_pending_reminder_scheduler(poll_interval_seconds=10))
    yield
    logger.info("Application shutting down...")
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
