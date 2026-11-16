"""Small HTTP API for the BoardProof web MVP."""
from __future__ import annotations

import base64
import hmac
import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .serve import allow_request
from .studio import run_action, state


ROOT = Path(os.getenv("BOARDPROOF_ROOT", ".")).resolve()
OUT_DIR = Path(os.getenv("BOARDPROOF_DIR", str(ROOT / "artifacts"))).resolve()
API_TOKEN = os.getenv("BOARDPROOF_API_TOKEN", "")
MAX_BODY_BYTES = 12 * 1024 * 1024
_WORKSPACE_LOCK = threading.Lock()

app = FastAPI(title="BoardProof API", version="0.2.0")
origins = [origin.strip() for origin in os.getenv(
    "BOARDPROOF_WEB_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


class BodySizeLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return

        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_bytes:
                response = JSONResponse({"detail": "request body too large"}, status_code=413)
                await response(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        body = b"".join(chunks)
        delivered = False

        async def replay_body():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay_body, send)


app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_BODY_BYTES)


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(default="board.enet", max_length=255)
    content: str | None = Field(default=None, max_length=8 * 1024 * 1024)
    content_b64: str | None = Field(default=None, max_length=11_184_812)
    brief: str = Field(default="", max_length=20_000)
    kind: str = Field(default="", max_length=40)
    fetch_datasheets: bool = False


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=40)
    config: str | None = Field(default=None, max_length=1024)
    revision: str = Field(default="", max_length=160)
    board: str | None = Field(default=None, max_length=255)


def _guard_api_access(request: Request) -> None:
    if API_TOKEN:
        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {API_TOKEN}"
        if not hmac.compare_digest(supplied, expected):
            raise HTTPException(401, detail="missing or invalid bearer token")


def _guard_mutation(request: Request) -> None:
    _guard_api_access(request)
    client = request.client.host if request.client else "unknown"
    allowed, wait = allow_request(client)
    if not allowed:
        raise HTTPException(429, detail=f"too many requests; try again in {wait}s")


@app.get("/healthz")
def health() -> dict:
    return {"status": "ok", "tool": "BoardProof"}


@app.get("/api/state")
def get_state(request: Request) -> dict:
    _guard_api_access(request)
    with _WORKSPACE_LOCK:
        workspace = state(ROOT, OUT_DIR, config_limit=None)
        files = {path.name for path in OUT_DIR.iterdir()
                 if path.is_file() and path.resolve().parent == OUT_DIR} if OUT_DIR.is_dir() else set()
        boards = []
        for name in sorted(files):
            stem = Path(name).stem
            if not name.endswith(".kicad_pcb"):
                continue
            boards.append({"name": name, **{
                key: filename for key, filename in {
                    "top": f"{stem}.svg", "iso": f"{stem}-3d.svg",
                    "model": f"{stem}-model.json", "gerbers": f"{stem}-gerbers.zip",
                }.items() if filename in files
                    and (key != "gerbers" or (OUT_DIR / filename).stat().st_mtime_ns
                         >= (OUT_DIR / name).stat().st_mtime_ns)
            }})
        preview = OUT_DIR / "preview"
        workspace["boards"] = boards
        workspace["previews"] = sorted(
            path.name for path in preview.iterdir() if path.is_file() and _is_preview(path.name)
            and path.resolve().parent == preview
        ) if preview.is_dir() else []
        workspace["files"] = sorted(name for name in files if name != "index.html"
                                    and Path(name).suffix in {".svg", ".zip", ".kicad_pcb", ".json", ".html"})
        workspace["board"] = Path(workspace["board"]).name if workspace["board"] else None
        return workspace


def _is_preview(filename: str) -> bool:
    return filename in {"schematic.svg", "netlist-schematic.svg"} or (
        filename.startswith("datasheet-") and filename.endswith(".png")
    )


@app.get("/api/artifacts/{filename}")
def get_artifact(filename: str, request: Request):
    _guard_api_access(request)
    output_root = OUT_DIR.resolve()
    path = (output_root / filename).resolve()
    if path.parent != output_root or not path.is_file():
        raise HTTPException(404, detail="artifact not found")
    return _artifact_response(path)


@app.get("/api/previews/{filename}")
def get_preview(filename: str, request: Request):
    _guard_api_access(request)
    directory = OUT_DIR / "preview"
    path = (directory / filename).resolve()
    if not _is_preview(filename) or path.parent != directory or not path.is_file():
        raise HTTPException(404, detail="preview not found")
    return _artifact_response(path)


def _artifact_response(path: Path) -> FileResponse:
    return FileResponse(
        path,
        filename=path.name,
        content_disposition_type="inline" if path.suffix in {".svg", ".png"} else "attachment",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                 "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'"},
    )


@app.post("/api/upload")
def upload(payload: UploadRequest, request: Request) -> dict:
    _guard_mutation(request)
    if payload.content_b64 is not None:
        try:
            content = base64.b64decode(payload.content_b64, validate=True)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, detail="content_b64 must contain valid base64") from exc
    else:
        content = (payload.content or "").encode("utf-8")

    from .onboard import UploadError, onboard

    try:
        with _WORKSPACE_LOCK:
            result = onboard(ROOT, OUT_DIR, payload.filename, content,
                             brief=payload.brief, kind=payload.kind,
                             fetch_datasheets=payload.fetch_datasheets)
    except UploadError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return result


@app.post("/api/run")
def run(payload: RunRequest, request: Request):
    _guard_mutation(request)
    with _WORKSPACE_LOCK:
        result = run_action(ROOT, OUT_DIR, payload.action, payload.config, payload.revision,
                            board=payload.board, render_dashboard=False)
    # Findings (code 1) are a completed check with a failing verdict; code 2 means
    # request/configuration could not be checked and should be an HTTP client error.
    return JSONResponse(result, status_code=422 if result.get("code") == 2 else 200)


def main() -> None:
    import uvicorn

    host = os.getenv("BOARDPROOF_API_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    if host not in {"127.0.0.1", "localhost", "::1"} and not API_TOKEN:
        raise SystemExit("Set BOARDPROOF_API_TOKEN before binding BoardProof API beyond localhost")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
