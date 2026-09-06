#!/usr/bin/env bash
# Force-restart the Whitespace Tool workflow UI on a fixed port.
#
# Kills whatever is currently holding the port, then starts the server
# fresh from the repo root. Works on Linux and macOS.
#
# Usage:
#   ./run.sh              # serve on 127.0.0.1:8765
#   ./run.sh 9000         # serve on a different port
#   PORT=9000 ./run.sh    # same, via env var
#   PYTHON=.venv/bin/python ./run.sh   # use a specific interpreter
set -euo pipefail

# Resolve to the repo root (the directory this script lives in) so it can be
# run from anywhere.
cd "$(dirname "$0")"

HOST="${HOST:-127.0.0.1}"
PORT="${1:-${PORT:-8765}}"
PYTHON="${PYTHON:-python3}"

echo "Freeing port ${PORT} (if in use)..."
if command -v lsof >/dev/null 2>&1; then
  # Kill any process listening on the port; ignore if none.
  lsof -ti "tcp:${PORT}" | xargs kill -9 2>/dev/null || true
elif command -v fuser >/dev/null 2>&1; then
  fuser -k "${PORT}/tcp" 2>/dev/null || true
else
  echo "  (neither lsof nor fuser found; skipping port kill)"
fi

# Give the OS a moment to release the socket before rebinding.
sleep 1

echo "Starting workflow UI at http://${HOST}:${PORT}/ ..."
exec "${PYTHON}" -m whitespace_tool workflow-ui --host "${HOST}" --port "${PORT}"
