"""school classes

Adds the ``school_class`` table (level + name) and a nullable ``student.class_id`` referencing
it. Purely additive: no backfill and no data transformation. Existing students land with
``class_id = NULL`` (unassigned), so no drift or arrears figure can move.

Hand-written after autogenerate, for a reason worth recording. Autogenerate produced a
``batch_alter_table`` on ``student`` with an unnamed foreign key. Both parts were wrong:

* Batch mode on SQLite rebuilds the table (create → copy → ``DROP TABLE student`` → rename).
  ``app/core/db.py`` sets ``PRAGMA foreign_keys=ON`` on every connection, so that DROP fails
  against any database that already holds ``payment`` / ``anchor_override`` rows. It succeeds on
  an empty database, which is why this must be verified against a copy of a *populated* one.
* An unnamed constraint cannot be dropped, so the downgrade could not have run.

SQLite can add a nullable column together with an inline ``REFERENCES`` clause in place, without
touching the existing rows — but neither ``op.add_column`` nor ``batch_alter_table`` will emit
that form (alembic always tries a separate ``ADD CONSTRAINT``, which SQLite rejects). Hence the
explicit DDL below. SQLite is this project's permanent backend by design, so dialect-specific DDL
here is a deliberate trade, not an oversight.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-31 15:15:03.959759

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('school_class',
    sa.Column('id', sa.Integer(), nullable=False),
    # Values ('2BAC'), not member names ('BAC2') — matches the ?level= filter and the exports.
    sa.Column('level', sa.Enum('1AC', '2AC', '3AC', 'TC', '1BAC', '2BAC', name='classlevel'), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('length(trim(name)) > 0', name='ck_school_class_name_nonempty'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('level', 'name', name='uq_school_class_level_name')
    )
    # ON DELETE SET NULL is a database-level backstop only: ClassService refuses to delete a
    # class that still has students, so in practice it never fires.
    op.execute(
        'ALTER TABLE student ADD COLUMN class_id INTEGER '
        'REFERENCES school_class(id) ON DELETE SET NULL'
    )


def downgrade() -> None:
    """Downgrade schema.

    Lossless for every pre-existing column: only ``student.class_id`` (added above) goes, along
    with the table it referenced. Native ``DROP COLUMN`` (SQLite 3.35+), avoiding the table
    rebuild for the same reason the upgrade does.
    """
    op.execute('ALTER TABLE student DROP COLUMN class_id')
    op.drop_table('school_class')
