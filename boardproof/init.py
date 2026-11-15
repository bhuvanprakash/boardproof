"""Generate a draft boardproof.json from a netlist you just exported.

Onboarding a real board should take one command. But a generated rule must never
block a build, so every rule is emitted with `severity: "warning"` and an explicit
"draft" note. Promotion to `error` is a human decision, recorded in review.
"""
from __future__ import annotations

import re
from pathlib import Path

from .index import ohms
from .model import Design

SUPPLY = re.compile(r"(?i)^(vdd|vcc|vbat|vin|avdd|dvdd|vddd|vdda|vddio|v\+|vbus|vsys)$")
GROUND = re.compile(r"(?i)^(gnd|vss|agnd|dgnd|ground|epad|ep|pad)$")
RAIL = re.compile(r"(?i)^(3v3|3_3|3\.3v|5v|5_0v|1v8|2v5|vbus|vbat|vcc|vdd|vddio|vsys)$")

DEFAULT_VOLTAGES = {
    "gnd": 0.0, "vss": 0.0, "3v3": 3.3, "3.3v": 3.3, "5v": 5.0, "5.0v": 5.0,
    "1v8": 1.8, "2v5": 2.5, "9v": 9.0, "12v": 12.0, "vbus": 5.0, "vsys": 5.0,
}


def draft_config(design: Design, netlist_name: str, firmware: str | None = None,
                 voltages: dict[str, float] | None = None) -> tuple[dict, list[str]]:
    declared = dict(DEFAULT_VOLTAGES)
    declared.update({k.lower(): float(v) for k, v in (voltages or {}).items()})
    notes: list[str] = []
    rules: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(rule: dict) -> None:
        key = (str(rule.get("component")), str(rule.get("pin")))
        if key in seen:
            return
        seen.add(key)
        rule.setdefault("severity", "warning")
        rule.setdefault("note", "DRAFT generated from the netlist. Review, then set severity to 'error'.")
        rules.append(rule)

    for comp in design.components.values():
        if comp.ref.upper().startswith(("R", "L", "C")):
            continue
        for pin in comp.pins.values():
            if not pin.net:
                continue
            if SUPPLY.match(pin.name):
                add({"id": f"{comp.ref}-{pin.name}-net", "type": "pin_net",
                     "component": comp.ref, "pin": pin.number, "net": pin.net})
                voltage = declared.get(pin.net.lower())
                if voltage is not None and voltage > 0:
                    add({"id": f"{comp.ref}-{pin.name}-limit", "type": "max_voltage",
                         "component": comp.ref, "pin": pin.number,
                         "min_v": round(voltage * 0.82, 2), "max_v": round(voltage * 1.09, 2)})
                    notes.append(
                        f"{comp.ref}.{pin.number} ({pin.name}): voltage window "
                        f"{voltage * 0.82:.2f}-{voltage * 1.09:.2f} V was GUESSED around "
                        f"{voltage} V. Replace it with the datasheet range before promoting this rule.")
                else:
                    notes.append(
                        f"{comp.ref}.{pin.number} ({pin.name}): net {pin.net!r} has no known voltage, "
                        "so no voltage limit was generated. Add it to net_voltages manually.")
            elif GROUND.match(pin.name):
                add({"id": f"{comp.ref}-{pin.name}-connected", "type": "connected",
                     "component": comp.ref, "pin": pin.number})

    for comp in design.components.values():
        if not comp.ref.upper().startswith("R") or len(comp.pins) != 2:
            continue
        value = ohms(comp.value)
        if value is None:
            notes.append(f"{comp.ref}: value {comp.value!r} could not be parsed; no pull-up rule generated.")
            continue
        nets = [p.net for p in comp.pins.values()]
        if len(set(nets)) != 2 or "" in set(nets):
            continue
        signal, rail = sorted(nets, key=lambda n: bool(RAIL.match(n)))
        add({"id": f"{comp.ref}-{signal}-pullup", "type": "resistor_between",
             "net_a": signal, "net_b": rail,
             "min_ohms": int(value * 0.5), "max_ohms": int(value * 2)})
        notes.append(
            f"{comp.ref}: range {int(value * 0.5)}-{int(value * 2)} ohm was inferred from the current "
            f"value ({comp.value}). A review must confirm it is the intended range.")

    if firmware:
        notes.append(
            "firmware_gpio rules cannot be generated: which macro drives which net is an "
            "intent decision. Add them by hand, e.g. "
            '{"type": "firmware_gpio", "define": "LED_PIN", "component": "U1", "net": "LED_STATUS"}.')

    voltages_out = {name: declared[name.lower()] for name in
                    {p.net for c in design.components.values() for p in c.pins.values() if p.net}
                    if name.lower() in declared}
    config = {
        "schema_version": 1,
        "netlist": netlist_name,
        "net_voltages": voltages_out,
        "rules": rules,
    }
    if firmware:
        config["firmware"] = firmware
    config["unverified_scope"] = [
        "PCB trace geometry, impedance, crosstalk and RF performance",
        "Schematic ERC, footprint-to-symbol pin mapping and pad assignments",
        "Thermal, power-integrity and inrush behaviour under load",
        "Mechanical fit, connector mating and manufacturing tolerances (DFM)",
        "Any component datasheet not captured in a vetted rule pack",
    ]
    return config, notes


def write_draft(design: Design, netlist: Path, out: Path, firmware: str | None = None,
                voltages: dict[str, float] | None = None) -> tuple[dict, list[str]]:
    config, notes = draft_config(design, netlist.name, firmware, voltages)
    out.parent.mkdir(parents=True, exist_ok=True)
    import json
    out.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return config, notes
