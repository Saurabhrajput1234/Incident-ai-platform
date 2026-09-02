"""add_incident_work_notes_table

Creates the incident_work_notes table as a proper one-to-many replacement
for the flat incident.work_notes TEXT field.

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-09-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b7c8d9e0f1a2'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'incident_work_notes',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('incident_id', sa.String(36), sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('source_type', sa.String(40), nullable=False),
        sa.Column('source_name', sa.String(200), nullable=False),
        sa.Column('source_id', sa.String(100), nullable=True),
        sa.Column('action_type', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_work_notes_incident_id', 'incident_work_notes', ['incident_id'])
    op.create_index('ix_work_notes_source_type', 'incident_work_notes', ['source_type'])
    op.create_index('ix_work_notes_created_at', 'incident_work_notes', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_work_notes_created_at', table_name='incident_work_notes')
    op.drop_index('ix_work_notes_source_type', table_name='incident_work_notes')
    op.drop_index('ix_work_notes_incident_id', table_name='incident_work_notes')
    op.drop_table('incident_work_notes')
