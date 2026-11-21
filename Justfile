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

# Fails when src/api/schema.d.ts doesn't match the backend's schema (run `npm run gen:api`).
schema:
    cd frontend && npm run gen:api >/dev/null
    git diff --exit-code -- frontend/src/api/schema.d.ts
