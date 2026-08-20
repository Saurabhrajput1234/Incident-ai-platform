"""engineer_unique_email_group

Allow an engineer to belong to multiple assignment groups.
Replaces the unique constraint on (email) with a composite unique
constraint on (email, assignment_group).

Revision ID: a1b2c3d4e5f6
Revises: 76deb7e985b5
Create Date: 2026-08-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '76deb7e985b5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old unique index on email alone
    op.drop_index('ix_engineers_email', table_name='engineers')

    # Re-create email index as non-unique (still want fast lookups by email)
    op.create_index('ix_engineers_email', 'engineers', ['email'], unique=False)

    # Add composite unique constraint (email, assignment_group)
    op.create_unique_constraint(
        'uq_engineer_email_group',
        'engineers',
        ['email', 'assignment_group'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_engineer_email_group', 'engineers', type_='unique')
    op.drop_index('ix_engineers_email', table_name='engineers')
    op.create_index('ix_engineers_email', 'engineers', ['email'], unique=True)
