"""Revision diff: what did this change break?

A hardware PR should be blocked by *newly introduced* violations, not by a
backlog of known ones. This is the PR gate.
"""
from __future__ import annotations

from typing import Any


def key(finding: dict[str, Any]) -> str:
    return f"{finding.get('code')}|{finding.get('message')}"


def compare(base: dict, head: dict) -> dict:
    base_map = {key(f): f for f in base.get("findings", []) if f.get("severity") == "error"}
    head_map = {key(f): f for f in head.get("findings", []) if f.get("severity") == "error"}
    introduced = [head_map[k] for k in head_map if k not in base_map]
    fixed = [base_map[k] for k in base_map if k not in head_map]
    persisting = [head_map[k] for k in head_map if k in base_map]
    return {
        "base": {"status": base.get("status"), "errors": len(base_map),
                 "netlist": base.get("netlist")},
        "head": {"status": head.get("status"), "errors": len(head_map),
                 "netlist": head.get("netlist")},
        "introduced": introduced,
        "fixed": fixed,
        "persisting": persisting,
        "regressed": bool(introduced),
        "summary": {
            "introduced": len(introduced),
            "fixed": len(fixed),
            "persisting": len(persisting),
        },
    }


def format_diff(result: dict) -> str:
    head, base = result["head"], result["base"]
    lines = [
        f"BoardProof revision diff: {base['errors']} error(s) -> {head['errors']} error(s)"
        f"  ({base['status']} -> {head['status']})"
    ]
    for label, items, mark in (
        ("NEW  ", result["introduced"], "regression"),
        ("FIXED", result["fixed"], "improvement"),
        ("STILL", result["persisting"], "pre-existing"),
    ):
        for item in items:
            lines.append(f"  [{label}] {item.get('code')}: {item.get('message')}  ({mark})")
    if not any(result[k] for k in ("introduced", "fixed", "persisting")):
        lines.append("  no error-level findings in either revision")
    if result["regressed"]:
        lines.append("  VERDICT: this revision introduces new hardware violations - blocked")
    else:
        lines.append("  VERDICT: no new hardware violations introduced")
    return "\n".join(lines)
