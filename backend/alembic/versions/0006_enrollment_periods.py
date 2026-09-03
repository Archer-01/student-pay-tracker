"""enrollment periods: leave and return

Records the spans a student was actually attending, so months they were away can be excluded from
what they owe. ``student.join_date`` is untouched and remains the immutable drift anchor — periods
say when the student was *present*, they never re-date the schedule.

**Purely additive, and no figure moves.** Every existing student is backfilled with a single
**open** period starting at their ``join_date``, which means no cycle falls outside a period and
nothing is suspended. Arrears, drift and outstanding balances are identical before and after.

One deliberate gap: a student already marked ``inactive`` has no recorded leave date, and this
migration does **not** invent one — guessing a departure month would silently change what they
owe. They keep an open period until a real leave is recorded via ``POST /students/{id}/leave``,
and the students list flags them so the gap is visible rather than forgotten.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-02 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'enrollment_period',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('entry_date', sa.Date(), nullable=False),
        # NULL = still attending.
        sa.Column('leave_date', sa.Date(), nullable=True),
        sa.Column('leave_reason', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint(
            'leave_date IS NULL OR leave_date >= entry_date',
            name='ck_enrollment_period_dates_ordered',
        ),
        sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # "At most one open period per student", enforced by the database rather than by convention.
    op.execute(
        "CREATE UNIQUE INDEX uq_enrollment_period_one_open "
        "ON enrollment_period (student_id) WHERE leave_date IS NULL"
    )
    # One open period per existing student, anchored at their join date: no gaps, so no cycle is
    # suspended and no number changes.
    op.execute(
        "INSERT INTO enrollment_period (student_id, entry_date) SELECT id, join_date FROM student"
    )


def downgrade() -> None:
    """Downgrade schema.

    Drops the attendance history entirely. Any recorded leave/return dates are lost, and every
    student reverts to being billed for every cycle since their join date.
    """
    op.drop_index('uq_enrollment_period_one_open', table_name='enrollment_period')
    op.drop_table('enrollment_period')
