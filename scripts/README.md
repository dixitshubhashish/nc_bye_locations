# scripts/

Wrappers for the command blocks this project runs over and over. Each script
has a header comment explaining what it does and why it exists. None of them
commit, and none of them ever delete or overwrite `.cache/whitespace_cache.db`.

| Script | What it does |
|---|---|
| `check-syntax.sh` | The pre-commit verification pass: `node --check` on every `ui/**` JS file and on each inline `<script>` in `integrations.html`, `py_compile` on the five main backend modules, then `git diff --check`. Read-only; exits non-zero on any failure. |
| `restart-server.sh --yes` | Kills any `whitespace_tool.cli` process, relaunches `workflow-ui` detached (log `.cache/server.log`, pid `.cache/server.pid`), waits for it to answer, prints PID + HTTP status. Requires `--yes` — the project's standing rule is to restart only when explicitly asked. |
| `login.sh` | Reads `WORKFLOW_LOGIN_USER`/`WORKFLOW_LOGIN_PASSWORD` from `.env`, POSTs `/api/login`, saves a 600-perm cookie jar at `.cache/session-cookies.txt`. Reuses a valid jar and re-logs-in automatically when a restart has invalidated it. Never prints the password. `eval "$(scripts/login.sh --export)"` sets `$WS_COOKIE_JAR` and `$WS_BASE` for follow-up `curl`. |
| `run-tests.sh [pytest args]` | `pytest unit_tests/ -q -p no:cacheprovider`. Leaves `WHITESPACE_CACHE_DB` to `unit_tests/conftest.py`, which is what keeps the suite off the live SQLite mirror (see BUG-42). |

Sessions are server-side, so `restart-server.sh` invalidates any saved cookie
jar — run `login.sh` again after a restart (it detects this on its own).

The canonical prose description of the verification pass lives in `CLAUDE.md`
and `codex.md`; these scripts are the executable form of it.
