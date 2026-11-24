"""Minimal HTTP server the alarm clock fetches reply audio from."""

from __future__ import annotations

import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _QuietHandler(SimpleHTTPRequestHandler):
    # The device is the only client; keep the log one line and useful.
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        print(f"[http] {self.address_string()} {fmt % args}", flush=True)


class AudioServer:
    """Serve a directory over HTTP on a background thread."""

    def __init__(self, directory: str | Path, bind: str = "0.0.0.0", port: int = 8000):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        handler = functools.partial(_QuietHandler, directory=str(self.directory))
        self.httpd = ThreadingHTTPServer((bind, port), handler)
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, name="audio-http", daemon=True
        )

    def start(self) -> "AudioServer":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def __enter__(self) -> "AudioServer":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
