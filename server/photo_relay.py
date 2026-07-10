#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal photo relay used by StackChan Remote MCP."""

from __future__ import annotations

import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value or ""


HOST = _env("STACKCHAN_RELAY_HOST", "0.0.0.0")
PORT = int(_env("STACKCHAN_RELAY_PORT", "18090"))
UPLOAD_TOKEN = _env("STACKCHAN_RELAY_TOKEN", required=True)
MAX_UPLOAD_BYTES = int(_env("STACKCHAN_RELAY_MAX_BYTES", str(2 * 1024 * 1024)))

default_save_dir = str(Path(__file__).resolve().parent)
SAVE_DIR = Path(_env("STACKCHAN_RELAY_SAVE_DIR", default_save_dir))
SAVE_DIR.mkdir(parents=True, exist_ok=True)
LATEST_PATH = SAVE_DIR / "latest.jpg"


class Handler(BaseHTTPRequestHandler):
    server_version = "StackChanPhotoRelay/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"{self.command} {self.path} <- {self.client_address[0]}"
        )

    def _check_token(self) -> bool:
        return self.headers.get("X-Relay-Token", "") == UPLOAD_TOKEN

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/upload":
            self.send_error(404, "Not Found")
            return
        if not self._check_token():
            self.send_error(403, "Bad token")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return

        if length <= 0 or length > MAX_UPLOAD_BYTES:
            self.send_error(413, "Bad length")
            return

        data = self.rfile.read(length)
        temporary_path = LATEST_PATH.with_suffix(".jpg.tmp")
        temporary_path.write_bytes(data)
        os.replace(temporary_path, LATEST_PATH)

        print(f"[{time.strftime('%H:%M:%S')}] saved {LATEST_PATH} ({len(data)} bytes)")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/")

        if path in ("/latest.jpg", "/latest"):
            if not self._check_token():
                self.send_error(403, "Bad token")
                return
            if not LATEST_PATH.exists():
                self.send_error(404, "No photo yet")
                return

            data = LATEST_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Photo-Mtime", str(LATEST_PATH.stat().st_mtime_ns))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"alive")
            return

        self.send_error(404, "Not Found")


if __name__ == "__main__":
    print(f"StackChan photo relay on {HOST}:{PORT}; saving to {LATEST_PATH}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
