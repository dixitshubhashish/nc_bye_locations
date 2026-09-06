"""Facade module re-exporting field registry loader from whitespace_tool.common.field_registry."""

from whitespace_tool.common.field_registry import load_field_registry, REGISTRY_PATH

__all__ = ["load_field_registry", "REGISTRY_PATH"]

