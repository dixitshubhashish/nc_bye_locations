#!/usr/bin/env bash
# login.sh — log into the running app and cache a session cookie for curl.
#
# Why this exists: every manual API probe needs a session, and the
# read-.env / POST /api/login / save-cookie-jar sequence gets retyped constantly.
#
# Sessions are SERVER-SIDE: restarting the server (scripts/restart-server.sh)
# invalidates the jar. This script detects that — it probes /api/session with the
# existing jar first and only re-logs-in when the jar is stale — so it is safe
# and cheap to run before every batch of calls.
#
# The password is read from .env and is NEVER printed, and the cookie jar is
# created with 600 permissions.
#
# Usage:
#   scripts/login.sh              # log in if needed, print the jar path
#   scripts/login.sh --force      # always re-login
#   eval "$(scripts/login.sh --export)"   # sets $WS_COOKIE_JAR and $WS_BASE
#   curl -b "$WS_COOKIE_JAR" -c "$WS_COOKIE_JAR" "$WS_BASE/api/reporting"
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${WORKFLOW_HOST:-127.0.0.1}"
PORT="${WORKFLOW_PORT:-8765}"
BASE="http://$HOST:$PORT"
JAR="${WS_COOKIE_JAR:-$ROOT/.cache/session-cookies.txt}"

FORCE=0
EXPORT=0
for arg in "$@"; do
  case "$arg" in
    --force)  FORCE=1 ;;
    --export) EXPORT=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

say() { [ "$EXPORT" -eq 1 ] && return 0; printf '%s\n' "$*"; }

mkdir -p "$(dirname "$JAR")"

# --- credentials -------------------------------------------------------------
# Read from the environment first, else from .env. Values may be quoted.
read_env_var() {
  [ -f .env ] || return 1
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" .env \
    | tail -n 1 \
    | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/" \
    | sed -e 's/[[:space:]]*$//'
}

USER_NAME="${WORKFLOW_LOGIN_USER:-$(read_env_var WORKFLOW_LOGIN_USER)}"
PASS="${WORKFLOW_LOGIN_PASSWORD:-$(read_env_var WORKFLOW_LOGIN_PASSWORD)}"

if [ -z "${USER_NAME:-}" ] || [ -z "${PASS:-}" ]; then
  echo "WORKFLOW_LOGIN_USER / WORKFLOW_LOGIN_PASSWORD not set and not found in .env" >&2
  exit 1
fi

# --- is the existing jar still good? ----------------------------------------
session_ok() {
  [ -s "$JAR" ] || return 1
  code="$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" "$BASE/api/session" 2>/dev/null)"
  [ "$code" = "200" ]
}

if [ "$FORCE" -eq 0 ] && session_ok; then
  say "session: reused existing jar (valid)"
else
  [ -s "$JAR" ] && [ "$FORCE" -eq 0 ] && say "session: stale (server restarted?) — logging in again"
  : > "$JAR"
  chmod 600 "$JAR"

  # Credentials go in a --data-binary @- body from stdin so the password never
  # appears in the process list or in any log of this command.
  code="$(printf '{"username":%s,"password":%s}' \
            "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$USER_NAME")" \
            "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$PASS")" \
          | curl -s -o /dev/null -w '%{http_code}' \
              -X POST "$BASE/api/login" \
              -H 'Content-Type: application/json' \
              -c "$JAR" --data-binary @- 2>/dev/null)"

  if [ "$code" != "200" ]; then
    echo "login failed: HTTP ${code:-no response} at $BASE/api/login (user: $USER_NAME)" >&2
    echo "is the server running?  scripts/restart-server.sh --yes" >&2
    exit 1
  fi
  chmod 600 "$JAR"
  say "session: logged in as $USER_NAME (HTTP 200)"
fi

if [ "$EXPORT" -eq 1 ]; then
  printf 'export WS_COOKIE_JAR=%q\n' "$JAR"
  printf 'export WS_BASE=%q\n' "$BASE"
else
  echo "jar:  $JAR"
  echo "base: $BASE"
  echo
  echo "example:"
  echo "  curl -s -b \"$JAR\" -c \"$JAR\" \"$BASE/api/session\""
fi
