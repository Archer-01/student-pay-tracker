"""school share handover

Adds ``school_share_handover``: the teacher's record that he handed the school its share of a
month, and how much. One row per month (unique year + month).

Purely additive: a new table, nothing backfilled. The downgrade drops the table and the
handovers recorded in it.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-21 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'school_share_handover',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('handed_on', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('month BETWEEN 1 AND 12', name='ck_school_share_handover_month'),
        sa.CheckConstraint('amount >= 0', name='ck_school_share_handover_amount_non_negative'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year', 'month', name='uq_school_share_handover_month'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('school_share_handover')
