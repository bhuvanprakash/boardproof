"""Derived lookups over a Design, built once per run.

The naive engine scanned every component for every `resistor_between` rule,
which is O(rules x components). On a 4,000-component board with 800 rules that is
3.2M operations per check. The index makes it O(components + rules) with an
O(1) dict lookup per rule, and it is cached on the Design object so repeated
runs (red team, benchmarks) pay for it once.
"""
from __future__ import annotations

import re
from typing import Iterable

from .model import Component, Design, Pin

_OHM = re.compile(r"(\d+(?:\.\d+)?)\s*([kKmMrR]?)")
_FACTORS = {"": 1.0, "r": 1.0, "k": 1e3, "m": 1e6}


def ohms(value: str) -> float | None:
    """Parse '4k7'-style or '4700R' values. Returns None instead of guessing."""
    cleaned = value.strip().replace("Ω", "").replace("ohm", "").replace("OHM", "")
    if not cleaned:
        return None
    match = _OHM.fullmatch(cleaned)
    if not match:
        # '4k7' style: digit, multiplier, digit
        alt = re.fullmatch(r"(\d+)([kKmM])(\d+)", cleaned)
        if not alt:
            return None
        return (float(alt.group(1)) + float("0." + alt.group(3))) * _FACTORS[alt.group(2).lower()]
    return float(match.group(1)) * _FACTORS[match.group(2).lower()]


def rebuild_nets(components: dict[str, Component]) -> dict[str, list[tuple[str, str]]]:
    nets: dict[str, list[tuple[str, str]]] = {}
    for comp in components.values():
        for pin in comp.pins.values():
            if pin.net:
                nets.setdefault(pin.net, []).append((comp.ref, pin.number))
    return nets


class DesignIndex:
    """Lazy, cached lookups. Construct once, share across checks/faults."""

    def __init__(self, design: Design) -> None:
        self.design = design
        self._resistors: dict[frozenset[str], list[tuple[str, float]]] | None = None
        self._pins_by_net: dict[tuple[str, str], list[Pin]] | None = None
        self._resistor_count = -1

    def _invalidate(self) -> None:
        self._resistors = None
        self._pins_by_net = None

    def sync(self) -> "DesignIndex":
        """Rebuild only if the component count changed (mutated designs)."""
        if len(self.design.components) != self._resistor_count:
            self._invalidate()
            self._resistor_count = len(self.design.components)
        return self

    def resistors_between(self, net_a: str, net_b: str) -> list[tuple[str, float]]:
        if self._resistors is None:
            table: dict[frozenset[str], list[tuple[str, float]]] = {}
            for comp in self.design.components.values():
                # Only explicit resistor designators with exactly two pins.
                if not comp.ref.upper().startswith("R") or len(comp.pins) != 2:
                    continue
                pins = list(comp.pins.values())
                net = frozenset(p.net for p in pins)
                if len(net) != 2 or "" in net:
                    continue
                value = ohms(comp.value)
                if value is None:
                    continue
                table.setdefault(net, []).append((comp.ref, value))
            self._resistors = table
        return self._resistors.get(frozenset((net_a, net_b)), [])

    def all_resistors(self) -> Iterable[Component]:
        for comp in self.design.components.values():
            if comp.ref.upper().startswith("R") and len(comp.pins) == 2:
                yield comp

    def pins_on_net(self, ref: str, net: str) -> list[Pin]:
        if self._pins_by_net is None:
            table: dict[tuple[str, str], list[Pin]] = {}
            for comp in self.design.components.values():
                for pin in comp.pins.values():
                    if pin.net:
                        table.setdefault((comp.ref, pin.net), []).append(pin)
            self._pins_by_net = table
        return self._pins_by_net.get((ref, net), [])


def index_for(design: Design) -> DesignIndex:
    cached = getattr(design, "_index", None)
    if isinstance(cached, DesignIndex):
        return cached.sync()
    built = DesignIndex(design)
    setattr(design, "_index", built)
    return built.sync()
