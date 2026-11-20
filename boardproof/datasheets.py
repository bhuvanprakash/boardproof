"""Fetch and pin the correct datasheet for a part number.

The point is provenance: every layout claim should trace to one immutable PDF,
addressed by hash, that we can re-download and compare later.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REGISTRY_NAME = "registry.json"
MAGIC = b"%PDF"
MAX_PDF_BYTES = 64 * 1024 * 1024

# Known-good sources, keyed by a part-number prefix. Only patterns we can explain:
# TI serves symlink URLs named after the part, ST after the lowercased part, NXP
# after the part for most data sheets. A miss raises rather than guessing.
SOURCES = (
    ("TMP", "https://www.ti.com/lit/ds/symlink/{slug}.pdf"),
    ("LM7", "https://www.ti.com/lit/ds/symlink/{slug}.pdf"),
    ("TLV", "https://www.ti.com/lit/ds/symlink/{slug}.pdf"),
    ("TPS", "https://www.ti.com/lit/ds/symlink/{slug}.pdf"),
    ("OPA", "https://www.ti.com/lit/ds/symlink/{slug}.pdf"),
    ("ADS", "https://www.ti.com/lit/ds/symlink/{slug}.pdf"),
    ("SN7", "https://www.ti.com/lit/ds/symlink/{slug}.pdf"),
    ("STM", "https://www.st.com/resource/en/datasheet/{slug}.pdf"),
    ("LSM", "https://www.st.com/resource/en/datasheet/{slug}.pdf"),
    ("LIS", "https://www.st.com/resource/en/datasheet/{slug}.pdf"),
    ("LPS", "https://www.st.com/resource/en/datasheet/{slug}.pdf"),
    ("S32", "https://www.nxp.com/docs/en/data-sheet/{slug}.pdf"),
    ("PCA", "https://www.nxp.com/docs/en/data-sheet/{slug}.pdf"),
    ("K22", "https://www.nxp.com/docs/en/data-sheet/{slug}.pdf"),
)


class DatasheetError(ValueError):
    pass


def slugify(part: str) -> str:
    """The registry/file key for a part number: lowercase, alphanumeric only."""
    return "".join(ch for ch in part.lower() if ch.isalnum())


_slug = slugify


def guess_url(part: str) -> str:
    for prefix, template in SOURCES:
        if part.upper().startswith(prefix):
            return template.format(slug=_slug(part))
    raise DatasheetError(
        f"no known datasheet source for {part!r}. Pass --url, or add the part to "
        f"datasheets/{REGISTRY_NAME} once you have verified the document."
    )


def _validate_public_pdf_url(url: str) -> str:
    """Reject local or non-HTTP targets before a user supplied URL is fetched."""
    if not isinstance(url, str) or not url.strip() or len(url) > 2048:
        raise DatasheetError("enter a valid public HTTP(S) PDF URL")
    candidate = url.strip()
    if any(ord(char) < 32 for char in candidate):
        raise DatasheetError("datasheet URL contains control characters")
    try:
        parsed = urllib.parse.urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise DatasheetError("datasheet URL is malformed") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise DatasheetError("datasheet URL must use public HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise DatasheetError("datasheet URL must not contain credentials")
    expected_port = 443 if scheme == "https" else 80
    if port is not None and port != expected_port:
        raise DatasheetError("datasheet URL must use the standard HTTP(S) port")

    host = parsed.hostname.rstrip(".")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            records = socket.getaddrinfo(host, expected_port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise DatasheetError("datasheet URL host could not be resolved") from exc
        addresses = []
        for record in records:
            try:
                addresses.append(ipaddress.ip_address(record[4][0].split("%", 1)[0]))
            except (IndexError, ValueError):
                continue
    if not addresses or any(not address.is_global for address in addresses):
        raise DatasheetError("datasheet URL must resolve only to public internet addresses")
    return candidate


class _PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, newurl):
        _validate_public_pdf_url(newurl)
        return super().redirect_request(request, file, code, message, headers, newurl)


def _open_public_url(request: urllib.request.Request, timeout: int):
    _validate_public_pdf_url(request.full_url)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _PublicRedirectHandler())
    return opener.open(request, timeout=timeout)


def _registry_path(directory: Path) -> Path:
    return Path(directory) / REGISTRY_NAME


def read_registry(directory: Path) -> dict:
    path = _registry_path(directory)
    if not path.is_file():
        return {"schema_version": 1, "documents": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasheetError(f"{path} is not valid JSON: {exc}") from exc
    data.setdefault("documents", {})
    return data


def write_registry(directory: Path, registry: dict) -> None:
    path = _registry_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(Path(path).read_bytes())
    return digest.hexdigest()


def fetch(part: str, directory: Path = Path("datasheets"), url: str | None = None,
          refresh: bool = False) -> dict:
    """Download (or reuse) a datasheet and record it in the registry."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    registry = read_registry(directory)
    target = directory / f"{_slug(part)}.pdf"
    entry = registry["documents"].get(_slug(part), {})
    source = url or entry.get("url") or guess_url(part)

    if target.is_file() and not refresh:
        digest = sha256(target)
        if entry.get("sha256") and entry["sha256"] != digest:
            raise DatasheetError(
                f"{target} no longer matches the hash recorded for {part}; a datasheet changed "
                "under a vetted rule pack. Re-vet before continuing.")
        entry.update({"part": part, "path": str(target), "sha256": digest,
                      "status": "cached"})
        registry["documents"][_slug(part)] = entry
        write_registry(directory, registry)
        return entry

    request = urllib.request.Request(source, headers={"User-Agent": "BoardProof/0.2"})
    try:
        with _open_public_url(request, timeout=60) as response:
            declared = response.headers.get("Content-Length") or ""
            if declared.isdigit() and int(declared) > MAX_PDF_BYTES:
                raise DatasheetError(
                    f"{source} declares {int(declared) // (1024 * 1024)} MB, over the "
                    f"{MAX_PDF_BYTES // (1024 * 1024)} MB limit; refusing to store it")
            payload = response.read(MAX_PDF_BYTES + 1)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise DatasheetError(f"could not download {source}: {exc}") from exc
    if len(payload) > MAX_PDF_BYTES:
        raise DatasheetError(f"{source} is larger than {MAX_PDF_BYTES // (1024 * 1024)} MB")
    if not payload.startswith(MAGIC):
        raise DatasheetError(
            f"{source} did not return a PDF (got {payload[:16]!r}); refusing to store it")
    target.write_bytes(payload)
    entry = {
        "part": part,
        "path": str(target),
        "url": source,
        "sha256": sha256(target),
        "bytes": len(payload),
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "downloaded",
    }
    registry["documents"][_slug(part)] = entry
    write_registry(directory, registry)
    return entry


