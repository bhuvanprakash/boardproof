"""Minimal static server for the artifacts, so the demo can live on Cloud Run.

No framework, no dependencies: one handler, one directory, one health check.
Cloud Run injects PORT; nothing else is required.
"""
from __future__ import annotations

import os
from functools import partial
import json
import os
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import base64


_HITS: dict[str, list[float]] = {}
RATE_LIMIT = int(os.getenv("BOARDPROOF_RATE_LIMIT", "12"))
RATE_WINDOW = float(os.getenv("BOARDPROOF_RATE_WINDOW", "60"))


def allow_request(client: str, limit: int | None = None, window: float | None = None) -> tuple[bool, int]:
    """Token bucket per client. Returns (allowed, seconds-until-a-slot-frees)."""
    limit = limit if limit is not None else RATE_LIMIT
    window = window if window is not None else RATE_WINDOW
    now = time.monotonic()
    bucket = [t for t in _HITS.get(client, []) if now - t < window]
    if len(bucket) >= limit:
        wait = int(window - (now - bucket[0])) + 1
        _HITS[client] = bucket
        return False, wait
    bucket.append(now)
    _HITS[client] = bucket
    return True, 0


class Handler(SimpleHTTPRequestHandler):
    root = Path(".")
    out_dir = Path("artifacts")
    token: str | None = None
    read_only = False

    def _json(self, payload: dict, status: int = 200) -> None:
        body = (json.dumps(payload, indent=2) + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        from .studio import run_action

        permitted, wait = allow_request(self.client_address[0])
        if not permitted:
            self._json({"ok": False, "code": 429,
                        "log": [f"too many requests - try again in {wait}s "
                                f"(limit {RATE_LIMIT} per {int(RATE_WINDOW)}s)"]}, 429)
            return

        if self.path == "/api/upload":
            if Handler.read_only:
                self._json({"ok": False, "log": ["this studio is read-only"]}, 403)
                return
            if Handler.token and self.headers.get("X-BoardProof-Token") != Handler.token:
                self._json({"ok": False, "log": ["missing or wrong action token"]}, 401)
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > 8 * 1024 * 1024:
                self._json({"ok": False, "log": ["file too large"]}, 413)
                return
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._json({"ok": False, "log": ["invalid JSON body"]}, 400)
                return
            from .onboard import UploadError, onboard

            raw_b64 = str(payload.get("content_b64") or "")
            if raw_b64:
                try:
                    content = base64.b64decode(raw_b64)
                except (ValueError, TypeError) as exc:
                    self._json({"ok": False, "log": [f"invalid base64: {exc}"]}, 400)
                    return
            else:
                content = str(payload.get("content") or "").encode("utf-8")
            try:
                result = onboard(self.root, self.out_dir,
                                 str(payload.get("filename") or "board.enet"),
                                 content,
                                 brief=str(payload.get("brief") or ""),
                                 kind=str(payload.get("kind") or ""))
            except UploadError as exc:
                self._json({"ok": False, "log": [str(exc)]}, 200)
                return
            from .dashboard import collect, render

            (self.out_dir / "index.html").write_text(render(collect(self.out_dir)), encoding="utf-8")
            self._json(result)
            return
        if self.path != "/api/run":
            self._json({"ok": False, "log": ["not found"]}, 404)
            return
        if Handler.read_only:
            self._json({"ok": False, "code": 2,
                        "log": ["this studio is read-only; run it without --read-only to act"]}, 403)
            return
        if Handler.token and self.headers.get("X-BoardProof-Token") != Handler.token:
            self._json({"ok": False, "code": 2,
                        "log": ["missing or wrong action token"]}, 401)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json({"ok": False, "code": 2, "log": ["invalid JSON body"]}, 400)
            return
        result = run_action(self.root, self.out_dir, str(payload.get("action", "")),
                            payload.get("config"), str(payload.get("revision", "")))
        self._json(result, 200 if result.get("ok") else 200)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        from .dashboard import collect, render
        from .studio import state

        if self.path in {"/api/state", "/api/state/"}:
            self._json(state(self.root, self.out_dir))
            return
        if self.path in {"/healthz", "/health"}:
            body = b'{"status":"ok","tool":"boardproof"}\n'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if urlparse(self.path).path in {"/", "/index.html"}:
            # Always regenerate: the dashboard is a view of what is on disk.
            self.out_dir.mkdir(parents=True, exist_ok=True)
            configs = state(self.root, self.out_dir)["configs"]
            page = render(collect(self.out_dir), studio=configs,
                          read_only=Handler.read_only)
            if Handler.token and _query_token(self.path) == Handler.token:
                # the token only reaches a page when it was supplied in the URL,
                # so a plain visitor gets a read-only view
                page = page.replace("<script>", "<script>window.BP_TOKEN="
                                    + json.dumps(Handler.token) + ";</script><script>", 1)
            (self.out_dir / "index.html").write_text(page, encoding="utf-8")
            body = page.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, fmt: str, *args) -> None:  # keep CI logs quiet
        print(f"[boardproof] {fmt % args}")


def _query_token(path: str) -> str | None:
    values = parse_qs(urlparse(path).query).get("token")
    return values[0] if values else None


def serve(directory: Path, port: int = 0, host: str = "0.0.0.0",
          root: Path | None = None, token: str | None = None,
          read_only: bool = False) -> ThreadingHTTPServer:
    directory.mkdir(parents=True, exist_ok=True)
    handler = partial(Handler, directory=str(directory))
    handler.func.root = Path(root or Path.cwd()).resolve()
    handler.func.out_dir = Path(directory).resolve()
    Handler.token = token or None
    Handler.read_only = read_only
    httpd = ThreadingHTTPServer((host, port), handler)
    return httpd


def main(directory: Path, port: int | None = None, root: Path | None = None,
         token: str | None = None, read_only: bool = False) -> int:
    resolved = port if port is not None else int(os.getenv("PORT", "8080"))
    httpd = serve(directory, resolved, root=root, token=token, read_only=read_only)
    print(f"BoardProof dashboard on http://localhost:{httpd.server_address[1]}/  (dir: {directory})")
    if Handler.read_only:
        print("  mode: read-only (actions refused)")
    elif Handler.token:
        print("  mode: actions require ?token=... in the URL (or X-BoardProof-Token)")
    else:
        print("  mode: actions open to anyone who can reach this port")
    print("Ctrl-C to stop. /healthz for the Cloud Run probe.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0
