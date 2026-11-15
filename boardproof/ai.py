"""Backwards-compatible shim. Prefer `boardproof infer` / `boardproof.cli`.

Kept so older scripts calling propose_datasheet() keep working; it now routes
through the same provider layer and emits a *proposed* rule pack, never rules
that CI can enforce.
"""
from __future__ import annotations

import json
from pathlib import Path

from .infer import proposal_from_pins
from .providers import get_provider


def propose_datasheet(pdf: Path, component: str, output: Path, model: str | None = None) -> None:
    pdf = Path(pdf)
    provider = get_provider("auto", model=model)
    facts = provider.extract(pdf, component)
    facts.setdefault("_model", getattr(provider, "model", None))
    pack = proposal_from_pins(facts, None, component, f"{component.lower()}-{pdf.stem.lower()}", pdf,
                              provider.name)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
