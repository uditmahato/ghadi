"""A health endpoint for the shadow service (issue #34).

One GET, one JSON document, built by a callable the service supplies, served on a
background thread. It exists so that a container health check, a systemd watchdog, or a
person with curl can ask "is it alive and is it seeing data" without reading logs.

``ok`` is false when the feed is stale, the audit chain is broken, or the service has
not decided on a window for too long. A quiet river is not a failure; a quiet feed is.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

__all__ = ["HealthServer"]

Snapshot = Callable[[], dict[str, Any]]


class HealthServer:
    """Serve ``/health`` from a snapshot function on a daemon thread."""

    def __init__(
        self, port: int, snapshot: Snapshot, host: str = "127.0.0.1", enabled: bool = True
    ) -> None:
        self.port = port
        self.snapshot = snapshot
        self.host = host
        self.enabled = enabled
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start serving. Port 0 lets the system pick a free port."""
        if not self.enabled:
            return
        snapshot = self.snapshot

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path.split("?")[0] not in ("/health", "/"):
                    self.send_response(404)
                    self.end_headers()
                    return
                try:
                    body = json.dumps(snapshot(), indent=2, default=str).encode("utf-8")
                    status = 200 if json.loads(body).get("ok") else 503
                except Exception as exc:  # the endpoint must answer even when broken
                    body = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
                    status = 503
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer((self.host, self.port), _Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="ghadi-health", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/health"
