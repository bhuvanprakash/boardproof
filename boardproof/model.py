from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class Pin:
    number: str
    name: str
    net: str

@dataclass(frozen=True)
class Component:
    ref: str
    value: str
    part: str
    pins: dict[str, Pin]
    attributes: dict[str, str] = field(default_factory=dict)

@dataclass
class Design:
    components: dict[str, Component]
    nets: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    source: str = ""
    net_voltages: dict[str, float] = field(default_factory=dict)

    def pin(self, ref: str, number: str) -> Pin | None:
        comp = self.components.get(ref)
        return comp.pins.get(str(number)) if comp else None

@dataclass
class Finding:
    severity: str
    code: str
    message: str
    rule_index: int
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "code": self.code, "message": self.message,
                "rule_index": self.rule_index, "evidence": self.evidence}
