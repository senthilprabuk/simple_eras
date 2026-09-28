#!/usr/bin/env bash
# Start, check and stop the ERAS app: FastAPI backend on :8000, Next.js frontend on :3000.
# Windows only, run from Git Bash.
# Usage, from anywhere in the repo: .claude/skills/run-simple-eras/app.sh <command>
#
#   start        launch both servers in the background and wait until they answer
#   status       which of :8000 and :3000 are listening, and the backend's /health
#   smoke        sign in through the API as the demo superadmin and read a few screens' data
#   link [MRN]   print today's check-in link for a patient (default FX-01); no login needed
#   logs         the last lines of both server logs
#   stop         kill whatever listens on :8000 and :3000
#   db-status    migrations applied to the database in backend/.env
#   db-build     build an EMPTY database from db/schema and db/seed, then the demo seed
#   reset-demo   rebuild the FX-* demo patients at day 21 and their alerts (undoes test check-ins)
set -euo pipefail

SKILL=$(cd "$(dirname "$0")" && pwd)
ROOT=$(git -C "$SKILL" rev-parse --show-toplevel)
PY="$ROOT/backend/.venv/Scripts/python.exe"
LOGS="${ERAS_LOG_DIR:-${TMPDIR:-/tmp}/run-simple-eras}"
API=http://127.0.0.1:8000
WEB=http://localhost:3000

winpath() { command -v cygpath >/dev/null && cygpath -w "$1" || echo "$1"; }

wait_for() {  # url, seconds
  local end=$((SECONDS + $2))
  until curl -sf -o /dev/null "$1"; do
    if [ $SECONDS -ge $end ]; then
      echo "$1 did not answer within $2s. Logs: $(winpath "$LOGS")" >&2
      return 1
    fi
    sleep 1
  done
}

listeners() {  # port -> PIDs listening on it
  netstat -ano | awk -v port=":$1" '$1 == "TCP" && $4 == "LISTENING" &&
    substr($2, length($2) - length(port) + 1) == port { print $5 }' | sort -u
}

case "${1:-}" in
  start)
    mkdir -p "$LOGS"
    if curl -sf -o /dev/null "$API/health"; then
      echo "backend already running"
    else
      (cd "$ROOT/backend" && nohup "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 \
        >"$LOGS/backend.log" 2>&1 &)
    fi
    if curl -sf -o /dev/null "$WEB/login"; then
      echo "frontend already running"
    else
      (cd "$ROOT/frontend" && nohup npm run dev -- --port 3000 >"$LOGS/frontend.log" 2>&1 &)
    fi
    wait_for "$API/health" 90
    wait_for "$WEB/login" 120
    echo "backend  $API  (docs: $API/docs)"
    echo "frontend $WEB"
    echo "logs     $(winpath "$LOGS")"
    ;;
  status)
    for port in 8000 3000; do echo ":$port listening PIDs: $(listeners $port | tr '\n' ' ')"; done
    curl -s "$API/health" && echo || echo "backend not answering"
    ;;
  smoke)
    curl -sf "$API/health" && echo
    token=$(curl -sf -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
      -d '{"email":"admin@stmarys.org","password":"password123"}' |
      "$PY" -c 'import json, sys; print(json.load(sys.stdin)["access_token"])')
    for path in /api/v1/alerts /api/v1/patients /api/v1/templates /api/v1/whatsapp/account; do
      printf '%-26s %s\n' "$path" \
        "$(curl -s -o /dev/null -w '%{http_code}' "$API$path" -H "Authorization: Bearer $token")"
    done
    ;;
  link)
    "$PY" "$SKILL/checkin_link.py" "${2:-FX-01}"
    ;;
  logs)
    for f in backend frontend; do echo "== $f"; tail -n "${2:-15}" "$LOGS/$f.log" 2>/dev/null || echo "(no log)"; done
    ;;
  stop)
    for port in 8000 3000; do
      for pid in $(listeners $port); do
        taskkill //F //T //PID "$pid" >/dev/null  # doubled slashes, or Git Bash turns them into paths
        echo "stopped PID $pid on :$port"
      done
    done
    ;;
  db-status)
    cd "$ROOT" && "$PY" db/migrate.py --status
    ;;
  db-build)
    "$PY" "$SKILL/db_build.py"
    "$PY" "$ROOT/backend/seed/seed_demo.py" | tail -n 9
    ;;
  reset-demo)
    "$PY" "$SKILL/db_build.py" --fixtures-only
    "$PY" "$ROOT/backend/seed/seed_demo.py" | tail -n 9
    ;;
  *)
    awk 'NR > 1 && !/^#/ { exit } NR > 1' "$0"
    exit 1
    ;;
esac
