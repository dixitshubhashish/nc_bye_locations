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
        # REPORTING_REFRESH_PENDING (2026-09-10, refresh-coalescing fix)
        # is the same class of bug: left True by one test, a LATER test's
        # own (unrelated) call to _refresh_silver_background() picks it up
        # and runs an extra pass - which can outlive that test's mock
        # `with patch.object(...)` block and then hit the real, unmocked
        # `bigquery` module from a background thread, surfacing as a
        # confusing `AttributeError` in a totally unrelated test file.
        ws.REPORTING_REFRESH_PENDING = False
        ws.LAST_FOREGROUND_ACTIVITY_AT = 0.0
        ws._LAST_BACKGROUND_INVALIDATION_AT = 0.0
        ws._LAST_SAMPLE_STATUS_RECOUNT_AT = 0.0

    reset()
    yield
    reset()


@pytest.fixture(scope="session", autouse=True)
def _forbid_real_bigquery_client():
    """Guard against a real background thread reaching live BigQuery.

    Root cause (2026-09-10): _refresh_silver_background() (and similar
    fire-and-forget paths, e.g. clear_sample_dataset()'s clear_worker())
    spawn a real background thread. A test that mocks
    _bigquery_client()/build_silver_layer() only inside its own
    `with patch.object(...)` block is safe as long as that thread finishes
    before the block exits - but if the thread runs long (a slow machine, an
    unmocked call several frames deep, a join() timeout that elapses first),
    it keeps running after the block restores the REAL function, and then
    makes a REAL network call to the live warehouse using real credentials.
    Confirmed live via full-suite hangs: `PYTHONFAULTHANDLER=1` + `SIGABRT`
    thread dumps repeatedly showed threads blocked deep inside the real
    build_silver_layer() -> a genuine HTTPS call to Google's BigQuery API,
    which is what actually produced the hangs (a *different* test's setUp()
    doing `thread.join()` on that same leaked thread). Two concrete leaks
    were found and fixed this way (test_csv_workflow.py's unmocked
    save_mapper() calls, test_bigquery_bootstrap.py's
    test_clear_sample_dataset_resets_bronze_and_triggers_refresh) - this
    guard is the backstop for the next one, not yet found.

    This MUST be session-scoped, not function-scoped. A function-scoped
    `monkeypatch.setattr` guard looked sufficient (all 654 tests passed with
    it) but a stress run of the full suite still reproduced the hang WITH
    that guard active: `monkeypatch`'s automatic teardown restores the true
    original function at the end of EVERY single test, and re-applies the
    guard at the start of the next one - so across a 654-test run there are
    653 real (if brief) windows where `_bigquery_client` is the actual,
    network-capable function. A leaked thread's call only has to land in ONE
    of those windows, which is not a negligible chance across an entire
    suite's wall-clock duration. Setting this up once for the whole session
    and never reverting to the real function until the session ends removes
    that gap entirely - a test's own `patch.object(ws, "_bigquery_client",
    ...)` still works exactly as before, patching OVER this guard for the
    duration of its own `with`/setUp block and restoring back to THIS guard
    (never the real function) once that block exits.
    """
    import whitespace_tool.workflow_server as ws

    def _guard(*args, **kwargs):
        raise AssertionError(
            "A test path reached the REAL _bigquery_client() - this must be "
            "mocked (directly, or by mocking whatever leaf function actually "
            "needs a client). This guard exists specifically so a stray "
            "background thread can never make a real BigQuery call during a "
            "test run - see _forbid_real_bigquery_client() in conftest.py."
        )

    original = ws._bigquery_client
    ws._bigquery_client = _guard
    yield
    ws._bigquery_client = original


def test_the_suite_never_opens_the_real_cache_database():
    """A guard on the guard: if this ever points back at .cache/, a test run
    is silently mutating the running app's mirror again."""
    from whitespace_tool import sqlite_cache

    assert "WHITESPACE_CACHE_DB" in os.environ
    assert ".cache/whitespace_cache.db" not in str(sqlite_cache.DB_PATH)
