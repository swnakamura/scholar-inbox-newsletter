"""Serve newsletter.html and proxy rating clicks to Scholar Inbox.

Why this exists: the rating endpoint at api.scholar-inbox.com sets its
session cookie with `SameSite=Lax` (and no `Domain`), so a browser opening
newsletter.html as `file://` cannot include credentials in cross-origin
fetches — the click silently fails with HTTP 401. Workaround: serve the
HTML from a localhost origin and proxy the rating call through this server,
which holds the scholarinboxcli session (authenticated server-side, no
SameSite issue).

Usage:
    uv run python scripts/serve.py [HTML_PATH] [--port 8765] [--no-browser]

Routes:
    GET  /                   → newsletter.html (HTML_PATH, default ./newsletter.html)
    POST /api/rate           → forwards to /api/make_rating/ with the scholarinboxcli cookie
                                body: {"rating": -1|0|1, "id": "<paper_id>"}
                                returns: {"ok": true} or {"ok": false, "error": "..."}

Stop with Ctrl-C.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Reuse scholarinboxcli's authenticated client for the proxy.
from scholarinboxcli.api.client import ApiError, ScholarInboxClient

# Reuse the auth bootstrap from fetch_digest so a missing magic link is
# surfaced the same way here.
sys.path.insert(0, str(Path(__file__).parent))
from fetch_digest import ensure_auth  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    server_version = "scholar-inbox-newsletter/0.2"
    html_path: Path = Path("newsletter.html")
    client: ScholarInboxClient | None = None

    def log_message(self, fmt, *args):  # quieter access log
        sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._serve_file(self.html_path, "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/rate":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(length) if length else b""
            payload = json.loads(body or "{}")
            rating = int(payload.get("rating"))
            paper_id = str(payload.get("id") or "").strip()
            if rating not in (-1, 0, 1) or not paper_id:
                self._json(400, {"ok": False, "error": "bad payload"})
                return
        except (ValueError, json.JSONDecodeError) as e:
            self._json(400, {"ok": False, "error": f"bad payload: {e}"})
            return

        assert self.client is not None
        try:
            self.client._request(
                "POST", "/api/make_rating/",
                json={"rating": rating, "id": paper_id},
            )
            self._json(200, {"ok": True})
        except ApiError as e:
            sys.stderr.write(f"rating proxy: ApiError {e.status_code} {e.message}\n")
            self._json(e.status_code or 502, {"ok": False, "error": str(e.message)})

    def _serve_file(self, path: Path, content_type: str):
        if not path.exists():
            self.send_error(404, f"not found: {path}")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("html", nargs="?", default="newsletter.html")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    html_path = Path(args.html).resolve()
    if not html_path.exists():
        sys.stderr.write(f"missing {html_path}; run render_html.py first.\n")
        raise SystemExit(2)

    ensure_auth()
    _Handler.html_path = html_path
    _Handler.client = ScholarInboxClient()

    srv = ThreadingHTTPServer((args.host, args.port), _Handler)
    url = f"http://{args.host}:{args.port}/"
    sys.stderr.write(f"serving {html_path.name} at {url}  (Ctrl-C to stop)\n")

    if not args.no_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\nstopping.\n")
        srv.shutdown()


if __name__ == "__main__":
    main()
