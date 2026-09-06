"""Facade module re-exporting file I/O operations from whitespace_tool.common.io."""

from whitespace_tool.common.io import write_csv, write_demographics_csv, write_json

__all__ = ["write_csv", "write_demographics_csv", "write_json"]

