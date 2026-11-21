#!/usr/bin/env bash
# PreToolUse guard for Bash: the few commands that can do real harm in this repo.
#   - staging or committing a database / backend/local-prod (real student data)
#   - stopping the developer's own servers (backend on 8000, Vite on 5173)
#   - pushing (the developer pushes; an agent asks first)
set -euo pipefail

cmd=$(jq -r '.tool_input.command // ""')

decide() { # decide <deny|ask> <reason>
  jq -n --arg d "$1" --arg r "$2" \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: $d, permissionDecisionReason: $r}}'
  exit 0
}

has() { grep -Eq -- "$1" <<<"$cmd"; }

DATA='\.db(-wal|-shm)?\b|\.sqlite3\b|local-prod'

if has '\bgit\b.*\b(add|stage)\b' && has "$DATA"; then
  decide deny "Databases and backend/local-prod hold real student data and are never staged."
fi

if has '\bgit\b.*\bcommit\b'; then
  staged=$(git -C "${CLAUDE_PROJECT_DIR:-.}" diff --cached --name-only 2>/dev/null | grep -E "$DATA" || true)
  if [[ -n "$staged" ]]; then
    decide deny "Staged student data, unstage it first: ${staged//$'\n'/, }"
  fi
fi

if { has '\b(kill|pkill|killall|fuser)\b' && has '\b(8000|5173)\b'; } \
  || has '\b(pkill|killall)\b.*\b(uvicorn|fastapi|vite|node|python)([[:space:]"'\'']|$)'; then
  decide deny "Ports 8000/5173 are the developer's own servers. Stop only processes you started, by PID."
fi

if has '\bgit\b.*\bpush\b'; then
  decide ask "The developer usually pushes; confirm this push."
fi

exit 0
