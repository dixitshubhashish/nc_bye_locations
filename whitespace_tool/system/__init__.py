"""System Infrastructure and Medallion Pipeline Module.

Manages storage connection tests, data dataset clearing, background scheduler tasks,
and silver/gold medallion pipeline transformations.
"""
from whitespace_tool.analytics.data_quality import run_quality_checks
from whitespace_tool.system.storage import ping_storage_connection, test_storage_connection, clear_saved_data
from whitespace_tool.system.medallion import build_silver_layer, build_gold_layer, sync_gold_mirror
from whitespace_tool.system.routes import handle_system_get, handle_system_post

__all__ = [
    "run_quality_checks",
    "ping_storage_connection",
    "test_storage_connection",
    "clear_saved_data",
    "build_silver_layer",
    "build_gold_layer",
    "sync_gold_mirror",
    "handle_system_get",
    "handle_system_post",
]


