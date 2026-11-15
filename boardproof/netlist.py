"""Parse EasyEDA Pro .enet format: https://github.com/easyeda/easyeda-netlist-format.

Do not attempt to parse arbitrary EasyEDA Std compressed shape data; that would
risk silently wrong net connectivity. Unsupported formats fail explicitly.
"""
from __future__ import annotations
import json
from pathlib import Path
from .model import Component, Design, Pin

class NetlistError(ValueError):
    pass


def load_enet(path: Path) -> Design:
    if path.suffix.lower() not in {".enet", ".json"}:
        raise NetlistError(f"Expected EasyEDA Pro .enet JSON export, got {path.name}")
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NetlistError(f"Cannot read valid .enet JSON at {path}: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("components"), dict):
        raise NetlistError("Not an EasyEDA Pro .enet export: expected 'components' object. "
                           "EasyEDA Standard compressed .json and Pro project archives are NOT supported in v0.1.")
    if not document["components"]:
        raise NetlistError("Netlist has zero components; refusing to report a false clean result")

    components: dict[str, Component] = {}
    nets: dict[str, list[tuple[str, str]]] = {}
    for unique_id, raw in document["components"].items():
        if not isinstance(raw, dict) or not isinstance(raw.get("props"), dict):
            raise NetlistError(f"Malformed component {unique_id}: missing props")
        props = raw["props"]
        ref = str(props.get("Designator", "")).strip()
        if not ref:
            raise NetlistError(f"Component {unique_id} missing Designator")
        if ref in components:
            raise NetlistError(f"Duplicate designator: {ref}")
        pin_map = raw.get("pinInfoMap")
        if not isinstance(pin_map, dict):
            raise NetlistError(f"Component {ref} missing pinInfoMap")
        pins: dict[str, Pin] = {}
        for pin_key, info in pin_map.items():
            if not isinstance(info, dict):
                raise NetlistError(f"Malformed pin {ref}.{pin_key}")
            number = str(info.get("number") or pin_key).strip()
            if not number or number in pins:
                raise NetlistError(f"Duplicate or empty pin number on {ref}: {number}")
            net = str(info.get("net") or "").strip()
            pins[number] = Pin(number=number, name=str(info.get("name") or ""), net=net)
            if net:
                nets.setdefault(net, []).append((ref, number))
        components[ref] = Component(ref, str(props.get("Value") or ""),
                                    str(props.get("Manufacturer Part") or props.get("DeviceName") or ""),
                                    pins, {str(k): str(v) for k, v in props.items()})
    return Design(components, nets, str(path))
