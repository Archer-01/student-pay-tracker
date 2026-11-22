"""student billed_from

Adds ``student.billed_from``: the day a student stopped being free on purpose (decision 0011).
Unpaid months due before it were free and stay free; the service sets it, never by hand.

Purely additive and nullable: nothing is backfilled, so every existing student keeps exactly the
arrears and drift it had (NULL means no restriction). The downgrade drops the column, losing only
those dates, which means formerly free months would count as owed again.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-22 14:20:47.388744

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('student', schema=None) as batch_op:
        batch_op.add_column(sa.Column('billed_from', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('student', schema=None) as batch_op:
        batch_op.drop_column('billed_from')
