#!/usr/bin/env bash
# run-tests.sh — run the unit test suite the way this project expects.
#
# Why this exists: the flags matter and get forgotten.
#   -p no:cacheprovider  keeps pytest from littering .pytest_cache
#   unit_tests/          scopes the run; the suite lives only here
#
# SAFETY — do not bypass this: unit_tests/conftest.py sets WHITESPACE_CACHE_DB to
# a throwaway temp file in pytest_configure, BEFORE any test module imports
# sqlite_cache (which resolves DB_PATH at import time). Without it a pytest run
# wipes the RUNNING APP's reporting mirror at .cache/whitespace_cache.db — the
# suite calls the real clear/mirror-swap functions. That actually happened; see
# BUG-42 in docs/bug_tracker.md. This script deliberately does NOT set or unset
# WHITESPACE_CACHE_DB, so conftest stays in charge.
#
# Any extra arguments are passed straight to pytest, e.g.
#   scripts/run-tests.sh unit_tests/test_geo_enrichment.py
#   scripts/run-tests.sh -k gold_mirror
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"

if [ "$#" -gt 0 ]; then
  TARGETS=("$@")
else
  TARGETS=(unit_tests/)
fi

echo "== $PY -m pytest ${TARGETS[*]} -q -p no:cacheprovider =="
echo "   (live mirror .cache/whitespace_cache.db is protected by unit_tests/conftest.py)"
echo

"$PY" -m pytest "${TARGETS[@]}" -q -p no:cacheprovider
rc=$?

echo
if [ "$rc" -eq 0 ]; then
  echo "TESTS PASSED (exit 0)"
else
  echo "TESTS FAILED (exit $rc)"
fi
exit "$rc"
