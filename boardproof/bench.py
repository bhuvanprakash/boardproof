"""Throughput benchmark on a synthetic board.

Exists so "faster" is a measurement instead of a claim. Also a regression guard:
CI runs a smaller board and fails if the engine gets slower than the budget.
"""
from __future__ import annotations

import json
import time
import tracemalloc
from pathlib import Path
from tempfile import TemporaryDirectory

from .checks import run_checks
from .netlist import load_enet

PIN_NAMES = ["VDD", "GND", "GPIO4", "GPIO5"]


def synthetic_document(components: int) -> dict:
    """Build a legal EasyEDA Pro .enet document with N components."""
    doc: dict = {"version": "2.0.0", "components": {}, "_meta": {"synthetic": True}}
    resistors = max(1, components // 4)
    for i in range(components - resistors):
        ref = f"U{i + 1}"
        pins = {}
        for slot, name in enumerate(PIN_NAMES, 1):
            net = ("3V3" if name == "VDD" else "GND" if name == "GND"
                   else f"IO{i}_{slot}")
            pins[str(slot)] = {"number": str(slot), "name": name, "net": net}
        doc["components"][f"c_{ref}"] = {
            "props": {"Designator": ref, "Value": "SYNTH-MCU",
                      "Manufacturer Part": "SYNTH", "FootprintName": "SYNTH"},
            "pinInfoMap": pins,
        }
    for i in range(resistors):
        ref = f"R{i + 1}"
        a, b = f"PU_A{i}", f"PU_B{i}"
        doc["components"][f"c_{ref}"] = {
            "props": {"Designator": ref, "Value": "4.7k",
                      "Manufacturer Part": "SYNTH-R", "FootprintName": "0603"},
            "pinInfoMap": {
                "1": {"number": "1", "name": "1", "net": a},
                "2": {"number": "2", "name": "2", "net": b},
            },
        }
    return doc


def synthetic_rules(components: int, rules: int) -> dict:
    resistors = max(1, components // 4)
    out: list[dict] = []
    for i in range(rules):
        kind = i % 4
        if kind == 0:
            out.append({"id": f"pullup-{i}", "type": "resistor_between",
                        "net_a": f"PU_A{i % resistors}", "net_b": f"PU_B{i % resistors}",
                        "min_ohms": 1000, "max_ohms": 10000})
        elif kind == 1:
            out.append({"id": f"vdd-{i}", "type": "max_voltage",
                        "component": f"U{(i % max(1, components - resistors)) + 1}",
                        "pin": "1", "min_v": 2.7, "max_v": 3.6})
        elif kind == 2:
            out.append({"id": f"gnd-{i}", "type": "connected",
                        "component": f"U{(i % max(1, components - resistors)) + 1}", "pin": "2"})
        else:
            out.append({"id": f"net-{i}", "type": "pin_net",
                        "component": f"U{(i % max(1, components - resistors)) + 1}",
                        "pin": "1", "net": "3V3"})
    return {"schema_version": 1, "netlist": "synthetic.enet",
            "net_voltages": {"GND": 0.0, "3V3": 3.3, "5V": 5.0}, "rules": out}


def run(components: int = 4000, rules: int = 800, repeat: int = 3) -> dict:
    document = synthetic_document(components)
    config = synthetic_rules(components, rules)
    timings = {"parse": [], "checks": []}
    findings = 0
    with TemporaryDirectory() as td:
        path = Path(td) / "synthetic.enet"
        text = json.dumps(document)
        for _ in range(repeat):
            path.write_text(text, encoding="utf-8")
            start = time.perf_counter()
            design = load_enet(path)
            timings["parse"].append(time.perf_counter() - start)

            start = time.perf_counter()
            result = run_checks(design, config, path)
            timings["checks"].append(time.perf_counter() - start)
            findings = len(result)
    best_checks = min(timings["checks"])
    return {
        "components": components,
        "rules": rules,
        "nets": len(design.nets),
        "parse_ms": round(min(timings["parse"]) * 1000, 2),
        "checks_ms": round(best_checks * 1000, 2),
        "rules_per_second": int(rules / best_checks) if best_checks else 0,
        "findings": findings,
        "repeat": repeat,
    }


def format_bench(result: dict) -> str:
    return (
        f"BoardProof bench  {result['components']:,} components · {result['nets']:,} nets · "
        f"{result['rules']:,} rules (best of {result['repeat']})\n"
        f"  netlist parse   {result['parse_ms']:>8.2f} ms\n"
        f"  checks          {result['checks_ms']:>8.2f} ms   "
        f"({result['rules_per_second']:,} rules/s)\n"
        f"  findings        {result['findings']:,}"
    )
