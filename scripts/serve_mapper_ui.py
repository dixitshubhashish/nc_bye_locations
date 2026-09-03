from __future__ import annotations

import argparse
import http.server
import socketserver
from pathlib import Path


class MapperUiHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path("ui").resolve()), **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local source mapper UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    with socketserver.TCPServer((args.host, args.port), MapperUiHandler) as httpd:
        print(f"Mapper UI running at http://{args.host}:{args.port}/mapper.html")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
