#!/usr/bin/env python3
"""Frame Pi: share what's on the wall, for the web frame back home (over Tailscale).

    python3 garden/frame/serve.py [--port 8090]

Serves two files and nothing else, read-only:
    /wall.png      the picture the panel last drew (~/garden-data/wall.png)
    /status.json   what the last 15-minute check did (/dev/shm/garden-frame/status.json)

Standard library only, so it costs a few MB of RAM on the Zero. Installed as
garden-frame-web.service by frame/install.sh.
"""
from __future__ import annotations

import argparse
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

DATA = Path.home() / "garden-data"
RUN = Path(os.environ.get("RUNTIME_DIRECTORY", "/dev/shm/garden-frame"))
FILES = {"/wall.png": (DATA / "wall.png", "image/png"),
         "/status.json": (RUN / "status.json", "application/json")}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path, kind = FILES.get(self.path.split("?")[0], (None, None))
        try:
            body = path.read_bytes() if path else None
        except OSError:
            body = None
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # no per-request logging: keeps the journal (and SD) quiet
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8090)
    args = ap.parse_args()
    HTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
