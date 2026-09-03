"""debt write-offs

Adds ``debt_writeoff``: an append-only record of a debt the teacher chose to forgive.

Whether a student "left owing money" is **derived** — no open enrollment period, and an
outstanding balance as of their last departure — so there is no flag column to add. The only
persisted fact is the decision to write a balance off, which exists so that clearing the leavers
list never requires recording a payment that was never received.

Purely additive: no existing table is touched and nothing is backfilled.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-02 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'debt_writeoff',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        # A snapshot of what was forgiven; the balance it came from is derived and transient.
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('amount >= 0', name='ck_debt_writeoff_amount_non_negative'),
        sa.CheckConstraint('length(trim(reason)) > 0', name='ck_debt_writeoff_reason_nonempty'),
        sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema. Forgiven-debt records are lost; the balances themselves were derived."""
    op.drop_table('debt_writeoff')
