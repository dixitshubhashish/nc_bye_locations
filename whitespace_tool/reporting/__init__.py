"""Reporting module (backend).

Folder-wise segregation of the reporting feature's backend concerns:

- ``helpers``  - pure, dependency-free reporting helpers (metric math,
  coordinate/brand/demographic predicates, param parsing).
- ``routes``   - the reporting HTTP API dispatch (``/api/reporting``,
  ``/api/geo/options``, ``/api/zips/search``, ``/api/sample/*``,
  ``/api/reporting/refresh``).
- ``api``      - the public reporting compute surface (re-exported from
  :mod:`whitespace_tool.workflow_server`).

This package is intentionally free of eager ``workflow_server`` imports so it
can be imported *during* ``workflow_server`` module load without a cycle.
Import :mod:`whitespace_tool.reporting.api` explicitly when you need the
compute functions.
"""
