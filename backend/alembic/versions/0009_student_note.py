"""student note

Adds ``student.note``: the teacher's private note on a student ("paie le samedi", "père :
Ahmed"). Shown on the student page only, never on a PDF.

Purely additive and nullable: existing students simply have no note, nothing is backfilled, and
the downgrade is lossless except for the notes themselves, which it drops with the column.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-21 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('student') as batch_op:
        batch_op.add_column(sa.Column('note', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('student') as batch_op:
        batch_op.drop_column('note')
