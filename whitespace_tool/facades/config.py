"""Facade module re-exporting configuration logic from whitespace_tool.common.config."""

from whitespace_tool.common.config import load_config, resolve_path

__all__ = ["load_config", "resolve_path"]

