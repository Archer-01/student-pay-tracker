#!/usr/bin/env bash
#
# Wipe the database and reload the demo dataset.
#
#   WHEN THIS IS LEGAL: before launch, while the database holds nothing but seeded demo data.
#   WHEN IT IS NOT:     ever after the teacher records a real payment.
#
# Schema changes do NOT need this. The container already runs `alembic upgrade head` on every
# start (see the Dockerfile CMD), and every migration in this project is verified in both
# directions against a *populated* copy of the database — migration 0002 passed against an empty
# one and failed against a real one, which is exactly the trap this avoids. Upgrading is the
# supported path forever; wiping only ever changes which rows exist, never which columns.
#
# So this script refuses to run if it finds a student the seed doesn't know about, on the
# assumption that anyone unrecognised is a real person whose payment history you are about to
# delete. Set FORCE=1 to override that, and mean it.
#
# Run it inside the running container, where `ardoise` and `alembic` are already on PATH:
#
#   docker compose exec -it app scripts/reset-demo-data.sh
#
# Non-interactive (CI, a rebuild script):
#
#   docker compose exec app env ASSUME_YES=1 scripts/reset-demo-data.sh
#
set -euo pipefail

DB_URL="${DATABASE_URL:-sqlite:////data/app.db}"
# Backups belong on the mounted volume. `ardoise db backup` defaults to a *relative* directory,
# which inside the container is /app/backups — a layer that vanishes with the container, taking
# the only copy of the data with it.
BACKUP_DIR="${BACKUP_DIR:-/data/backups}"

# The slim runtime image has no sqlite3 binary, so every inspection goes through Python.
py() { python -c "$1"; }

banner() { printf '\n\033[1m%s\033[0m\n' "$1"; }

banner "Target"
printf '  database: %s\n' "$DB_URL"
printf '  backups:  %s\n' "$BACKUP_DIR"

if ! py 'import app.core.db' >/dev/null 2>&1; then
  echo "  ERROR: run this inside the app container, from /app." >&2
  exit 1
fi

banner "Current contents"
py '
from app.core.db import get_sessionmaker
from sqlalchemy import text
s = get_sessionmaker()()
for table in ("student", "payment", "school_class", "pack", "enrollment_period", "debt_writeoff"):
    try:
        n = s.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
        print(f"  {table:<20} {n}")
    except Exception:
        print(f"  {table:<20} (missing — database not migrated yet)")
'

# --- Safety net: does anything here look like a real person? -----------------
banner "Checking for real data"
UNEXPECTED="$(py '
from app.core.db import get_sessionmaker
from app.core.seed import SEED_STUDENTS
from app.models import Student

# Read the roster from the seed module itself, so this check cannot drift out of date.
known = {(s.first_name, s.last_name) for s in SEED_STUDENTS}
session = get_sessionmaker()()
try:
    rows = session.query(Student).all()
except Exception:
    rows = []          # no student table yet: a fresh deploy, nothing to protect
strangers = [s.full_name for s in rows if (s.first_name, s.last_name) not in known]
print("\n".join(strangers))
')"

if [ -n "$UNEXPECTED" ]; then
  printf '  Found %s student(s) the seed does not know:\n' "$(echo "$UNEXPECTED" | wc -l | tr -d ' ')"
  echo "$UNEXPECTED" | sed 's/^/    - /'
  if [ "${FORCE:-0}" != "1" ]; then
    cat >&2 <<'MSG'

  REFUSING TO CONTINUE.

  These look like real students, and this script would delete them along with every payment
  they have ever made. If the schema is what you were trying to update, you do not need this
  script at all — restarting the container runs the migrations.

  If you are certain this is still demo data, re-run with FORCE=1.
MSG
    exit 1
  fi
  echo "  FORCE=1 set — continuing anyway."
else
  echo "  Only seeded demo students found."
fi

# --- Back up before destroying anything --------------------------------------
banner "Backing up"
ardoise db backup --to "$BACKUP_DIR"
LATEST="$(ls -1t "$BACKUP_DIR"/*.db 2>/dev/null | head -1 || true)"
if [ -z "$LATEST" ] || [ ! -s "$LATEST" ]; then
  echo "  ERROR: no non-empty backup was written; refusing to wipe." >&2
  exit 1
fi
printf '  wrote %s (%s bytes)\n' "$LATEST" "$(wc -c < "$LATEST" | tr -d ' ')"

# --- Confirm ------------------------------------------------------------------
if [ "${ASSUME_YES:-0}" != "1" ]; then
  banner "Confirm"
  printf '  This deletes every row and reloads the demo data. Type "wipe" to continue: '
  read -r REPLY
  if [ "$REPLY" != "wipe" ]; then
    echo "  Cancelled. Nothing was changed."
    exit 1
  fi
fi

# --- Wipe and reload ----------------------------------------------------------
banner "Resetting schema"
# `db reset` is alembic downgrade base + upgrade head, so it also proves the downgrade path works.
ALLOW_DB_RESET=1 ardoise db reset --yes

banner "Seeding"
ardoise db seed

banner "Result"
py '
from app.core.db import get_sessionmaker
from sqlalchemy import text
s = get_sessionmaker()()
for table in ("student", "payment", "school_class", "pack", "enrollment_period"):
    n = s.execute(text("SELECT count(*) FROM " + table)).scalar_one()
    print(f"  {table:<20} {n}")
'
printf '\n  Done. Backup kept at %s\n\n' "$LATEST"
