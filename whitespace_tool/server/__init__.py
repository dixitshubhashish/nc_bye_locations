"""Modular HTTP Server Subpackage for Location Intelligence.

Contains HTTP request handlers, static asset routers, API dispatchers,
and server startup lifecycle functions.
"""
from __future__ import annotations

from whitespace_tool.server.dispatcher import dispatch_get_request, dispatch_post_request
from whitespace_tool.server.handler import _json_response, make_handler
from whitespace_tool.server.runner import serve

__all__ = [
    "serve",
    "make_handler",
    "dispatch_get_request",
    "dispatch_post_request",
    "_json_response",
]

