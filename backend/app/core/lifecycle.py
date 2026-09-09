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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    Code before yield runs on startup.
    Code after yield runs on shutdown.
    """
    logger.info("Application starting up...")
    # Start pending reminder background scheduler (polling every 10s)
    scheduler_task = asyncio.create_task(start_pending_reminder_scheduler(poll_interval_seconds=10))
    yield
    logger.info("Application shutting down...")
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
