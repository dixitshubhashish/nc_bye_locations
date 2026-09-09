#!/usr/bin/env bash
# check-syntax.sh — the project's pre-commit verification pass, in one command.
#
# Why this exists: the same block of `node --check` / `py_compile` / `git diff
# --check` calls is retyped in every session (it is documented in CLAUDE.md and
# codex.md). There is no bundler, so `node --check` is the only syntax gate the
# UI files get.
#
# Read-only: compiles and lints, writes nothing, commits nothing.
# Exit code 0 = everything parsed; non-zero = at least one failure (all checks
# are run regardless, so you see every problem in one pass).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fails=0
ok()   { printf '  ok   %s\n' "$1"; }
bad()  { printf '  FAIL %s\n' "$1"; fails=$((fails + 1)); }

JS_FILES="
ui/js/mapper.js
ui/js/reporting.js
ui/js/review.js
ui/js/templates.js
ui/js/common.js
ui/js/login.js
ui/reporting-tabs.js
"

PY_FILES="
whitespace_tool/workflow_server.py
whitespace_tool/sqlite_cache.py
whitespace_tool/geo_enrichment.py
whitespace_tool/warehouse_bigquery.py
whitespace_tool/normalization.py
"

echo "== node --check (UI) =="
for f in $JS_FILES; do
  if [ ! -f "$f" ]; then bad "$f (missing)"; continue; fi
  if node --check "$f" >/dev/null 2>&1; then ok "$f"; else bad "$f"; node --check "$f" 2>&1 | sed 's/^/       /'; fi
done

echo "== inline <script> blocks in ui/integrations.html =="
# integrations.html carries inline scripts that no other check covers. Each
# block is extracted to a temp file and parsed on its own, so a line number in a
# failure is relative to that block.
if [ -f ui/integrations.html ]; then
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT
  python3 - "$tmpdir" <<'PY'
import re, sys, pathlib
out = pathlib.Path(sys.argv[1])
html = pathlib.Path("ui/integrations.html").read_text(encoding="utf-8", errors="replace")
n = 0
for m in re.finditer(r"<script([^>]*)>(.*?)</script>", html, re.S | re.I):
    attrs, body = m.group(1), m.group(2)
    if re.search(r"\bsrc\s*=", attrs, re.I):
        continue                       # external file, nothing inline to parse
    if re.search(r'type\s*=\s*["\']?(?!text/javascript|module|application/javascript)', attrs, re.I):
        continue                       # templates / JSON blocks are not JS
    if not body.strip():
        continue
    n += 1
    line = html[: m.start()].count("\n") + 1
    (out / f"block{n:02d}_line{line}.js").write_text(body, encoding="utf-8")
# (blocks written to the temp dir; the loop below reports each one)
PY
  found=0
  for f in "$tmpdir"/*.js; do
    [ -e "$f" ] || continue
    found=1
    label="integrations.html $(basename "$f" .js)"
    if node --check "$f" >/dev/null 2>&1; then ok "$label"; else bad "$label"; node --check "$f" 2>&1 | sed 's/^/       /'; fi
  done
  [ "$found" = 0 ] && echo "  (no inline script blocks found)"
else
  bad "ui/integrations.html (missing)"
fi

echo "== python3 -m py_compile (backend) =="
for f in $PY_FILES; do
  if [ ! -f "$f" ]; then bad "$f (missing)"; continue; fi
  if python3 -m py_compile "$f" >/dev/null 2>&1; then ok "$f"; else bad "$f"; python3 -m py_compile "$f" 2>&1 | sed 's/^/       /'; fi
done

echo "== git diff --check (whitespace / conflict markers) =="
if git diff --check; then ok "git diff --check"; else bad "git diff --check"; fi

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit "$fails"
