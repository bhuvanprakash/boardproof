"""Red team: inject realistic faults and measure whether the checks catch them.

An ordinary checker says "I found no violations". This says "I found no
violations, and here is how those rules performed against known faults, and
here is where they are blind".

That is mutation testing applied to pre-manufacturing hardware rules. Faults are
derived from the rules themselves, so every targeted fault is relevant by
construction: if a rule cannot catch the fault aimed at it, the rule is
decoration. Blind spots are reported as gaps with the rule that would close them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from .checks import RULE_TYPES, run_checks
from .index import index_for, ohms, rebuild_nets
from .model import Design

GPIO = re.compile(r"(?:GPIO|IO)(\d+)", re.IGNORECASE)
RAILISH = re.compile(r"(?i)^(gnd|vss|3v3|5v|vcc|vdd|vbus|vbat|\.\.\.)$")


@dataclass
class Fault:
    id: str
    kind: str
    summary: str
    expect: set[str]
    apply: Callable[[], tuple[Design, dict[str, int] | None]]
    target: str = ""
    targeted: bool = True
    representable: bool = True
    note: str = ""


def _set_pin_net(design: Design, ref: str, number: str, net: str) -> Design:
    comp = design.components[ref]
    pins = dict(comp.pins)
    pins[number] = replace(pins[number], net=net)
    components = dict(design.components)
    components[ref] = replace(comp, pins=pins)
    return replace(design, components=components, nets=rebuild_nets(components))


def _drop_component(design: Design, ref: str) -> Design:
    components = {k: v for k, v in design.components.items() if k != ref}
    return replace(design, components=components, nets=rebuild_nets(components))


def _revalue(design: Design, ref: str, factor: float) -> Design:
    comp = design.components[ref]
    current = ohms(comp.value)
    if current is None:
        return design
    scaled = current * factor
    text = f"{scaled / 1000:g}k" if scaled >= 1000 else f"{scaled:g}R"
    components = dict(design.components)
    components[ref] = replace(comp, value=text)
    return replace(design, components=components, nets=design.nets)


def build_faults(design: Design, config: dict) -> list[Fault]:
    index = index_for(design)
    voltages = {str(k): float(v) for k, v in (config.get("net_voltages") or {}).items()}
    rules = [r for r in (config.get("rules") or []) if str(r.get("type")) in RULE_TYPES]
    faults: list[Fault] = []
    seen: set[tuple[str, str]] = set()

    def add(fault: Fault) -> None:
        if fault.id not in {f.id for f in faults}:
            faults.append(fault)

    def pick_wrong_net(pin_net: str, legal: set[str], low: float, high: float) -> str:
        """A net that is genuinely different and, if possible, genuinely illegal."""
        pool = [(n, v) for n, v in voltages.items()
                if n != pin_net and (not legal or n not in legal)]
        violating = [n for n, v in pool if not (low <= v <= high)]
        if violating:
            return max(violating, key=lambda n: voltages[n])
        if pool:
            # prefer the highest declared rail: an over-voltage is the realistic mistake
            return max(pool, key=lambda kv: kv[1])[0]
        return next((n for n in design.nets if n != pin_net and (not legal or n not in legal)), "")

    for rule in rules:
        kind = str(rule.get("type"))
        ref, number = str(rule.get("component", "")), str(rule.get("pin", ""))
        pin = design.pin(ref, number)

        if kind in {"max_voltage", "pin_net"} and pin is not None and pin.net:
            if ("net", f"{ref}.{number}") in seen:
                continue
            seen.add(("net", f"{ref}.{number}"))
            legal = set(rule.get("any_of") or ([rule["net"]] if "net" in rule else []))
            low = float(rule.get("min_v", float("-inf")))
            high = float(rule.get("max_v", float("inf")))
            target = pick_wrong_net(pin.net, legal, low, high)
            if not target:
                continue
            expect = {kind.upper()}
            if kind == "pin_net":
                expect.add("MAX_VOLTAGE")
            add(Fault(
                id=f"supply-swap:{ref}.{number}", kind="supply_swap", target=f"{ref}.{number}",
                summary=f"{ref}.{number} ({pin.name}) reconnected to {target} instead of {pin.net}",
                expect=expect,
                apply=lambda ref=ref, number=number, target=target: (
                    _set_pin_net(design, ref, number, target), None),
            ))

        elif kind == "connected" and pin is not None and pin.net:
            add(Fault(
                id=f"float:{ref}.{number}", kind="disconnect", target=f"{ref}.{number}",
                summary=f"{ref}.{number} ({pin.name}) left floating",
                expect={"CONNECTED"},
                apply=lambda ref=ref, number=number: (_set_pin_net(design, ref, number, ""), None),
            ))

        elif kind == "resistor_between":
            net_a, net_b = str(rule.get("net_a", "")), str(rule.get("net_b", ""))
            matched = index.resistors_between(net_a, net_b)
            if not matched:
                continue
            victim, value = matched[0]
            add(Fault(
                id=f"drop-resistor:{victim}", kind="remove_resistor", target=victim,
                summary=f"{victim} ({value:g} ohm, {net_a}-{net_b}) deleted",
                expect={"RESISTOR_BETWEEN"},
                apply=lambda victim=victim: (_drop_component(design, victim), None),
            ))
            add(Fault(
                id=f"drift-resistor:{victim}", kind="value_drift", target=victim,
                summary=f"{victim} revalued 100x, out of the accepted range",
                expect={"RESISTOR_BETWEEN"},
                apply=lambda victim=victim: (_revalue(design, victim, 100.0), None),
            ))

        elif kind == "firmware_gpio":
            define, net = str(rule.get("define", "")), str(rule.get("net", ""))
            landed = index.pins_on_net(ref, net)
            if not (define and len(landed) == 1):
                continue
            match = GPIO.search(landed[0].name)
            if not match:
                continue
            actual = int(match.group(1))
            add(Fault(
                id=f"fw-shift:{define}", kind="firmware_shift", target=define,
                summary=f"firmware {define} set to {actual + 1} while the netlist still uses GPIO{actual}",
                expect={"FIRMWARE_GPIO"},
                apply=lambda define=define, actual=actual: (design, {define: actual + 1}),
            ))

    # ---- blind-spot probe: does a signal-net typo get noticed anywhere? ----
    declared = {str(r.get("net", "")) for r in rules if r.get("type") == "pin_net"}
    referenced = set()
    for rule in rules:
        for field in ("net", "net_a", "net_b"):
            if rule.get(field):
                referenced.add(str(rule[field]))
    blind = next(
        ((comp, pin) for comp in design.components.values()
         for pin in comp.pins.values()
         if pin.net and not RAILISH.match(pin.net) and not comp.ref.upper().startswith("R")
         and pin.net not in referenced),
        None,
    )
    if blind:
        comp, pin = blind
        add(Fault(
            id=f"net-typo:{comp.ref}.{pin.number}", kind="net_typo", target=f"{comp.ref}.{pin.number}",
            summary=f"one-character net rename strands {comp.ref}.{pin.number} ({pin.name}, {pin.net})",
            expect={"PIN_NET", "CONNECTED", "MCU_NET_AMBIGUOUS"},
            targeted=pin.net in declared,
            apply=lambda ref=comp.ref, number=pin.number, net=pin.net: (
                _set_pin_net(design, ref, number, net + "X"), None),
        ))

    add(Fault(
        id="footprint-pinmap", kind="not_representable",
        summary="symbol pin order disagrees with the physical footprint",
        expect=set(), apply=lambda: (design, None), representable=False,
        note="a .enet netlist carries pin numbers, not footprint pads - needs PCB-level data",
    ))
    return faults


def run_redteam(design: Design, config: dict, config_path: Path) -> dict:
    results: list[dict] = []
    suggestions: list[str] = []
    for fault in build_faults(design, config):
        if not fault.representable:
            results.append({"id": fault.id, "kind": fault.kind, "summary": fault.summary,
                            "status": "unverifiable", "caught_by": [], "expected": [],
                            "target": fault.target, "note": fault.note})
            continue
        mutated, overrides = fault.apply()
        fired = {f.code for f in run_checks(mutated, config, config_path, fw_overrides=overrides)}
        caught_by = sorted(fired & fault.expect)
        if caught_by:
            status = "caught"
        elif fault.targeted:
            status = "missed"
            suggestions.append(
                f"{fault.summary}: no rule fires. The rule aimed at {fault.target} is not "
                f"actually detecting it - tighten it or attach the evidence it needs.")
        else:
            status = "gap"
            suggestions.append(
                f"{fault.summary}: nothing constrains {fault.target}, so no rule could fire. "
                "Add a pin_net rule naming the intended net to close this blind spot.")
        results.append({"id": fault.id, "kind": fault.kind, "summary": fault.summary,
                        "status": status, "caught_by": caught_by, "target": fault.target,
                        "expected": sorted(fault.expect), "observed": sorted(fired)})
    targeted = [r for r in results if r["status"] in {"caught", "missed"}]
    caught = [r for r in targeted if r["status"] == "caught"]
    ratio = (len(caught) / len(targeted)) if targeted else 1.0
    return {
        "faults": results,
        "score": {
            "caught": len(caught),
            "targeted": len(targeted),
            "gaps": sum(1 for r in results if r["status"] == "gap"),
            "unverifiable": sum(1 for r in results if r["status"] == "unverifiable"),
            "ratio": round(ratio, 3),
        },
        "suggestions": suggestions,
        "note": "Mutation testing of the rule set. Not proof of board correctness.",
    }


def format_report(result: dict) -> str:
    score = result["score"]
    pct = int(round(score["ratio"] * 100))
    lines = [f"RED TEAM  {score['caught']}/{score['targeted']} targeted faults caught ({pct}%)"
             f"  ·  {score['gaps']} blind spot(s)  ·  {score['unverifiable']} unverifiable from a netlist"]
    for item in result["faults"]:
        status = item["status"]
        if status == "caught":
            mark, tail = "PASS", "caught by " + ", ".join(item["caught_by"])
        elif status == "missed":
            mark, tail = "FAIL", "MISSED - the rule aimed at it did not fire"
        elif status == "gap":
            mark, tail = "GAP ", "nothing constrains this yet"
        else:
            mark, tail = "SKIP", item.get("note", "")
        lines.append(f"  [{mark}] {item['kind']:<16} {item['summary']}")
        lines.append(f"         {tail}")
    for text in result["suggestions"]:
        lines.append(f"  -> {text}")
    return "\n".join(lines)
