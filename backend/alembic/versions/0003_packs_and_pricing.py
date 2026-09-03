"""packs and pricing

Adds ``pack``, ``subject``, ``pack_subject`` and ``student_pack_assignment``. **Purely additive:**
no existing table is touched and nothing is backfilled, so every drift, arrears and outstanding
figure is identical before and after. Students without an assignment keep being priced from the
legacy ``student.fee`` (see ``app/services/pricing_service.py``); ``fee`` is dropped in a later
sprint, once every student is on a pack, via a native DROP COLUMN.

Two hunks were removed from the autogenerate output by hand:

* ``Detected removed/added foreign key (class_id)(id) on table student`` — spurious. Migration
  0002 added that FK with an inline ``REFERENCES`` clause, which SQLite stores unnamed, so
  autogenerate sees the model's constraint as "different" and proposes dropping and re-adding it.
  It would emit a ``batch_alter_table`` on ``student``, i.e. a table rebuild — which fails against
  any populated database (``DROP TABLE student`` vs. ``foreign_keys=ON``; see 0002's docstring).
  **Expect this phantom diff on every future autogenerate against `student`, and delete it.**

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-31 16:02:11.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('subject',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.CheckConstraint('length(trim(name)) > 0', name='ck_subject_name_nonempty'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('pack',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    # Same ClassLevel enum as school_class; values ('2BAC'), not member names ('BAC2').
    sa.Column('level', sa.Enum('1AC', '2AC', '3AC', 'TC', '1BAC', '2BAC', name='classlevel'), nullable=False),
    sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('length(trim(name)) > 0', name='ck_pack_name_nonempty'),
    sa.CheckConstraint('price >= 0', name='ck_pack_price_non_negative'),
    sa.PrimaryKeyConstraint('id'),
    # One price per offering per level — the reason `level` lives on the pack at all.
    sa.UniqueConstraint('name', 'level', name='uq_pack_name_level')
    )
    op.create_table('pack_subject',
    sa.Column('pack_id', sa.Integer(), nullable=False),
    sa.Column('subject_id', sa.Integer(), nullable=False),
    # Link rows die with their pack; a subject that is still in use cannot be deleted.
    sa.ForeignKeyConstraint(['pack_id'], ['pack.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subject_id'], ['subject.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('pack_id', 'subject_id')
    )
    op.create_table('student_pack_assignment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('pack_id', sa.Integer(), nullable=False),
    # A snapshot of the agreed price, never a join to pack.price — so repricing a pack, moving a
    # student between packs, and per-student discounts all leave billing history untouched.
    sa.Column('monthly_price', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('note', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('monthly_price >= 0', name='ck_assignment_price_non_negative'),
    sa.ForeignKeyConstraint(['pack_id'], ['pack.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('student_id', 'effective_from', name='uq_assignment_student_from')
    )


def downgrade() -> None:
    """Downgrade schema.

    Lossless for everything that predates this migration: only the four new tables go, and
    ``student.fee`` — untouched on the way up — is still the price of record on the way down.
    """
    op.drop_table('student_pack_assignment')
    op.drop_table('pack_subject')
    op.drop_table('pack')
    op.drop_table('subject')
