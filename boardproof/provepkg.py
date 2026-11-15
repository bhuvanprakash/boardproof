"""Assemble the passport from whatever the pipeline produced on disk."""
from __future__ import annotations

import json
from pathlib import Path

from .passport import build, render


def _read(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def build_document(out_dir: Path, revision: str) -> dict:
    out_dir = Path(out_dir)
    report = _read(out_dir / "report.json") or {
        "netlist": str(out_dir), "components": 0, "nets": 0, "findings": [],
        "counts": {"error": 0, "warning": 0, "info": 0}, "status": "passed",
        "packs": [], "unverified_scope": [], "verified_by_type": {},
    }
    pcb = _read(out_dir / "pcb-check.json")
    rules = _read(out_dir / "redteam.json")
    layout = _read(out_dir / "pcb-redteam.json")
    document = build(report, revision, None, rules)
    document["layout_redteam"] = layout
    if pcb:
        document["pcb"] = pcb
        svg = Path(pcb.get("svg") or "")
        if svg.is_file():
            document["pcb_svg"] = svg.read_text(encoding="utf-8")
            document["pcb"]["inline_svg"] = True
    return {"json": document, "html": render(document)}
