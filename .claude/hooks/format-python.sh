#!/usr/bin/env bash
# PostToolUse on Edit/Write: ruff-format the backend Python file just written, so CI's
# `ruff format --check` never fails on an agent's edit. Formatting only: `ruff check --fix`
# would delete an import added a step before the code that uses it.
set -uo pipefail

file=$(jq -r '.tool_input.file_path // ""')
root="${CLAUDE_PROJECT_DIR:-.}"

case "$file" in
  "$root"/backend/*.py) uv run --project "$root/backend" ruff format --quiet --force-exclude "$file" ;;
esac
exit 0
