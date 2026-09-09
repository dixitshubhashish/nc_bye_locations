"""Test isolation for the SQLite mirror.

The suite exercises clear_sample_reporting_mirror(), clear_local_cache_db()
and the gold-mirror swap for real. Before this file existed, sqlite_cache's
DB_PATH was a bare constant pointing at .cache/whitespace_cache.db, so those
tests ran against the **live application cache** - a `pytest unit_tests/` run
wiped the running app's reporting mirror, and the dashboard collapsed to
"0 data" with nothing in the server logs to explain it, because the wipes
were not coming from the server. Orphaned pytest processes kept doing it for
hours after the run that spawned them had "finished".

Every test session now gets its own throwaway database.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from pathlib import Path

def pytest_configure(config):
    """Point the cache at a throwaway file before anything imports it.

    sqlite_cache resolves DB_PATH once at import, so this has to run before
    the first test module is collected - which is exactly what
    pytest_configure guarantees. Tests that isolate themselves further with
    patch.object(sqlite_cache, "DB_PATH", tmp) keep working unchanged; this
    only moves the default off the live database.
    """
    if not os.environ.get("WHITESPACE_CACHE_DB"):
        directory = tempfile.mkdtemp(prefix="whitespace-test-cache-")
        os.environ["WHITESPACE_CACHE_DB"] = str(Path(directory) / "test_cache.db")


@pytest.fixture(autouse=True)
def _reset_process_globals():
    """Clear the module-level runtime flags between tests.

    These are process globals that production code sets, so one test can leave
    them set for every test after it. That is not hypothetical: a leftover
    ENRICHMENT_STOP_REQUESTED made build_silver_layer() abort immediately -
    `_enrichment_checkpoint()` raises "Enrichment stopped by user." before the
    first query - so three silver tests failed with rows=0 and zero queries
    recorded, but ONLY when run after the rest of the suite. They passed
    standalone, which is the signature of exactly this problem.
    """
    import whitespace_tool.workflow_server as ws

    def reset():
        for flag in ("ENRICHMENT_STOP_REQUESTED", "SAMPLE_LOAD_CANCELLED", "_SAMPLE_LOAD_RUNNING"):
            event = getattr(ws, flag, None)
            if event is not None:
                event.clear()
        # Plain booleans, not Events. REPORTING_REFRESHING left True by one
        # test makes _refresh_silver_background() return False in the next
        # ("already refreshing"), so it never starts its thread - which is how
        # test_refresh_silver_background_low_priority_thread failed only when
        # run after test_gold_mirror.py.
        ws.REPORTING_REFRESHING = False
        ws.LAST_FOREGROUND_ACTIVITY_AT = 0.0
        ws._LAST_BACKGROUND_INVALIDATION_AT = 0.0
        ws._LAST_SAMPLE_STATUS_RECOUNT_AT = 0.0

    reset()
    yield
    reset()


def test_the_suite_never_opens_the_real_cache_database():
    """A guard on the guard: if this ever points back at .cache/, a test run
    is silently mutating the running app's mirror again."""
    from whitespace_tool import sqlite_cache

    assert "WHITESPACE_CACHE_DB" in os.environ
    assert ".cache/whitespace_cache.db" not in str(sqlite_cache.DB_PATH)
