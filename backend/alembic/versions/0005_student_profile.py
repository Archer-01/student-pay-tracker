"""student profile: split name, add is_repeating

Splits ``student.name`` into ``first_name`` + ``last_name`` and adds ``is_repeating``
("redoublant"). ``last_name`` is nullable because some students have no surname on record.

**The split is an explicit mapping, not a heuristic.** Splitting on whitespace looks fine until it
meets a compound given name: the seed data alone contains "Fatima Zahra", where both words are the
given name and there is no surname — a naive split would invent the surname "Zahra". With a
handful of rows the right move is to enumerate them. Anything not in the mapping falls back to
first-token/rest, which is a guess; the fallback exists so the migration cannot fail, not because
it is correct. Review ``student`` after upgrading if the table held names this migration doesn't
know.

The table is rebuilt (create-copy-DROP-rename) rather than altered, because ``first_name`` must end
up NOT NULL and SQLite cannot add a NOT NULL column without a default, nor tighten one afterwards.
That DROP needs foreign-key enforcement suspended; ``alembic/env.py`` does it for the whole
migration run and explains why it can't be done from here.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-01 10:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# full name -> (first_name, last_name). A NULL last name means "no surname on record".
_KNOWN_NAMES: dict[str, tuple[str, str | None]] = {
    "Amina Benali": ("Amina", "Benali"),
    "Youssef El Amrani": ("Youssef", "El Amrani"),
    "Sara Idrissi": ("Sara", "Idrissi"),
    "Omar Tazi": ("Omar", "Tazi"),
    "Fatima Zahra": ("Fatima Zahra", None),  # compound given name, no surname
    "Mehdi Alaoui": ("Mehdi", "Alaoui"),
}

_NEW_STUDENT = """
CREATE TABLE student_new (
    id INTEGER NOT NULL,
    first_name VARCHAR NOT NULL,
    last_name VARCHAR,
    phone VARCHAR,
    is_repeating BOOLEAN DEFAULT '0' NOT NULL,
    join_date DATE NOT NULL,
    status VARCHAR(8) NOT NULL,
    class_id INTEGER REFERENCES school_class(id) ON DELETE SET NULL,
    pack_id INTEGER REFERENCES pack(id) ON DELETE RESTRICT,
    custom_price NUMERIC(10, 2),
    price_note VARCHAR,
    created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
    -- Carried across only so the name corrections below can key off it, then dropped.
    name VARCHAR,
    PRIMARY KEY (id),
    CONSTRAINT ck_student_custom_price_non_negative
        CHECK (custom_price IS NULL OR custom_price >= 0),
    CONSTRAINT ck_student_first_name_nonempty CHECK (length(trim(first_name)) > 0)
)
"""

_OLD_STUDENT = """
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

_COLUMNS = (
    "phone, join_date, status, class_id, pack_id, custom_price, price_note, created_at"
)


def _swap_in(create_sql: str, copy_sql: str) -> None:
    """SQLite's documented table rebuild. See env.py for the foreign-key handling."""
    op.execute(create_sql)
    op.execute(copy_sql)
    op.execute("DROP TABLE student")
    op.execute("ALTER TABLE student_new RENAME TO student")


def upgrade() -> None:
    """Upgrade schema."""
    # Copy first using the fallback split, then correct the names we actually know. Two passes
    # with bound parameters, rather than one query built by concatenating CASE expressions — the
    # names are user data and have no business being interpolated into SQL.
    fallback_first = (
        "CASE WHEN instr(name, ' ') = 0 THEN name "
        "ELSE substr(name, 1, instr(name, ' ') - 1) END"
    )
    fallback_last = (
        "CASE WHEN instr(name, ' ') = 0 THEN NULL "
        "ELSE substr(name, instr(name, ' ') + 1) END"
    )
    _swap_in(
        _NEW_STUDENT,
        f"""
        INSERT INTO student_new
            (id, first_name, last_name, is_repeating, {_COLUMNS}, name)
        SELECT id, {fallback_first}, {fallback_last}, 0, {_COLUMNS}, name
        FROM student
        """,
    )

    bind = op.get_bind()
    for full, (first, last) in _KNOWN_NAMES.items():
        bind.execute(
            sa.text(
                "UPDATE student SET first_name = :first, last_name = :last WHERE name = :full"
            ),
            {"first": first, "last": last, "full": full},
        )
    # `name` was carried across only to key the corrections above; it is not part of the schema.
    op.execute("ALTER TABLE student DROP COLUMN name")


def downgrade() -> None:
    """Downgrade schema.

    Recomposes ``name`` from the two parts. ``is_repeating`` is dropped and cannot come back.
    """
    _swap_in(
        _OLD_STUDENT,
        f"""
        INSERT INTO student_new (id, name, {_COLUMNS})
        SELECT id,
               trim(first_name || COALESCE(' ' || last_name, '')),
               {_COLUMNS}
        FROM student
        """,
    )
