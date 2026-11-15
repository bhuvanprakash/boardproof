"""Provenance: every enforced numeric limit must be traceable to a datasheet page
and a named human reviewer.

The invariant this module exists to enforce is the product's whole thesis:

  An LLM may PROPOSE a constraint. It may never ENFORCE one.
  A numeric limit cannot enter CI without (a) a citation and (b) a reviewer.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUSES = ("proposed", "vetted", "rejected")
NUMERIC_FIELDS: dict[str, tuple[str, ...]] = {
    "max_voltage": ("min_v", "max_v"),
    "resistor_between": ("min_ohms", "max_ohms"),
}


class ProvenanceError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    digest.update(Path(path).read_bytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class Citation:
    """A pointer into the authoritative document. Not a summary - a quote."""

    page: str
    quote: str
    section: str = ""
    table: str = ""
    confidence: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in ("", None)}

    @classmethod
    def from_dict(cls, raw: Any) -> "Citation":
        if not isinstance(raw, dict):
            raise ProvenanceError("citation must be an object")
        page = str(raw.get("page", "")).strip()
        quote = str(raw.get("quote", "")).strip()
        if not page or not quote:
            raise ProvenanceError("citation requires a page and an exact quote")
        confidence = raw.get("confidence")
        return cls(
            page=page,
            quote=quote,
            section=str(raw.get("section", "")).strip(),
            table=str(raw.get("table", "")).strip(),
            confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
        )

    def locator(self) -> str:
        bits = [f"p.{self.page}"]
        if self.section:
            bits.append(f"§{self.section}")
        if self.table:
            bits.append(f"Table {self.table}")
        return " ".join(bits)


def citation_of(rule: dict) -> Citation | None:
    raw = rule.get("citation")
    if raw is None:
        return None
    try:
        return Citation.from_dict(raw)
    except ProvenanceError:
        return None


def numeric_fields_for(rule: dict) -> tuple[str, ...]:
    return NUMERIC_FIELDS.get(str(rule.get("type")), ())


def has_numeric_limit(rule: dict) -> bool:
    return any(f in rule for f in numeric_fields_for(rule))


def dumps(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"
