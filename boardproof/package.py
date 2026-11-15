"""Datasheet-derived package geometry, and land-pattern verification.

This is what closes the "land patterns are approximate" gap: the datasheet states
the pitch and the pad sizes, the library states what we generate, and the check
compares them. If they disagree, the board is wrong before copper is poured.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .footprints import LIBRARY, LandPattern, outline_of
from .provenance import STATUSES, Citation, utc_now

PACKAGE_KIND = "boardproof-package"
TOLERANCE_MM = 0.06          # land-pattern tolerance against the drawing nominals
PAD_TOLERANCE_MM = 0.12


class PackageError(ValueError):
    pass


def empty_spec(pack_id: str, part: str = "", package: str = "") -> dict:
    return {
        "schema_version": 1,
        "kind": PACKAGE_KIND,
        "package": {
            "id": pack_id,
            "part": part,
            "package": package,
            "status": "proposed",
            "reviewed_by": None,
            "reviewed_at": None,
            "source": {"document": "", "url": "", "sha256": ""},
            "extracted_by": {"engine": "", "at": ""},
        },
        "geometry": {
            "pin_count": None,
            "pitch_mm": None,
            "body_w_mm": None,
            "body_h_mm": None,
            "pad_w_mm": None,
            "pad_h_mm": None,
            "thermal_pad": False,
            "citation": None,
        },
        "limits": {"max_current_per_pin_a": None},
        "notes": [],
    }


def validate_spec(spec: Any, path: Path | str = "<memory>", require_vetted: bool = False) -> dict:
    if not isinstance(spec, dict) or spec.get("kind") != PACKAGE_KIND:
        raise PackageError(f"{path}: not a {PACKAGE_KIND} document")
    if spec.get("schema_version") != 1:
        raise PackageError(f"{path}: requires schema_version: 1")
    meta = spec.get("package") or {}
    if not str(meta.get("id", "")).strip():
        raise PackageError(f"{path}: package.id is required")
    status = str(meta.get("status", ""))
    if status not in STATUSES:
        raise PackageError(f"{path}: package.status must be one of {list(STATUSES)}")
    if require_vetted and status != "vetted":
        raise PackageError(
            f"{path}: package {meta.get('id')!r} is {status!r}. Verify the drawing and run "
            "boardproof package vet before enforcing it.")
    if require_vetted and not str(meta.get("reviewed_by") or "").strip():
        raise PackageError(f"{path}: a vetted package spec needs package.reviewed_by")
    geometry = spec.get("geometry") or {}
    if not isinstance(geometry.get("pin_count"), int) or geometry["pin_count"] < 2:
        raise PackageError(f"{path}: geometry.pin_count must be an integer >= 2")
    if not isinstance(geometry.get("pitch_mm"), (int, float)) or geometry["pitch_mm"] <= 0:
        raise PackageError(f"{path}: geometry.pitch_mm is required to check a land pattern")
    try:
        Citation.from_dict(geometry.get("citation"))
    except Exception as exc:  # noqa: BLE001
        raise PackageError(
            f"{path}: geometry needs a citation (page + exact quote) from the package drawing: "
            f"{exc}") from exc
    return spec


def load_spec(path: Path, require_vetted: bool = False) -> dict:
    import json

    try:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise PackageError(f"cannot read package spec {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PackageError(f"{path} is not valid JSON: {exc}") from exc
    return validate_spec(spec, path, require_vetted)


def vet_spec(proposal_path: Path, reviewer: str, out: Path | None = None) -> dict:
    reviewer = reviewer.strip()
    if not reviewer:
        raise PackageError("--reviewer is required: someone must have read the drawing")
    spec = load_spec(proposal_path)
    spec["package"]["status"] = "vetted"
    spec["package"]["reviewed_by"] = reviewer
    spec["package"]["reviewed_at"] = utc_now()
    validate_spec(spec, proposal_path, require_vetted=True)
    destination = Path(out) if out else Path(proposal_path)
    import json

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    return spec


def _pattern_for(pattern_name: str) -> LandPattern | None:
    return LIBRARY.get(pattern_name)


def applies_to(spec: dict, footprint, design=None) -> bool:
    """A datasheet geometry governs the parts it describes, nothing else."""
    meta = spec["package"]
    refs = {str(r) for r in (meta.get("refs") or [])}
    if refs and footprint.ref not in refs:
        return False
    if refs:
        return True
    part = str(meta.get("part", "")).strip().lower()
    if not part or design is None:
        return bool(meta.get("refs"))
    component = design.components.get(footprint.ref)
    if component is None:
        return False
    haystack = f"{component.part} {component.value} {component.ref}".lower()
    key = "".join(ch for ch in part if ch.isalnum())
    return bool(key) and key in "".join(ch for ch in haystack if ch.isalnum())


def land_pattern_findings(spec: dict, board, design=None,
                          tolerance: float = TOLERANCE_MM) -> list[dict]:
    """Compare generated footprints against the datasheet drawing."""
    geometry = spec["geometry"]
    meta = spec["package"]
    citation = geometry.get("citation") or {}
    findings: list[dict] = []
    for footprint in board.footprints:
        if not applies_to(spec, footprint, design):
            continue
        pattern = _pattern_for(footprint.pattern)
        name = f"{footprint.ref} ({footprint.pattern})"
        if pattern is None:
            findings.append({
                "severity": "warning", "code": "LAND_PATTERN_UNKNOWN",
                "message": f"{name}: no library geometry to compare against the datasheet",
                "evidence": {"ref": footprint.ref, "pattern": footprint.pattern}})
            continue
        if len(pattern.pads) != int(geometry["pin_count"]):
            findings.append({
                "severity": "error", "code": "LAND_PATTERN_MISMATCH",
                "message": f"{name}: {len(pattern.pads)} pads in the library vs "
                           f"{geometry['pin_count']} pins on the datasheet drawing",
                "evidence": {"citation": citation, "pack": meta["id"]}})
            continue

        pitch = geometry["pitch_mm"]
        ys = sorted({round(p.y, 3) for p in pattern.pads})
        measured = round(min(b - a for a, b in zip(ys, ys[1:])), 3) if len(ys) > 1 else None
        if measured is None:
            cols = sorted({round(p.x, 3) for p in pattern.pads})
            measured = round(min(b - a for a, b in zip(cols, cols[1:])), 3) if len(cols) > 1 else None
        if measured is not None and abs(measured - pitch) > tolerance:
            findings.append({
                "severity": "error", "code": "LAND_PATTERN_MISMATCH",
                "message": f"{name}: library pitch {measured:g} mm vs datasheet {pitch:g} mm "
                           f"({meta['package']} drawing, p.{citation.get('page')})",
                "evidence": {"measured_mm": measured, "datasheet_mm": pitch,
                             "citation": citation, "pack": meta["id"],
                             "quote": citation.get("quote")}})

        if geometry.get("thermal_pad") and not any(p.kind == "thermal" for p in pattern.pads):
            findings.append({
                "severity": "error", "code": "THERMAL_PAD_MISSING",
                "message": f"{name}: the datasheet specifies an exposed thermal pad and the "
                           "generated footprint has none",
                "evidence": {"citation": citation}})
    return findings


def ipc2221_current(width_mm: float, copper_oz: float = 1.0, delta_t_c: float = 10.0,
                    external: bool = True) -> float:
    """IPC-2221 external-layer current capacity in amps, for a given track width."""
    width_mil = width_mm / 0.0254
    thickness_mil = copper_oz * 1.378
    area = width_mil * thickness_mil
    k = 0.048 if external else 0.024
    return k * (delta_t_c ** 0.44) * (area ** 0.725)


def current_findings(board, net_currents: dict[str, float], copper_oz: float = 1.0) -> list[dict]:
    findings: list[dict] = []
    for net, expected in (net_currents or {}).items():
        tracks = [s for s in board.segments if s.net == net]
        if not tracks:
            continue
        narrowest = min(tracks, key=lambda s: s.width)
        capacity = ipc2221_current(narrowest.width, copper_oz,
                                   external=narrowest.layer == "F.Cu")
        if float(expected) > capacity:
            findings.append({
                "severity": "error", "code": "TRACK_CURRENT",
                "message": f"net {net} carries {float(expected):.2f} A but a {narrowest.width:g} mm "
                           f"track on {narrowest.layer} carries about {capacity:.2f} A "
                           f"(IPC-2221, {copper_oz:g} oz, 10 °C rise)",
                "evidence": {"net": net, "required_a": float(expected),
                             "capacity_a": round(capacity, 2),
                             "width_mm": narrowest.width, "copper_oz": copper_oz}})
    return findings
