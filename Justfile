# Repo-wide commands. Each app keeps its own day-to-day ones (backend/Justfile, frontend npm scripts).

# Everything CI checks (.github/workflows/ci.yml): run before calling a change done.
check: backend frontend

# ruff format + ruff check + mypy, tests with coverage (app/ ≥ 95 %, app/services 100 %),
# migrations on an empty DB matching the models (`alembic check`).
backend:
    cd backend && just lint
    cd backend && just cov
    cd backend && export DATABASE_URL="sqlite:///$(mktemp -d)/check.db" && uv run alembic upgrade head && uv run alembic check

# Generated API types up to date, then typecheck, lint and tests with coverage (≥ 85 %).
frontend: schema
    cd frontend && npx tsc -b
    cd frontend && npm run lint
    cd frontend && npm run test:coverage

# Fails when src/api/schema.d.ts didn't match the backend's schema. It compares the file before
# and after regenerating it (not against the last commit, as CI does), so a schema regenerated
# but not yet committed passes; a stale one is regenerated, and the check says so.
schema:
    #!/usr/bin/env bash
    set -euo pipefail
    cd frontend
    before=$(shasum src/api/schema.d.ts)
    npm run gen:api >/dev/null
    if [[ "$before" != "$(shasum src/api/schema.d.ts)" ]]; then
      echo "src/api/schema.d.ts was stale: regenerated it, review and commit it" >&2
      exit 1
    fi
