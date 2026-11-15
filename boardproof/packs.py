"""Vetted rule packs: the compounding asset.

A pack is a reviewed set of constraints for one part, bound to a source document
by hash and to a human by name. CI loads packs, never raw AI proposals.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from functools import lru_cache

from .checks import RULE_TYPES, SEVERITIES
from .provenance import (
    STATUSES,
    Citation,
    has_numeric_limit,
    numeric_fields_for,
)

PACK_SCHEMA_VERSION = 1
KIND = "boardproof-rulepack"


class PackError(ValueError):
    pass


def empty_pack(pack_id: str, part: str = "", manufacturer: str = "", package: str = "") -> dict:
    return {
        "schema_version": PACK_SCHEMA_VERSION,
        "kind": KIND,
        "pack": {
            "id": pack_id,
            "part": part,
            "manufacturer": manufacturer,
            "package": package,
            "status": "proposed",
            "source": {"document": "", "sha256": "", "pages": ""},
            "extracted_by": {"engine": "", "model": None, "at": ""},
            "reviewed_by": None,
            "reviewed_at": None,
            "review_notes": [],
        },
        "net_voltages": {},
        "rules": [],
    }


def _fail(path: Path | str, message: str) -> None:
    raise PackError(f"{path}: {message}")


def validate_pack(pack: Any, path: Path | str = "<memory>", require_vetted: bool = False) -> dict:
    if not isinstance(pack, dict):
        _fail(path, "rule pack must be a JSON object")
    if pack.get("schema_version") != PACK_SCHEMA_VERSION:
        _fail(path, f"requires schema_version: {PACK_SCHEMA_VERSION}")
    if pack.get("kind") != KIND:
        _fail(path, f"requires kind: {KIND!r} (not a BoardProof rule pack)")
    meta = pack.get("pack")
    if not isinstance(meta, dict) or not str(meta.get("id", "")).strip():
        _fail(path, "pack.id is required")
    status = str(meta.get("status", "")).strip()
    if status not in STATUSES:
        _fail(path, f"pack.status must be one of {list(STATUSES)}")
    if require_vetted:
        validate_pack_header(pack, path, require_vetted=True)
    rules = pack.get("rules")
    if not isinstance(rules, list) or not rules:
        _fail(path, "pack must contain a non-empty rules list")
    seen: set[str] = set()
    for index, rule in enumerate(rules, 1):
        if not isinstance(rule, dict):
            _fail(path, f"rule {index} must be an object")
        if str(rule.get("type", "")) not in RULE_TYPES:
            _fail(path, f"rule {index} has unknown type {rule.get('type')!r}")
        if str(rule.get("severity", "error")) not in SEVERITIES:
            _fail(path, f"rule {index} has invalid severity")
        rule_id = str(rule.get("id", "")).strip()
        if not rule_id:
            _fail(path, f"rule {index} requires a stable id")
        if rule_id in seen:
            _fail(path, f"duplicate rule id {rule_id!r}")
        seen.add(rule_id)
        if has_numeric_limit(rule):
            cite = rule.get("citation")
            try:
                Citation.from_dict(cite)
            except Exception as exc:  # noqa: BLE001 - surfaced as config error
                fields = "/".join(numeric_fields_for(rule))
                _fail(
                    path,
                    f"rule {rule_id!r} asserts numeric limit(s) {fields} without a usable "
                    f"citation (page + exact quote): {exc}",
                )
    voltages = pack.get("net_voltages", {})
    if not isinstance(voltages, dict):
        _fail(path, "net_voltages must be an object")
    for name, value in voltages.items():
        if not isinstance(value, (int, float)):
            _fail(path, f"net_voltages[{name!r}] must be a number")
    return pack


def validate_pack_header(pack: dict, path: Path | str, require_vetted: bool = True) -> None:
    meta = pack.get("pack") or {}
    status = str(meta.get("status", "")).strip()
    if require_vetted and status != "vetted":
        raise PackError(
            f"{path}: pack {meta.get('id')!r} is {status!r}, not 'vetted'. Refusing to enforce an "
            "unreviewed proposal. Run: boardproof vet --proposal <file> --reviewer <name>"
        )
    if require_vetted and not str(meta.get("reviewed_by") or "").strip():
        raise PackError(f"{path}: vetted pack requires pack.reviewed_by")


def load_pack(path: Path, require_vetted: bool = False) -> dict:
    """Validate once per (path, mtime, size). Callers get a private deep copy."""
    path = Path(path)
    try:
        stat = path.stat()
    except OSError as exc:
        raise PackError(f"cannot read rule pack {path}: {exc}") from exc
    pack = _load_cached(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    if require_vetted:
        # Cheap re-check; the expensive validation is cached.
        validate_pack_header(pack, path, require_vetted=True)
    return copy.deepcopy(pack)


@lru_cache(maxsize=128)
def _load_cached(path_str: str, _mtime: int, _size: int) -> dict:
    path = Path(path_str)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PackError(f"cannot read rule pack {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PackError(f"rule pack {path} is not valid JSON: {exc}") from exc
    return validate_pack(raw, path, require_vetted=False)


def annotate_rule(rule: dict, pack: dict, pack_path: Path | str) -> dict:
    """Attach read-only provenance so every finding can name its source."""
    meta = pack["pack"]
    enriched = dict(rule)
    enriched["_provenance"] = {
        "pack_id": meta["id"],
        "pack_path": str(pack_path),
        "status": meta.get("status"),
        "part": meta.get("part", ""),
        "reviewed_by": meta.get("reviewed_by"),
        "reviewed_at": meta.get("reviewed_at"),
        "source_document": (meta.get("source") or {}).get("document", ""),
        "source_sha256": (meta.get("source") or {}).get("sha256", ""),
        "citation": rule.get("citation"),
    }
    return enriched


def resolve_config(config: dict, config_path: Path, require_vetted: bool = True) -> dict:
    """Merge referenced packs into the config and return a runnable spec.

    Config-local rules are kept after pack rules so a board may add rules that
    are not part of any published pack.
    """
    if config.get("schema_version") != 1:
        raise PackError("boardproof config requires schema_version: 1")
    references = config.get("packs", []) or []
    if not isinstance(references, list):
        raise PackError("'packs' must be a list of pack paths")
    merged_rules: list[dict] = []
    merged_voltages: dict[str, float] = {}
    loaded: list[dict] = []
    for ref in references:
        entry = ref if isinstance(ref, dict) else {"path": ref}
        if entry.get("enabled", True) is False:
            continue
        raw_path = str(entry.get("path", "")).strip()
        if not raw_path:
            raise PackError("each pack entry requires a 'path'")
        pack_path = (config_path.parent / raw_path).resolve()
        pack = load_pack(pack_path, require_vetted=require_vetted)
        for name, value in (pack.get("net_voltages") or {}).items():
            merged_voltages.setdefault(name, float(value))
        for rule in pack["rules"]:
            merged_rules.append(annotate_rule(rule, pack, pack_path))
        loaded.append({"id": pack["pack"]["id"], "path": raw_path,
                       "status": pack["pack"]["status"],
                       "reviewed_by": pack["pack"].get("reviewed_by"),
                       "rules": len(pack["rules"])})
    for name, value in (config.get("net_voltages") or {}).items():
        merged_voltages[name] = float(value)
    merged_rules.extend(config.get("rules") or [])
    resolved = dict(config)
    resolved["rules"] = merged_rules
    resolved["net_voltages"] = merged_voltages
    resolved["_packs"] = loaded
    return resolved
