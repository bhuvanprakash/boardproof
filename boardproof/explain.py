"""Turn deterministic findings into an engineer-facing explanation.

The deterministic engine decides pass/fail. This module only decides *wording*,
and every sentence it emits is grounded in the finding's own evidence plus a
citation that a human already approved.
"""
from __future__ import annotations

from typing import Any

from .model import Design, Finding
from .providers import Provider, redact_explanations


def build_payload(findings: list[Finding], design: Design, packs: list[dict] | None = None) -> dict:
    items: list[dict] = []
    for finding in findings:
        prov = finding.evidence.get("provenance") or {}
        items.append(
            {
                "rule_index": finding.rule_index,
                "code": finding.code,
                "severity": finding.severity,
                "message": finding.message,
                "observed": finding.evidence,
                "provenance": prov,
            }
        )
    declared = getattr(design, "net_voltages", {}) or {}
    return {
        "design": {
            "components": sorted(design.components),
            "nets": sorted(design.nets),
            "declared_net_voltages": declared,
        },
        "rule_packs": packs or [],
        "findings": items,
    }


def allowed_pages(findings: list[Finding]) -> dict[int, set[str]]:
    pages: dict[int, set[str]] = {}
    for finding in findings:
        citation = (finding.evidence.get("provenance") or {}).get("citation") or {}
        page = citation.get("page")
        if page is not None:
            pages.setdefault(finding.rule_index, set()).add(str(page))
    return pages


def explain_findings(findings: list[Finding], design: Design, provider: Provider,
                     packs: list[dict] | None = None) -> dict[str, Any]:
    if not findings:
        return {"engine": provider.name, "explanations": [], "rejected": []}
    payload = build_payload(findings, design, packs)
    result = provider.explain(payload)
    kept, rejected = redact_explanations(
        result,
        allowed_pages(findings),
        {f.rule_index for f in findings},
    )
    for entry in kept:
        entry["engine"] = provider.name
    return {"engine": provider.name, "explanations": kept, "rejected": rejected}


def attach(findings: list[Finding], explanations: list[dict]) -> None:
    """Merge explanations into finding evidence for reporting."""
    by_index = {int(e["rule_index"]): e for e in explanations if "rule_index" in e}
    for finding in findings:
        entry = by_index.get(finding.rule_index)
        if entry:
            finding.evidence = dict(finding.evidence)
            finding.evidence["explanation"] = entry
