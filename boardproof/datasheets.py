"""Fetch and pin the correct datasheet for a part number.

The point is provenance: every layout claim should trace to one immutable PDF,
addressed by hash, that we can re-download and compare later.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REGISTRY_NAME = "registry.json"
MAGIC = b"%PDF"

# Known-good sources, keyed by a part-number prefix. Only patterns we can explain.
SOURCES = (
    ("TMP1", "https://www.ti.com/lit/ds/symlink/{slug}.pdf"),
    ("LM7", "https://www.ti.com/lit/ds/symlink/{slug}.pdf"),
    ("TLV", "https://www.ti.com/lit/ds/symlink/{slug}.pdf"),
)


class DatasheetError(ValueError):
    pass


def _slug(part: str) -> str:
    base = "".join(ch for ch in part.lower() if ch.isalnum())
    return base


def guess_url(part: str) -> str:
    for prefix, template in SOURCES:
        if part.upper().startswith(prefix):
            return template.format(slug=_slug(part))
    raise DatasheetError(
        f"no known datasheet source for {part!r}. Pass --url, or add the part to "
        f"datasheets/{REGISTRY_NAME} once you have verified the document."
    )


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
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise DatasheetError(f"could not download {source}: {exc}") from exc
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
