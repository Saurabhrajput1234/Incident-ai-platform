"""
AgentExecutionLogger — lightweight context manager that writes a row to
agent_executions at the start and end of every agent handler run.

Usage (in any handler):
    async with AgentExecutionLogger(
        agent_name="TriageAgent",
        incident_id=event.incident_id,
        triggering_event_type="IncidentCreatedEvent",
        triggering_event_id=event.incident_id,
        correlation_id=event.incident_number,
    ) as log:
        response = await TriageService(db).run_triage(...)
        log.set_result("success" if response.success else "failed", error=...)
"""
import uuid
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings

logger = logging.getLogger(__name__)


class _ExecutionContext:
    """Mutable holder so the caller can call set_result() inside the with block."""

    def __init__(self):
        self.status = "success"
        self.error: str | None = None

    def set_result(self, status: str, error: str | None = None):
        self.status = status
        self.error = error


@asynccontextmanager
async def agent_execution_log(
    agent_name: str,
    incident_id: str | None = None,
    triggering_event_type: str | None = None,
    triggering_event_id: str | None = None,
    correlation_id: str | None = None,
):
    """
    Async context manager that bookends an agent run with DB writes.

    On enter  → INSERT row with status='running'
    On exit   → UPDATE row with final status + completed_at
    On error  → UPDATE row with status='failed' + exception message
    """
    ctx = _ExecutionContext()
    execution_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    engine = create_async_engine(settings.DATABASE_URL, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # --- Insert 'running' row ---
    try:
        async with session_factory() as db:
            await _insert_row(
                db=db,
                execution_id=execution_id,
                agent_name=agent_name,
                incident_id=incident_id,
                triggering_event_type=triggering_event_type,
                triggering_event_id=triggering_event_id,
                correlation_id=correlation_id,
                started_at=started_at,
            )
    except Exception as insert_exc:
        logger.warning("[AgentExecutionLogger] Insert failed for %s: %s", agent_name, insert_exc)

    # --- Yield control to the agent handler ---
    try:
        yield ctx
    except Exception as exc:
        ctx.status = "failed"
        ctx.error = str(exc)
        raise
    finally:
        # --- Update row with final outcome ---
        completed_at = datetime.now(timezone.utc)
        try:
            async with session_factory() as db:
                await _update_row(
                    db=db,
                    execution_id=execution_id,
                    status=ctx.status,
                    error=ctx.error,
                    completed_at=completed_at,
                )
        except Exception as update_exc:
            logger.warning("[AgentExecutionLogger] Update failed for %s: %s", agent_name, update_exc)
        finally:
            await engine.dispose()


async def _insert_row(
    db: AsyncSession,
    execution_id: str,
    agent_name: str,
    incident_id: str | None,
    triggering_event_type: str | None,
    triggering_event_id: str | None,
    correlation_id: str | None,
    started_at: datetime,
) -> None:
    from sqlalchemy import text
    await db.execute(
        text("""
            INSERT INTO agent_executions
                (id, incident_id, agent_name, triggering_event_type,
                 triggering_event_id, status, attempt_count,
                 started_at, correlation_id)
            VALUES
                (:id, :incident_id, :agent_name, :triggering_event_type,
                 :triggering_event_id, 'running', 1,
                 :started_at, :correlation_id)
        """),
        {
            "id": execution_id,
            "incident_id": incident_id,
            "agent_name": agent_name,
            "triggering_event_type": triggering_event_type,
            "triggering_event_id": triggering_event_id,
            "started_at": started_at,
            "correlation_id": correlation_id,
        },
    )
    await db.commit()


async def _update_row(
    db: AsyncSession,
    execution_id: str,
    status: str,
    error: str | None,
    completed_at: datetime,
) -> None:
    from sqlalchemy import text
    await db.execute(
        text("""
            UPDATE agent_executions
            SET status       = :status,
                error        = :error,
                completed_at = :completed_at
            WHERE id = :id
        """),
        {
            "id": execution_id,
            "status": status,
            "error": error,
            "completed_at": completed_at,
        },
    )
    await db.commit()
