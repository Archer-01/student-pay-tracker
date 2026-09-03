"""single pack per student

Collapses pricing to one number per student. Before this, a price could come from three places —
``pack.price``, ``student_pack_assignment.monthly_price`` and the legacy ``student.fee`` — which
was one concept too many. After it:

    effective price = student.custom_price  if set,  else  student.pack.price

``student`` gains ``pack_id`` (the single pack they're on), ``custom_price`` (set only when they
don't pay the pack price) and ``price_note`` (why). ``student.fee`` and the whole
``student_pack_assignment`` table go.

**This trades away historical pricing, deliberately.** Changing a pack's price now changes what
its students owe for months already unpaid, and moving a student to another pack reprices their
past months too. That was accepted: prices are still being settled while the data is dummy, and by
the time real students are billed, changes will be rare.

**The rebuild.** ``student.fee`` cannot be dropped with ``ALTER TABLE ... DROP COLUMN`` — SQLite
refuses to drop a column named in a CHECK constraint (``ck_student_fee_non_negative``). So the
table is rebuilt using SQLite's documented create-copy-DROP-rename procedure. That DROP requires
``foreign_keys=OFF``, since ``payment`` and ``anchor_override`` hold rows referencing ``student``
(the same trap as migration 0002); ``alembic/env.py`` suspends enforcement for the whole migration
run, and explains there why it cannot be done from inside this file.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-31 19:20:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_STUDENT = """
CREATE TABLE student_new (
    id INTEGER NOT NULL,
    name VARCHAR NOT NULL,
    phone VARCHAR,
    join_date DATE NOT NULL,
    status VARCHAR(8) NOT NULL,
    class_id INTEGER REFERENCES school_class(id) ON DELETE SET NULL,
    pack_id INTEGER REFERENCES pack(id) ON DELETE RESTRICT,
    custom_price NUMERIC(10, 2),
    price_note VARCHAR,
    created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_student_custom_price_non_negative
        CHECK (custom_price IS NULL OR custom_price >= 0)
)
"""

# Carry every student's current price across unchanged, so no arrears figure moves:
#   * on a pack at a bespoke price -> custom_price keeps that price (and its note)
#   * on a pack at the pack price  -> custom_price stays NULL; the pack price applies
#   * on no pack at all            -> custom_price keeps the legacy fee, so they stay billed
_COPY_STUDENTS = """
INSERT INTO student_new
    (id, name, phone, join_date, status, class_id, pack_id, custom_price, price_note, created_at)
SELECT
    s.id, s.name, s.phone, s.join_date, s.status, s.class_id,
    a.pack_id,
    CASE
        WHEN a.pack_id IS NULL THEN s.fee
        WHEN a.monthly_price <> p.price THEN a.monthly_price
        ELSE NULL
    END,
    a.note,
    s.created_at
FROM student s
LEFT JOIN (
    SELECT a1.student_id, a1.pack_id, a1.monthly_price, a1.note
    FROM student_pack_assignment a1
    WHERE a1.effective_from = (
        SELECT MAX(a2.effective_from)
        FROM student_pack_assignment a2
        WHERE a2.student_id = a1.student_id
    )
) a ON a.student_id = s.id
LEFT JOIN pack p ON p.id = a.pack_id
"""

_OLD_STUDENT = """
CREATE TABLE student_new (
    id INTEGER NOT NULL,
    name VARCHAR NOT NULL,
    phone VARCHAR,
    join_date DATE NOT NULL,
    fee NUMERIC(10, 2) NOT NULL,
    status VARCHAR(8) NOT NULL,
    created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
    class_id INTEGER REFERENCES school_class(id) ON DELETE SET NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_student_fee_non_negative CHECK (fee >= 0)
)
"""

# Going back, fee is the price that was in force: the override if there was one, else the pack's.
_RESTORE_STUDENTS = """
INSERT INTO student_new (id, name, phone, join_date, fee, status, created_at, class_id)
SELECT
    s.id, s.name, s.phone, s.join_date,
    COALESCE(s.custom_price, p.price, 0),
    s.status, s.created_at, s.class_id
FROM student s
LEFT JOIN pack p ON p.id = s.pack_id
"""

_RESTORE_ASSIGNMENTS = """
INSERT INTO student_pack_assignment
    (student_id, pack_id, monthly_price, effective_from, note)
SELECT s.id, s.pack_id, COALESCE(s.custom_price, p.price), s.join_date, s.price_note
FROM student s
JOIN pack p ON p.id = s.pack_id
"""


def _rebuild_student(create_sql: str, copy_sql: str) -> None:
    """Swap `student` for a new definition, preserving rows and child foreign keys.

    SQLite's documented table-rebuild procedure. Relies on env.py having suspended foreign-key
    enforcement for the migration run; child FK clauses keep pointing at ``student``, and the
    rows are referentially sound again as soon as the rename completes.
    """
    op.execute(create_sql)
    op.execute(copy_sql)
    op.execute("DROP TABLE student")
    op.execute("ALTER TABLE student_new RENAME TO student")


def upgrade() -> None:
    """Upgrade schema."""
    _rebuild_student(_NEW_STUDENT, _COPY_STUDENTS)
    op.execute("DROP TABLE student_pack_assignment")


def downgrade() -> None:
    """Downgrade schema.

    Restores ``fee`` and a single assignment per student, priced at what they pay now. The
    *history* this migration discarded cannot come back — a student who once paid a different
    price under an earlier assignment is restored with only their current one, dated from their
    join date. Lossy by nature, not by oversight.
    """
    op.execute(
        """
        CREATE TABLE student_pack_assignment (
            id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            pack_id INTEGER NOT NULL,
            monthly_price NUMERIC(10, 2) NOT NULL,
            effective_from DATE NOT NULL,
            note VARCHAR,
            created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT ck_assignment_price_non_negative CHECK (monthly_price >= 0),
            CONSTRAINT uq_assignment_student_from UNIQUE (student_id, effective_from),
            FOREIGN KEY(pack_id) REFERENCES pack (id) ON DELETE RESTRICT,
            FOREIGN KEY(student_id) REFERENCES student (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(_RESTORE_ASSIGNMENTS)
    _rebuild_student(_OLD_STUDENT, _RESTORE_STUDENTS)
