#!/usr/bin/env bash
# Force-kill whatever is holding the port, then (re)start the workflow UI
# in the current directory. Run this from the repo root.
#
# Usage:
#   ./run.sh            # port 8765
#   ./run.sh 9000       # different port
set -euo pipefail

PORT="${1:-8765}"

echo "Killing anything on port ${PORT}..."
lsof -ti "tcp:${PORT}" | xargs kill -9 2>/dev/null || fuser -k "${PORT}/tcp" 2>/dev/null || true
sleep 1

echo "Starting workflow UI at http://127.0.0.1:${PORT}/ ..."
exec python3 -m whitespace_tool workflow-ui --host 127.0.0.1 --port "${PORT}"

