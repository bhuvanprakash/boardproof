"""Small HTTP API for the BoardProof web MVP."""
from __future__ import annotations

import base64
import hmac
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import datasheets as datasheet_store
from .datasheets import DatasheetError
from .serve import allow_request
from .studio import run_action, state


ROOT = Path(os.getenv("BOARDPROOF_ROOT", ".")).resolve()
OUT_DIR = Path(os.getenv("BOARDPROOF_DIR", str(ROOT / "artifacts"))).resolve()
DATASHEETS_DIR = Path(os.getenv("BOARDPROOF_DATASHEETS_DIR", str(ROOT / "datasheets"))).resolve()
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
    config_path: str | None = Field(default=None, max_length=1024)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=40)
    config: str | None = Field(default=None, max_length=1024)
    revision: str = Field(default="", max_length=160)
    board: str | None = Field(default=None, max_length=255)
    base: str | None = Field(default=None, max_length=255)
    head: str | None = Field(default=None, max_length=255)


class DatasheetFetchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part: str = Field(min_length=1, max_length=80)
    url: str | None = Field(default=None, max_length=600)
    refresh: bool = False


class DatasheetVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part: str = Field(min_length=1, max_length=80)


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
        output_root = OUT_DIR.resolve()
        workspace = state(ROOT, output_root, config_limit=None)
        files = {path.name for path in output_root.iterdir()
                 if path.is_file() and path.resolve().parent == output_root} if output_root.is_dir() else set()
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
                    and (key != "gerbers" or (output_root / filename).stat().st_mtime_ns
                         >= (output_root / name).stat().st_mtime_ns)
            }})
        preview = output_root / "preview"
        workspace["boards"] = boards
        workspace["previews"] = sorted(
            path.name for path in preview.iterdir() if path.is_file() and _is_preview(path.name)
            and path.resolve().parent == preview
        ) if preview.is_dir() else []
        stats = _preview_entries()
        workspace["preview_stats"] = {
            "schematic": sum(1 for item in stats if item["kind"] == "schematic"),
            "datasheets": sum(1 for item in stats if item["kind"] == "datasheet"),
        }
        workspace["files"] = sorted(name for name in files if name != "index.html"
                                    and Path(name).suffix in {".svg", ".zip", ".kicad_pcb", ".json", ".html"})
        workspace["board"] = Path(workspace["board"]).name if workspace["board"] else None
        return workspace


def _is_preview(filename: str) -> bool:
    """Which files under artifacts/preview the API will hand to a browser."""
    if filename in {"schematic.svg", "netlist-schematic.svg"}:
        return True
    if filename.startswith("datasheet-") and filename.endswith(".png"):
        return True
    return Path(filename).suffix in {".svg", ".png"} and "schematic" in filename


_SHEET_STATS = re.compile(r"(\d+)\s+parts?\s*·\s*(\d+)\s+nets?")


def _sheet_stats(path: Path) -> dict | None:
    """Part/net counts printed in a generated sheet header, read without a parser."""
    if path.suffix != ".svg":
        return None
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:4096]
    except OSError:
        return None
    match = _SHEET_STATS.search(head)
    return {"parts": int(match.group(1)), "nets": int(match.group(2))} if match else None


def _preview_entries() -> list[dict]:
    entries = []
    for path in _preview_files():
        stat = path.stat()
        stats = _sheet_stats(path)
        entries.append({
            "name": path.name,
            "kind": "schematic" if "schematic" in path.name else "datasheet",
            "bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                .replace(microsecond=0).isoformat(),
            "parts": stats["parts"] if stats else None,
            "nets": stats["nets"] if stats else None,
        })
    return entries


def _preview_pages() -> dict[str, str]:
    """datasheet slug -> rendered page filename."""
    prefix, suffix = "datasheet-", ".png"
    return {path.name[len(prefix):-len(suffix)]: path.name
            for path in _preview_files() if path.name.startswith(prefix)
            and path.name.endswith(suffix)}


def _preview_files() -> list[Path]:
    directory = OUT_DIR / "preview"
    if not directory.is_dir():
        return []
    resolved = directory.resolve()
    return [path for path in sorted(directory.iterdir())
            if path.is_file() and path.resolve().parent == resolved and _is_preview(path.name)]


