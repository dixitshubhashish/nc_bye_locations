"""
Backend Facade Module for Storage Configuration.

Re-exports storage configuration functions and constants from `whitespace_tool.common.storage_config`.
"""

from whitespace_tool.common.storage_config import (
    DEFAULT_STORAGE_CONFIG,
    ENV_FILE,
    load_dotenv,
    load_storage_config,
)

__all__ = [
    "DEFAULT_STORAGE_CONFIG",
    "ENV_FILE",
    "load_dotenv",
    "load_storage_config",
]

