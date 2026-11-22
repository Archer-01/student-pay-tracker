"""free periods

Replaces ``student.billed_from`` (0011) with a ``free_period`` table (decision 0014). One date
couldn't say when a student *became* free, so it waived real debt from months they were priced
(a 0 typed by mistake and fixed erased it) and missed a pack repriced from 0. A period per
stretch of being free records exactly the months that were free.

Backfill, so nothing a teacher sees changes:

- every student free today (an agreed price of 0, or no agreed price and a pack at 0) gets an open
  period from their join date (``opened_on`` too: they have been free since, not since today).
  They owe nothing today either way, since prices are current (decision 0002); without it, their
  first price would bill every month back to joining;
- a student with a ``billed_from`` (free until then, priced since: possible only in the hours
  0011 was live) gets the closed period ``[join_date, billed_from)``, which waives exactly what
  ``billed_from`` waived.

It also adds ``student.entered_on``, the day a student was entered (backfilled from
``created_at``): a price corrected to 0 on that day frees them from joining, as an enrolment at 0
would.

``billed_from`` is dropped with a plain ``DROP COLUMN`` (SQLite 3.35+), not a batch rebuild of
``student``, which would lose the ON DELETE rules SQLite keeps inline (see ``alembic/env.py``).

The downgrade is lossy: it drops the periods and leaves ``billed_from`` empty, so months that were
free count as owed again.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-22 14:54:26.933295

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('free_period',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('from_date', sa.Date(), nullable=False),
    sa.Column('to_date', sa.Date(), nullable=True),
    sa.Column('opened_on', sa.Date(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('to_date IS NULL OR to_date > from_date', name='ck_free_period_dates_ordered'),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('free_period', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_free_period_student_id'), ['student_id'], unique=False)
        batch_op.create_index('uq_free_period_one_open', ['student_id'], unique=True, sqlite_where=sa.text('to_date IS NULL'))

    # The day each student was entered: their creation date, as near as the data allows.
    op.add_column('student', sa.Column('entered_on', sa.Date(), nullable=True))
    op.execute("UPDATE student SET entered_on = date(created_at)")
    # Free today: open from joining.
    op.execute(
        """
        INSERT INTO free_period (student_id, from_date, opened_on)
        SELECT s.id, s.join_date, s.join_date FROM student s
        LEFT JOIN pack p ON p.id = s.pack_id
        WHERE s.custom_price = 0 OR (s.custom_price IS NULL AND p.price = 0)
        """
    )
    # Free until billed_from, priced since (and not free again).
    op.execute(
        """
        INSERT INTO free_period (student_id, from_date, to_date, opened_on)
        SELECT s.id, s.join_date, s.billed_from, s.join_date FROM student s
        WHERE s.billed_from IS NOT NULL AND s.billed_from > s.join_date
          AND s.id NOT IN (SELECT student_id FROM free_period)
        """
    )
    op.drop_column('student', 'billed_from')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('student', sa.Column('billed_from', sa.DATE(), nullable=True))
    op.drop_column('student', 'entered_on')

    with op.batch_alter_table('free_period', schema=None) as batch_op:
        batch_op.drop_index('uq_free_period_one_open', sqlite_where=sa.text('to_date IS NULL'))
        batch_op.drop_index(batch_op.f('ix_free_period_student_id'))

    op.drop_table('free_period')