@app.get("/api/previews")
def get_previews(request: Request) -> dict:
    """Metadata for every schematic/datasheet preview in the workspace."""
    _guard_api_access(request)
    entries = _preview_entries()
    return {"previews": entries,
            "count": len(entries),
            "schematic": sum(1 for item in entries if item["kind"] == "schematic"),
            "datasheets": sum(1 for item in entries if item["kind"] == "datasheet")}


@app.get("/api/datasheets")
def get_datasheets(request: Request) -> dict:
    """The pinned datasheet registry: hash, source, and rendered page per part."""
    _guard_api_access(request)
    try:
        documents = datasheet_store.list_documents(DATASHEETS_DIR)
    except DatasheetError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    pages = _preview_pages()
    for document in documents:
        document["page"] = pages.get(document["slug"])
        document["pdf"] = f"/api/datasheets/pdf/{document['slug']}"
    return {"documents": documents,
            "directory": str(DATASHEETS_DIR),
            "prefixes": sorted({prefix for prefix, _ in datasheet_store.SOURCES}),
            "max_pdf_mb": datasheet_store.MAX_PDF_BYTES // (1024 * 1024)}


@app.post("/api/datasheets/fetch")
def fetch_datasheet(payload: DatasheetFetchRequest, request: Request) -> dict:
    """Pin one part's datasheet, recording its hash in the registry."""
    _guard_mutation(request)
    try:
        entry = datasheet_store.fetch(payload.part.strip(), DATASHEETS_DIR,
                                      url=payload.url, refresh=payload.refresh)
    except DatasheetError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    slug = datasheet_store.slugify(payload.part)
    return {**entry, "slug": slug, "page": _preview_pages().get(slug),
            "pdf": f"/api/datasheets/pdf/{slug}", "exists": Path(entry["path"]).is_file()}


@app.post("/api/datasheets/verify")
def verify_datasheet(payload: DatasheetVerifyRequest, request: Request) -> dict:
    """Re-hash one stored datasheet against the registry."""
    _guard_api_access(request)
    try:
        return datasheet_store.verify(payload.part.strip(), DATASHEETS_DIR)
    except DatasheetError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@app.post("/api/datasheets/verify-all")
def verify_all_datasheets(request: Request) -> dict:
    """Re-hash every pinned document in one round trip."""
    _guard_api_access(request)
    try:
        results = datasheet_store.verify_all(DATASHEETS_DIR)
    except DatasheetError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return {"results": results, "count": len(results),
            "ok": all(item["ok"] for item in results)}


@app.get("/api/datasheets/pdf/{part}")
def get_datasheet_pdf(part: str, request: Request):
    _guard_api_access(request)
    directory = DATASHEETS_DIR.resolve()
    path = (directory / f"{datasheet_store.slugify(part)}.pdf").resolve()
    if path.parent != directory or not path.is_file():
        raise HTTPException(404, detail="datasheet not found")
    return _artifact_response(path)


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
    directory = OUT_DIR.resolve() / "preview"
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
    if payload.content is not None and payload.content_b64 is not None:
        raise HTTPException(422, detail="provide content or content_b64, not both")
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
                             fetch_datasheets=payload.fetch_datasheets,
                             config_path=payload.config_path)
    except UploadError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return result


@app.post("/api/run")
def run(payload: RunRequest, request: Request):
    _guard_mutation(request)
    with _WORKSPACE_LOCK:
        result = run_action(ROOT, OUT_DIR, payload.action, payload.config, payload.revision,
                            board=payload.board, base=payload.base, head=payload.head,
                            render_dashboard=False)
    # Findings (code 1) are a completed check with a failing verdict; code 2 means
    # request/configuration could not be checked and should be an HTTP client error.
    return JSONResponse(result, status_code=422 if result.get("code") == 2 else 200)


def main() -> None:
    import uvicorn

    host = os.getenv("BOARDPROOF_API_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8193"))
    if host not in {"127.0.0.1", "localhost", "::1"} and not API_TOKEN:
        raise SystemExit("Set BOARDPROOF_API_TOKEN before binding BoardProof API beyond localhost")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
