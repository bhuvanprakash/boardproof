from __future__ import annotations
import re
from functools import lru_cache
from pathlib import Path
from .index import index_for, ohms
from .model import Design, Finding
from .firmware import parse_defines

SEVERITIES = {"error", "warning", "info"}
RULE_TYPES = {"pin_net", "connected", "max_voltage", "resistor_between", "firmware_gpio"}


@lru_cache(maxsize=2048)
def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def run_checks(design: Design, config: dict, config_path: Path,
               fw_overrides: dict[str, int] | None = None) -> list[Finding]:
    """Pure function: same design + same config -> same findings.

    `fw_overrides` lets the red team simulate a firmware regression without
    writing a file; it never widens what the checks accept.
    """
    if config.get("schema_version") != 1:
        raise ValueError("boardproof config requires schema_version: 1")
    rules = config.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("config must define a non-empty rules list")
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict) or rule.get("type") not in RULE_TYPES:
            raise ValueError(f"Rule {i + 1} has unknown/missing type: {rule!r}")
        if rule.get("severity", "error") not in SEVERITIES:
            raise ValueError(f"Rule {i + 1} has invalid severity")

    fw_path = config.get("firmware")
    fw: dict[str, int] = parse_defines((config_path.parent / fw_path).resolve()) if fw_path else {}
    if fw_overrides:
        fw = {**fw, **fw_overrides}
    index = index_for(design)
    result: list[Finding] = []
    for rule_index, rule in enumerate(rules, 1):
        kind = rule["type"]
        severity = rule.get("severity", "error")
        label = str(rule.get("id", f"rule-{index}"))

        provenance = rule.get("_provenance")

        def add(message: str, details: dict, code: str | None = None, sev: str | None = None):
            payload = dict(details)
            if provenance:
                payload["provenance"] = provenance
            result.append(Finding(sev or severity, code or kind.upper(), f"[{label}] {message}", rule_index, payload))

        if kind in {"pin_net", "connected", "max_voltage"}:
            ref, pin_number = str(rule.get("component", "")), str(rule.get("pin", ""))
            pin = design.pin(ref, pin_number)
            if pin is None:
                add(f"Unknown component/pin {ref}.{pin_number}; cannot verify", {"component": ref, "pin": pin_number}, "MISSING_PIN")
                continue
            if kind == "connected":
                if not pin.net:
                    add(f"{ref}.{pin_number} ({pin.name}) is unconnected", {"component": ref, "pin": pin_number})
            elif kind == "pin_net":
                wanted = rule.get("net")
                allowed = rule.get("any_of", [wanted] if wanted is not None else [])
                if not isinstance(allowed, list) or not allowed:
                    raise ValueError(f"Rule {rule_index}: pin_net needs net or any_of")
                if pin.net not in allowed:
                    add(f"{ref}.{pin_number} ({pin.name}) uses net {pin.net or '<unconnected>'}, "
                        f"expected one of {allowed}", {"component": ref, "pin": pin_number,
                        "observed_net": pin.net, "expected_nets": allowed})
            else:
                declared = config.get("net_voltages", {})
                if pin.net not in declared:
                    add(f"Voltage of net {pin.net or '<unconnected>'} is not declared; cannot confirm "
                        f"rating on {ref}.{pin_number}", {"component": ref, "pin": pin_number},
                        "VOLTAGE_UNKNOWN")
                    continue
                voltage = float(declared[pin.net])
                lo = float(rule.get("min_v", float("-inf")))
                hi = float(rule.get("max_v", float("inf")))
                if not lo <= voltage <= hi:
                    add(f"{ref}.{pin_number} on {pin.net} has declared {voltage:g} V; "
                        f"allowed {lo:g} to {hi:g} V", {"component": ref, "pin": pin_number,
                        "net": pin.net, "voltage": voltage, "min_v": lo, "max_v": hi})

        elif kind == "resistor_between":
            a, b = str(rule.get("net_a", "")), str(rule.get("net_b", ""))
            if not a or not b or a == b:
                raise ValueError(f"Rule {rule_index}: resistor_between needs two distinct nets")
            low = float(rule.get("min_ohms", 0))
            high = float(rule.get("max_ohms", float("inf")))
            matched = [{"component": ref, "ohms": value}
                       for ref, value in index.resistors_between(a, b)
                       if low <= value <= high]
            if not matched:
                add(f"No two-terminal resistor between {a} and {b} in accepted range "
                    f"({rule.get('min_ohms',0)}–{rule.get('max_ohms','∞')} ohms)",
                    {"net_a": a, "net_b": b,
                     "min_ohms": float(rule.get("min_ohms", 0)),
                     "max_ohms": float(rule["max_ohms"]) if "max_ohms" in rule else None,
                     "matching_resistors": matched})

        elif kind == "firmware_gpio":
            define = str(rule.get("define", ""))
            ref = str(rule.get("component", ""))
            net = str(rule.get("net", ""))
            if not fw_path:
                add("No firmware file configured; cannot perform firmware crosscheck", {}, "FW_UNKNOWN")
                continue
            if define not in fw:
                add(f"Macro {define} is missing or not a simple numeric #define; cannot verify", 
                    {"define": define}, "FW_UNKNOWN")
                continue
            comp = design.components.get(ref)
            if comp is None:
                add(f"Unknown MCU component {ref}", {"component": ref}, "MISSING_COMPONENT")
                continue
            connected = index.pins_on_net(ref, net)
            if len(connected) != 1:
                add(f"Expected exactly one {ref} pin on {net}, found {len(connected)}", 
                    {"component": ref, "net": net, "pins": [p.number for p in connected]}, "MCU_NET_AMBIGUOUS")
                continue
            pin = connected[0]
            pattern = rule.get("pin_label_regex", r"(?:GPIO|IO)(\d+)")
            try:
                match = _compile(pattern).search(pin.name)
            except re.error as exc:
                raise ValueError(f"Rule {rule_index}: invalid pin_label_regex: {exc}") from exc
            if not match:
                add(f"Cannot infer GPIO number from pin name '{pin.name}'; no false pass",
                    {"component": ref, "net": net, "pin_name": pin.name}, "GPIO_UNKNOWN")
                continue
            actual = int(match.group(1))
            if fw[define] != actual:
                add(f"Firmware {define}={fw[define]}, but {net} connects to "
                    f"{ref}.{pin.number} ({pin.name})",
                    {"define": define, "firmware_gpio": fw[define], "schematic_gpio": actual,
                    "component": ref, "pin": pin.number, "net": net})
    return result
