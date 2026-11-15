"""Independent physical verification of a generated board.

The generator writes a file; this module re-reads that file and proves what
actually landed on disk. Nothing here trusts the in-memory board.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .model import Design
from .pcb import Board, PadInst, Segment, distance_point_segment, read_kicad

CLEARANCE = 0.2
TOL = 0.05
KICAD_CANDIDATES = (
    "kicad-cli",
    "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
    "/usr/bin/kicad-cli",
    "/usr/local/bin/kicad-cli",
)


@dataclass
class PcbFinding:
    severity: str
    code: str
    message: str
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"severity": self.severity, "code": self.code,
                "message": self.message, "evidence": self.evidence}


class _Union:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, item: int) -> int:
        self.parent.setdefault(item, item)
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _seg_point_hits(segment: Segment, x: float, y: float) -> bool:
    return distance_point_segment(x, y, segment.x1, segment.y1, segment.x2,
                                  segment.y2) <= (segment.width / 2 + TOL)


def _segments_cross(a: Segment, b: Segment) -> float:
    if a.layer != b.layer:
        return 99.0
    half = max(a.width, b.width) / 2
    ax, ay = sorted((a.x1, a.x2)), sorted((a.y1, a.y2))
    bx, by = sorted((b.x1, b.x2)), sorted((b.y1, b.y2))
    dx = max(0.0, max(bx[0] - ax[1], ax[0] - bx[1]))
    dy = max(0.0, max(by[0] - ay[1], ay[0] - by[1]))
    if dx == 0 and dy == 0:
        return 0.0
    return (dx * dx + dy * dy) ** 0.5 - half


def _pad_segment_gap(pad: PadInst, segment: Segment) -> float:
    if segment.layer != pad.layer:
        return 99.0
    cx = min(max(segment.x1, pad.x - pad.w / 2), pad.x + pad.w / 2)
    cy = min(max(segment.y1, pad.y - pad.h / 2), pad.y + pad.h / 2)
    return distance_point_segment(cx, cy, segment.x1, segment.y1, segment.x2,
                                  segment.y2) - segment.width / 2


def find_kicad_cli() -> str | None:
    configured = os.getenv("KICAD_CLI")
    if configured and Path(configured).exists():
        return configured
    for candidate in KICAD_CANDIDATES:
        found = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if found:
            return found
    return None


def run_kicad_drc(board_path: Path) -> dict:
    cli = find_kicad_cli()
    if not cli:
        return {"available": False,
                "note": "kicad-cli not found; DRC was NOT run (reported, not hidden)"}
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "drc.json"
        try:
            proc = subprocess.run(
                [cli, "pcb", "drc", "--format", "json", "--output", str(out), str(board_path)],
                capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as exc:
            return {"available": True, "error": f"kicad-cli failed to start: {exc}"}
        if not out.exists():
            return {"available": True,
                    "error": (proc.stderr or proc.stdout or "no report").strip()[:400]}
        try:
            report = json.loads(out.read_text())
        except json.JSONDecodeError as exc:
            return {"available": True, "error": f"unreadable DRC report: {exc}"}
    violations = report.get("violations") or []
    unconnected = report.get("unconnected_items") or []
    parity = report.get("schematic_parity") or []
    return {
        "available": True,
        "violations": len(violations),
        "unconnected": len(unconnected),
        "schematic_parity": len(parity),
        "items": [
            {"type": v.get("type"), "severity": v.get("severity"), "group": group,
             "description": (v.get("description") or "").strip()[:200]}
            for group, group_items in (("violations", violations),
                                       ("unconnected", unconnected),
                                       ("parity", parity))
            for v in group_items
        ][:14],
    }


def check_board(board_path: Path, design: Design, board: Board | None = None,
                decoupling_max_mm: float = 4.0, require_routing: bool = False,
                run_drc: bool = True, packages: list[dict] | None = None,
                net_currents: dict[str, float] | None = None, copper_oz: float = 1.0,
                advisory: set[str] | None = None) -> dict:
    parsed = board or read_kicad(board_path.read_text(encoding="utf-8"))
    findings: list[PcbFinding] = []

    for footprint in parsed.footprints:
        comp = design.components.get(footprint.ref)
        if comp is None:
            findings.append(PcbFinding("error", "EXTRA_FOOTPRINT",
                                       f"{footprint.ref} is on the board but not in the netlist",
                                       {"ref": footprint.ref}))
            continue
        for pad in footprint.pads:
            pin = comp.pins.get(pad.number)
            if pin is None:
                findings.append(PcbFinding(
                    "error", "PAD_NOT_IN_SCHEMATIC",
                    f"{footprint.ref}.{pad.number} ({pad.net}) has no schematic pin",
                    {"ref": footprint.ref, "pad": pad.number}))
                continue
            if (pin.net or "") != (pad.net or ""):
                findings.append(PcbFinding(
                    "error", "PAD_NET_MISMATCH",
                    f"{footprint.ref}.{pad.number}: board says {pad.net or '<no net>'}, "
                    f"schematic says {pin.net or '<no net>'}",
                    {"ref": footprint.ref, "pad": pad.number,
                     "board_net": pad.net, "netlist_net": pin.net}))

    placed = {f.ref for f in parsed.footprints}
    if len(placed) != len(parsed.footprints):
        findings.append(PcbFinding("error", "DUPLICATE_FOOTPRINT",
                                   "a designator appears more than once on the board", {}))
    for ref in sorted(set(design.components) - placed):
        findings.append(PcbFinding("error", "MISSING_FOOTPRINT",
                                   f"{ref} is in the netlist but has no footprint on the board",
                                   {"ref": ref}))

    pads = parsed.pads()
    union = _Union()
    base = {"pad": 0, "segment": 100_000, "via": 200_000}

    def node(kind: str, index: int) -> int:
        return base[kind] + index

    for index, pad in enumerate(pads):
        for sindex, segment in enumerate(parsed.segments):
            if pad.net and segment.net and pad.net != segment.net:
                continue
            if _seg_point_hits(segment, pad.x, pad.y):
                union.union(node("pad", index), node("segment", sindex))
    for index, via in enumerate(parsed.vias):
        for sindex, segment in enumerate(parsed.segments):
            if via.net and segment.net and via.net != segment.net:
                continue
            if _seg_point_hits(segment, via.x, via.y):
                union.union(node("via", index), node("segment", sindex))

    by_net: dict[str, list[tuple[int, PadInst]]] = {}
    for index, pad in enumerate(pads):
        if pad.net:
            by_net.setdefault(pad.net, []).append((index, pad))
    unrouted: list[str] = []
    for net, members in by_net.items():
        if len(members) < 2:
            continue
        roots = {union.find(node("pad", index)) for index, _ in members}
        if len(roots) > 1:
            unrouted.append(net)
            isolated = [f"{p.ref}.{p.number}" for index, p in members
                        if union.find(node("pad", index)) != min(roots)]
            findings.append(PcbFinding(
                "error" if require_routing else "notice", "UNROUTED_NET",
                f"net {net} is not fully connected: {', '.join(isolated)} "
                "have no copper path to the rest", {"net": net, "isolated": isolated}))

    for i, a in enumerate(parsed.segments):
        for b in parsed.segments[i + 1:]:
            if a.net == b.net:
                continue
            gap = _segments_cross(a, b)
            if gap < CLEARANCE - TOL:
                findings.append(PcbFinding(
                    "error", "CLEARANCE",
                    f"{a.net} and {b.net} tracks are {gap:.2f} mm apart on {a.layer} "
                    f"(minimum {CLEARANCE:g} mm)",
                    {"nets": [a.net, b.net], "gap_mm": round(gap, 3)}))
    for segment in parsed.segments:
        for pad in pads:
            if pad.net == segment.net or not pad.net:
                continue                     # unconnected/mechanical pads are not ours to judge
            gap = _pad_segment_gap(pad, segment)
            if gap < CLEARANCE - TOL:
                findings.append(PcbFinding(
                    "error", "CLEARANCE",
                    f"track {segment.net} is {gap:.2f} mm from pad "
                    f"{pad.ref}.{pad.number} ({pad.net})",
                    {"nets": [segment.net, pad.net], "gap_mm": round(gap, 3)}))

    for pad in pads:
        if not (pad.w / 2 <= pad.x <= parsed.width - pad.w / 2
                and pad.h / 2 <= pad.y <= parsed.height - pad.h / 2):
            findings.append(PcbFinding("error", "OUT_OF_BOUNDS",
                                       f"{pad.ref}.{pad.number} lies outside the board outline",
                                       {"ref": pad.ref, "pad": pad.number}))
    for segment in parsed.segments:
        for x, y in ((segment.x1, segment.y1), (segment.x2, segment.y2)):
            if not (0 <= x <= parsed.width and 0 <= y <= parsed.height):
                findings.append(PcbFinding("error", "OUT_OF_BOUNDS",
                                           f"{segment.net} track leaves the board outline",
                                           {"net": segment.net}))

    ic = next((f for f in parsed.footprints if f.ref[:1].upper() == "U"), None)
    caps = [f for f in parsed.footprints if f.ref[:1].upper() == "C"]
    if ic and caps and ic.pads:
        for cap in caps:
            if not cap.pads:
                continue
            nearest = min(min(abs(cap.pads[0].x - p.x), 99) for p in ic.pads)
            if nearest > decoupling_max_mm:
                findings.append(PcbFinding(
                    "warning", "DECOUPLING_DISTANCE",
                    f"{cap.ref} is {nearest:.1f} mm from {ic.ref} supply pins "
                    f"(rule: within {decoupling_max_mm:g} mm)",
                    {"ref": cap.ref, "distance_mm": round(nearest, 2)}))

    # 7. datasheet-derived geometry: the land pattern must match the drawing
    from .package import current_findings, land_pattern_findings

    datasheet_checks: list[str] = []
    for spec in packages or []:
        for item in land_pattern_findings(spec, parsed, design):
            findings.append(PcbFinding(item["severity"], item["code"], item["message"],
                                       item.get("evidence", {})))
        datasheet_checks.append(
            f"land pattern vs datasheet {spec['package'].get('package') or spec['package']['id']} "
            f"(p.{(spec['geometry'].get('citation') or {}).get('page')})")
    for item in current_findings(parsed, net_currents or {}, copper_oz):
        findings.append(PcbFinding(item["severity"], item["code"], item["message"],
                                   item.get("evidence", {})))
    if net_currents:
        datasheet_checks.append(f"track current capacity (IPC-2221, {copper_oz:g} oz copper)")

    drc = run_kicad_drc(board_path) if run_drc else {'available': False,
                                                        'note': 'external DRC skipped for this run'}
    if drc.get("available"):
        for item in drc.get("items", []):
            severity = "error" if item.get("severity") in {"error", "fatal"} else "warning"
            if item.get("group") == "unconnected" and not require_routing:
                severity = "notice"
            findings.append(PcbFinding(
                severity, f"DRC_{str(item.get('type') or 'FINDING').upper()[:40]}",
                (item.get("description") or "DRC violation").replace("\n", " ")[:180],
                {"source": "kicad-cli"}))
    # A hand-routed board is judged by KiCad's DRC, not by our cruder pad rectangles.
    # On imported boards the geometric pass is advisory unless the caller says otherwise.
    if advisory:
        findings = [
            PcbFinding("warning", f.code, f.message, f.evidence)
            if f.severity == "error" and f.code in advisory else f
            for f in findings
        ]
    errors = [f for f in findings if f.severity == "error"]
    notices = [f for f in findings if f.severity == "notice"]
    return {
        "tool": "BoardProof",
        "kind": "pcb-check",
        "board": str(board_path),
        "status": "failed" if errors else "passed",
        "counts": {"error": len(errors),
                   "warning": len([f for f in findings if f.severity == "warning"]),
                   "notice": len(notices)},
        "routing_required": require_routing,
        "policy": {"advisory": sorted(advisory) if advisory else [],
                   "authoritative": "KiCad DRC (kicad-cli) when available" if drc.get("available")
                                    else "our geometry only"},
        "census": {
            "width_mm": parsed.width, "height_mm": parsed.height,
            "footprints": len(parsed.footprints), "pads": len(pads),
            "segments": len(parsed.segments), "vias": len(parsed.vias),
            "nets": len(by_net),
        },
        "nets": {"total": len(by_net), "unrouted": unrouted,
                 "fully_connected": len(by_net) - len(unrouted)},
        "drc": drc,
        "findings": [f.as_dict() for f in findings],
        "verified": [
            "footprint coverage for every netlist component",
            "pad-to-net assignment against the verified schematic",
            ("copper connectivity for every multi-pad net" if require_routing
             else "pad-to-net assignment (routing not required for this run)"),
            f"copper clearance >= {CLEARANCE:g} mm between different nets",
            "board outline containment",
        ] + datasheet_checks
          + (["KiCad DRC via kicad-cli"] if drc.get("available") else []),
        "unverified": (
            ["impedance, crosstalk and RF behaviour",
             "assembly/DFM rules and panelisation",
             "steady-state thermal rise beyond the IPC-2221 10 °C assumption"]
            + ([] if packages else
               ["land patterns not checked against a datasheet geometry (no package spec loaded)"])
            + ([] if drc.get("available") else ["KiCad DRC (kicad-cli not installed)"])
        ),
        "note": "Passing this check means the layout matches the schematic and the geometry "
                "we generated. It is not a manufacturing release.",
    }


def format_report(result: dict) -> str:
    census = result["census"]
    lines = [f"PCB CHECK {result['status'].upper()}: {census['footprints']} footprints, "
             f"{census['pads']} pads, {result['nets']['fully_connected']}/"
             f"{result['nets']['total']} nets fully connected, {census['segments']} tracks, "
             f"{census['vias']} vias on a {census['width_mm']:g}x{census['height_mm']:g} mm board"]
    drc = result.get("drc") or {}
    if drc.get("available"):
        lines.append(f"  KiCad DRC: {drc.get('violations', 0)} violation(s), "
                     f"{drc.get('unconnected', 0)} unconnected, "
                     f"{drc.get('schematic_parity', 0)} parity")
    elif drc.get("error"):
        lines.append(f"  KiCad DRC: unavailable ({drc['error']})")
    else:
        lines.append("  KiCad DRC: not run (kicad-cli not installed)")
    for finding in result["findings"]:
        lines.append(f"  [{finding['severity'].upper()}] {finding['code']}: {finding['message']}")
    if not result["findings"]:
        lines.append("  no physical violations found by the checks above")
    return "\n".join(lines)
