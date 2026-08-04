"""
Application lifecycle manager.

Handles startup and shutdown events using FastAPI's lifespan context.
Add startup tasks (DB pool warm-up, cache init, etc.) before the yield.
Add cleanup tasks (close connections, flush queues, etc.) after the yield.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    Code before yield runs on startup.
    Code after yield runs on shutdown.
    """
    logger.info("Application starting up...")
    # Future: initialise DB connection pool, cache, etc.
    yield
    # Future: close connections, flush message queues, etc.
    logger.info("Application shutting down...")
