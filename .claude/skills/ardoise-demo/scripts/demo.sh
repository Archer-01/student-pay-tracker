#!/usr/bin/env bash
# A throwaway Ardoise with demo data, on scratch ports. Never touches the developer's own servers
# (8000, 5173) or their databases: everything lives under <dir>.
#
#   demo.sh start <dir> [dev|prod]   API on $API_PORT (8001), app on $WEB_PORT (5174 dev, 5175 prod)
#   demo.sh stop <dir>               stops what start started, by PID
#   demo.sh status <dir>
#
# dev  = Vite dev server (fast, no service worker).
# prod = a production build served by `vite preview`: the service worker and offline mode work.
# Sign in as aymen / demo-pass-123. Run two demos side by side with other ports and dirs.
set -euo pipefail

cmd=${1:?usage: demo.sh start|stop|status <dir> [dev|prod]}
dir=${2:?usage: demo.sh start|stop|status <dir> [dev|prod]}
mode=${3:-dev}
here=$(cd "$(dirname "$0")" && pwd)
root=$(git -C "$here" rev-parse --show-toplevel)
api_port=${API_PORT:-8001}
web_port=${WEB_PORT:-$([[ $mode == prod ]] && echo 5175 || echo 5174)}

for port in "$api_port" "$web_port"; do
  if [[ $port == 8000 || $port == 5173 ]]; then
    echo "refusing port $port: it belongs to the developer's own servers" >&2
    exit 1
  fi
done

mkdir -p "$dir"
dir=$(cd "$dir" && pwd)
export DATABASE_URL="sqlite:///$dir/db/central.db" COOKIE_SECURE=false SCHOOL_SHARE_PERCENT=25

wait_for() { # wait_for <url> <log>
  for _ in $(seq 1 60); do
    curl -sf -o /dev/null "$1" && return 0
    sleep 0.5
  done
  echo "not answering: $1 (see $2)" >&2
  exit 1
}

running() { [[ -f $1 ]] && kill -0 "$(cat "$1")" 2>/dev/null; }

case $cmd in
  start)
    fresh=false
    if [[ ! -f $dir/db/central.db ]]; then
      fresh=true
      mkdir -p "$dir/db"
      (cd "$root/backend" && uv run alembic upgrade head \
        && uv run ardoise users add aymen --name "Aymen Bekkaoui" --password demo-pass-123) \
        >"$dir/setup.log" 2>&1 || { echo "setup failed, see $dir/setup.log" >&2; exit 1; }
    fi

    # Each server is started detached from this script's output (</dev/null, its own log), so a
    # caller piping this script doesn't wait on it; $! is the server's own process.
    if ! running "$dir/api.pid"; then
      (
        cd "$root/backend"
        nohup uv run uvicorn app.main:app --host 127.0.0.1 --port "$api_port" \
          </dev/null >"$dir/api.log" 2>&1 &
        echo $! >"$dir/api.pid"
      )
    fi
    wait_for "http://127.0.0.1:$api_port/health" "$dir/api.log"
    if $fresh; then
      API="http://127.0.0.1:$api_port/api/v1" uv run --no-project python "$here/seed.py"
      # Seeded through the API, every payment was "recorded" just now, which floods Accueil's
      # "Encaissé aujourd'hui". Date each one when it was paid, as if typed in on the day.
      sqlite3 "$dir/db/tenant-1.db" "UPDATE payment SET created_at = paid_date || ' 18:00:00';"
    fi

    if ! running "$dir/web.pid"; then
      if [[ $mode == prod ]]; then
        (cd "$root/frontend" && npx vite build --outDir "$dir/dist" --emptyOutDir >"$dir/build.log" 2>&1)
      fi
      (
        cd "$root/frontend"
        nohup node "$here/web.mjs" "$mode" "$web_port" "$api_port" "$dir" \
          </dev/null >"$dir/web.log" 2>&1 &
        echo $! >"$dir/web.pid"
      )
    fi
    wait_for "http://127.0.0.1:$web_port/" "$dir/web.log"
    echo "Ardoise ($mode): http://127.0.0.1:$web_port  (aymen / demo-pass-123), API :$api_port, files in $dir"
    ;;
  stop)
    for name in web api; do
      if running "$dir/$name.pid"; then
        pid=$(cat "$dir/$name.pid")
        # uv and nohup start children: stop the whole group the PID leads, then the PID itself.
        pkill -TERM -P "$pid" 2>/dev/null || true
        kill "$pid" 2>/dev/null || true
      fi
      rm -f "$dir/$name.pid"
    done
    echo "stopped (data kept in $dir/db; delete the folder for a fresh seed)"
    ;;
  status)
    for name in api web; do
      if running "$dir/$name.pid"; then echo "$name: running (pid $(cat "$dir/$name.pid"))"; else echo "$name: stopped"; fi
    done
    ;;
  *)
    echo "usage: demo.sh start|stop|status <dir> [dev|prod]" >&2
    exit 1
    ;;
esac
