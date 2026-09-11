"""create_pending_cycles_table

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-09-06 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c8d9e0f1a2b3'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'pending_cycles',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('incident_id', sa.String(length=36), sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ACTIVE'),
        sa.Column('reminder_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_reminders', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('reminder_template', sa.String(length=100), nullable=True),
        sa.Column('next_reminder_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_pending_cycles_incident_id', 'pending_cycles', ['incident_id'])
    op.create_index('ix_pending_cycles_status', 'pending_cycles', ['status'])
    op.create_index(
        'uq_active_cycle_per_incident',
        'pending_cycles',
        ['incident_id'],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
        sqlite_where=sa.text("status = 'ACTIVE'")
    )


def downgrade() -> None:
    op.drop_index('uq_active_cycle_per_incident', table_name='pending_cycles')
    op.drop_index('ix_pending_cycles_status', table_name='pending_cycles')
    op.drop_index('ix_pending_cycles_incident_id', table_name='pending_cycles')
    op.drop_table('pending_cycles')
