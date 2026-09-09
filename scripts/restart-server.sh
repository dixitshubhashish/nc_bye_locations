#!/usr/bin/env bash
# restart-server.sh — stop any running workflow-ui and start a fresh one.
#
# Why this exists: backend (.py) changes are NOT live until the server is
# restarted, and the kill/relaunch/wait/curl dance gets retyped every time.
#
# IMPORTANT — project standing rule: do NOT restart the server unless the user
# explicitly asked. This script only exists so that, when they do ask, it is one
# command. It refuses to run without --yes to make that deliberate.
#
# Side effects: kills processes matching `whitespace_tool.cli`, writes a log to
# .cache/server.log and a pid to .cache/server.pid. It NEVER touches
# .cache/whitespace_cache.db. Server-side sessions live in the process, so any
# cookie jar from scripts/login.sh is invalidated by this restart — re-run
# scripts/login.sh afterwards.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${WORKFLOW_HOST:-127.0.0.1}"
PORT="${WORKFLOW_PORT:-8765}"
LOG="$ROOT/.cache/server.log"
PIDFILE="$ROOT/.cache/server.pid"

if [ "${1:-}" != "--yes" ]; then
  cat >&2 <<MSG
refusing to restart without --yes.

Restarting drops in-flight background jobs and invalidates every server-side
session. The project's standing rule is to restart only when explicitly asked.

  scripts/restart-server.sh --yes
MSG
  exit 2
fi

mkdir -p "$ROOT/.cache"

echo "== stopping existing workflow-ui =="
# -f matches the full command line; the grep -v guards against matching this
# script itself.
old="$(pgrep -f 'whitespace_tool.cli' 2>/dev/null | tr '\n' ' ')"
if [ -n "${old// /}" ]; then
  echo "  killing: $old"
  # shellcheck disable=SC2086
  kill $old 2>/dev/null
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    pgrep -f 'whitespace_tool.cli' >/dev/null 2>&1 || break
    sleep 0.5
  done
  still="$(pgrep -f 'whitespace_tool.cli' 2>/dev/null | tr '\n' ' ')"
  if [ -n "${still// /}" ]; then
    echo "  still alive, sending KILL: $still"
    # shellcheck disable=SC2086
    kill -9 $still 2>/dev/null
    sleep 1
  fi
else
  echo "  none running"
fi

echo "== starting workflow-ui on $HOST:$PORT =="
if [ ! -x .venv/bin/python ]; then
  echo "  .venv/bin/python not found — create the venv and install requirements.txt" >&2
  exit 1
fi

# Appended, not truncated, so a previous crash's log survives.
nohup .venv/bin/python -m whitespace_tool.cli workflow-ui \
  --host "$HOST" --port "$PORT" >>"$LOG" 2>&1 &
pid=$!
echo "$pid" > "$PIDFILE"
echo "  pid $pid  (log: $LOG)"

echo "== waiting for it to answer =="
status=""
for i in $(seq 1 60); do
  status="$(curl -s -o /dev/null -w '%{http_code}' "http://$HOST:$PORT/" 2>/dev/null || true)"
  case "$status" in
    000|"") sleep 1 ;;
    *) break ;;
  esac
done

if ! kill -0 "$pid" 2>/dev/null; then
  echo "  process exited during startup — last 30 log lines:" >&2
  tail -n 30 "$LOG" >&2
  exit 1
fi

echo
echo "PID:    $pid"
echo "URL:    http://$HOST:$PORT/"
echo "STATUS: ${status:-no response}"
echo "LOG:    $LOG"
echo
echo "NOTE: sessions are server-side — any saved cookie jar is now invalid."
echo "      Re-run scripts/login.sh before further authenticated curl calls."

case "$status" in
  2*|3*) exit 0 ;;
  *) exit 1 ;;
esac
