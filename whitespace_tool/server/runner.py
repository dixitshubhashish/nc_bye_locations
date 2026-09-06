"""Server execution and lifecycle runner module.

Provides ``serve()`` and server lifecycle controls for launching the Workflow UI HTTP server.
"""
from __future__ import annotations

import logging
from pathlib import Path
import socketserver

from whitespace_tool.server.handler import make_handler
from whitespace_tool.system.scheduler import _start_silver_gold_scheduler

LOGGER = logging.getLogger("whitespace_tool.workflow_server")


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    ui_dir = repo_root / "ui"
    if not ui_dir.exists():
        ui_dir = Path("ui").resolve()
    handler = make_handler(ui_dir)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    _start_silver_gold_scheduler()
    with socketserver.ThreadingTCPServer((host, port), handler) as httpd:
        print(f"Workflow UI running at http://{host}:{port}/")
        httpd.serve_forever()