def lookup(part: str, directory: Path = Path("datasheets")) -> dict:
    entry = read_registry(Path(directory))["documents"].get(_slug(part))
    if not entry:
        raise DatasheetError(
            f"no datasheet recorded for {part!r}; run: boardproof datasheet fetch --part {part}")
    path = Path(entry["path"])
    if not path.is_file():
        raise DatasheetError(f"{path} is recorded for {part} but missing on disk; re-fetch it")
    return entry


def verify(part: str, directory: Path = Path("datasheets")) -> dict:
    entry = lookup(part, directory)
    actual = sha256(Path(entry["path"]))
    return {"part": part, "path": entry["path"], "url": entry.get("url"),
            "expected_sha256": entry.get("sha256"), "actual_sha256": actual,
            "ok": actual == entry.get("sha256")}


def list_documents(directory: Path = Path("datasheets")) -> list[dict]:
    """Every registry entry, annotated with what is actually on disk right now.

    A registry can outlive its file (or point at a moved one), so the API reports
    presence instead of trusting the recorded path.
    """
    directory = Path(directory)
    documents = []
    for key, entry in sorted(read_registry(directory)["documents"].items()):
        record = dict(entry)
        record["slug"] = key
        record.setdefault("part", key)
        path = Path(record.get("path") or "")
        if not path.is_file():
            fallback = directory / f"{key}.pdf"
            path = fallback if fallback.is_file() else path
        present = path.is_file()
        record["exists"] = present
        record["path"] = str(path) if present else record.get("path") or ""
        record["bytes"] = path.stat().st_size if present else None
        record["hash_ok"] = bool(present and record.get("sha256")
                                 and sha256(path) == record["sha256"])
        documents.append(record)
    return documents


def verify_all(directory: Path = Path("datasheets")) -> list[dict]:
    """Re-hash every stored document; a drift is reported, never repaired."""
    results = []
    for record in list_documents(directory):
        results.append({"part": record["part"], "slug": record["slug"],
                        "path": record["path"], "ok": record["hash_ok"],
                        "expected_sha256": record.get("sha256"),
                        "note": "" if record["exists"] else "file missing on disk"})
    return results
