"""add agent_executions table

Revision ID: f1a2b3c4d5e6
Revises: e67628208ea8
Create Date: 2026-10-07

"""
from alembic import op
import sqlalchemy as sa

revision = 'f1a2b3c4d5e6'
down_revision = 'e67628208ea8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Table already exists in DB — create only if it doesn't exist
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_executions (
            id                   VARCHAR(36)   PRIMARY KEY,
            incident_id          VARCHAR(36)   REFERENCES incidents(id) ON DELETE SET NULL,
            agent_name           VARCHAR(100)  NOT NULL,
            triggering_event_id  VARCHAR(100),
            triggering_event_type VARCHAR(100),
            status               VARCHAR(20)   NOT NULL DEFAULT 'running',
            attempt_count        INTEGER       NOT NULL DEFAULT 1,
            started_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
            completed_at         TIMESTAMPTZ,
            result               TEXT,
            error                TEXT,
            correlation_id       VARCHAR(100)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_agent_executions_incident_id
        ON agent_executions (incident_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_agent_executions_agent_name
        ON agent_executions (agent_name)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_agent_executions_started_at
        ON agent_executions (started_at DESC)
    """)


def downgrade() -> None:
    op.drop_table('agent_executions')
