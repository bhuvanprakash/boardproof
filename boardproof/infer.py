"""AI-proposed, human-vetted, machine-enforced constraint extraction.

Flow:
    infer  (PDF -> *propose.json, status=proposed, untrusted)
    vet    (propose.json -> pack.json, status=vetted, requires reviewer + citations)
    check  (pack.json -> CI; refuses anything not vetted)
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

from .model import Design
from .packs import PackError, empty_pack, load_pack, validate_pack
from .provenance import Citation, dumps, sha256_file, utc_now
from .providers import Provider, ProviderError  # noqa: F401  (re-exported for callers)

SUPPLY = re.compile(r"(?i)^(vdd|vcc|vbat|vin|avdd|dvdd|v\+|supply|vsys|vddd|vdda)$")
GROUND = re.compile(r"(?i)^(gnd|vss|agnd|dgnd|ground|pad|epad|ep)$")
PULLUP = re.compile(r"(?i)(sda|scl|sdi|sdo|cs|ncs|reset|nrst|en|int|irq|alert|wake|boot)")
RAIL = re.compile(r"(?i)^(3v3|3_3|5v|1v8|2v5|vcc|vdd|vbus|vbat|vddio|sys_?5v|sys_?3v3)$")


def _pin_sort_key(value: str) -> tuple[int, str]:
    digits = re.sub(r"\D", "", value)
    return (int(digits) if digits else 10**6, value)


def _rule_id(part: str, kind: str, ref: str, pin: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", f"{part}-{kind}-{ref}-{pin}".lower()).strip("-")
    return slug


NUMBERISH = re.compile(r"[0-9]")


def _squash(text: str) -> str:
    out = text.lower()
    for a, b in (("kΩ", "k"), ("k ohm", "k"), ("kohm", "k"), ("Ω", ""), ("µ", "u"), ("μ", "u"),
                 ("ohms", ""), ("ohm", ""), ("-", ""), (" ", ""), (",", "")):
        out = out.replace(a, b)
    return out


def quote_supports(quote: str, values: list[float]) -> bool:
    """Does the quoted text actually contain the numbers we are about to enforce?

    This is the guard that stopped a real datasheet test from shipping a 5 kΩ
    pull-up rule whose only citation was the words 'Serial clock'.
    """
    squashed = _squash(quote)
    for value in values:
        if value is None:
            continue
        number = int(value) if float(value).is_integer() else value
        candidates = {f"{number:g}", str(number)}
        if isinstance(number, int) and number >= 1000 and number % 1000 == 0:
            candidates.add(f"{number // 1000}k")
        if not any(re.search(rf"(?<![0-9.]){re.escape(c)}(?![0-9])", squashed) for c in candidates):
            return False
    return True


def _first(value: object) -> str:
    """Models occasionally return '3, 4' for a single-value field. Keep the first."""
    text = str(value or "").strip()
    for separator in (",", ";", " and "):
        if separator in text:
            text = text.split(separator)[0].strip()
    return text


def _citation(pin: dict) -> dict | None:
    try:
        return Citation(
            page=_first(pin.get("cited_page", "")),
            quote=str(pin.get("cited_quote", "")),
            section=_first(pin.get("cited_section", "")),
            table=_first(pin.get("cited_table", "")),
            confidence=float(pin["confidence"]) if isinstance(pin.get("confidence"), (int, float)) else None,
        ).as_dict()
    except Exception:  # noqa: BLE001 - unusable citation is meaningful, not fatal
        return None


def _rail_for(design: Design | None, ref: str, pin_number: str) -> str:
    """Best-effort rail lookup; anything ambiguous is left unbound for review."""
    if design is None or ref not in design.components:
        return ""
    for pin in design.components[ref].pins.values():
        if pin.number == pin_number and RAIL.match(pin.net or ""):
            return pin.net
    return ""


def proposal_from_pins(facts: dict[str, Any], design: Design | None, component: str,
                       pack_id: str, source_pdf: Path, engine: str) -> dict:
    part = str(facts.get("component") or component)
    pack = empty_pack(pack_id, part=part,
                      manufacturer=str(facts.get("manufacturer", "")),
                      package=str(facts.get("package", "")))
    pack["pack"]["source"] = {
        "document": source_pdf.name,
        "sha256": sha256_file(source_pdf) if source_pdf.is_file() else "",
        "pages": "",
    }
    pack["pack"]["extracted_by"] = {
        "engine": engine,
        "model": facts.get("_model"),
        "at": utc_now(),
    }
    notes: list[str] = [str(w) for w in (facts.get("review_warnings") or [])]
    pins = [p for p in (facts.get("pins") or []) if isinstance(p, dict)]
    pins.sort(key=lambda p: _pin_sort_key(str(p.get("number", ""))))

    for pin in pins:
        number = str(pin.get("number", "")).strip()
        name = str(pin.get("name", "")).strip()
        if not number:
            notes.append(f"Pin without a number was skipped: {name or '<unnamed>'}")
            continue
        citation = _citation(pin)
        if citation is None:
            notes.append(f"{component}.{number} ({name}) has no usable page quote; no rule generated.")
            continue
        function = str(pin.get("function", ""))
        lo, hi = pin.get("recommended_min_v"), pin.get("recommended_max_v")

        if SUPPLY.match(name) and isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            if not quote_supports(str(citation.get("quote", "")), [float(lo), float(hi)]):
                notes.append(
                    f"{component}.{number} ({name}): the cited quote does not contain "
                    f"{lo:g}-{hi:g} V. Rule WITHHELD - the citation does not support the number.")
                lo = hi = None
        if SUPPLY.match(name) and isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            pack["rules"].append({
                "id": _rule_id(pack_id, "max-voltage", component, number),
                "type": "max_voltage",
                "component": component,
                "pin": number,
                "min_v": float(lo),
                "max_v": float(hi),
                "citation": citation,
                "note": f"Recommended operating range for {name} from {function or 'datasheet'}.",
            })
        if GROUND.match(name):
            pack["rules"].append({
                "id": _rule_id(pack_id, "connected", component, number),
                "type": "connected",
                "component": component,
                "pin": number,
                "citation": citation,
                "note": f"{name} must be tied low.",
            })
        pull_min, pull_max = pin.get("pullup_min_ohms"), pin.get("pullup_max_ohms")
        target = str(pin.get("requires_pullup_to", "") or "")
        if PULLUP.search(name) and isinstance(pull_max, (int, float)) and not quote_supports(
                str(citation.get("quote", "")), [float(pull_max)]):
            notes.append(
                f"{component}.{number} ({name}): a pull-up was detected but the cited quote "
                f"contains no resistance value. Rule WITHHELD - review the datasheet text manually.")
            pull_max = None
        if PULLUP.search(name) and isinstance(pull_max, (int, float)):
            if design is not None and design.pin(component, number) is None:
                notes.append(
                    f"{component}.{number} ({name}) is not present on {component} in this netlist "
                    f"(package mismatch?); pull-up rule skipped rather than emitted unbound."
                )
                continue
            rail = target or _rail_for(design, component, number) or "3V3"
            if not target and not _rail_for(design, component, number):
                notes.append(
                    f"{component}.{number} ({name}) requires a pull-up but no rail was found in the "
                    f"netlist; defaulted to {rail!r}. Confirm before vetting."
                )
            bound = design.pin(component, number) if design else None
            if not bound or not bound.net:
                notes.append(f"{component}.{number} ({name}) has no net in this netlist; the pull-up rule will fail closed until the schematic is wired.")
            pack["rules"].append({
                "id": _rule_id(pack_id, "pullup", component, number),
                "type": "resistor_between",
                "net_a": (design.pin(component, number).net if design and design.pin(component, number) else f"{component}_{name}"),
                "net_b": rail,
                "min_ohms": float(pin.get("pullup_min_ohms", 1000)),
                "max_ohms": float(pull_max),
                "citation": citation,
                "note": f"Bus line {name} needs a defined idle level.",
            })
        if pin.get("absolute_max_v") is not None and citation.get("table"):
            notes.append(
                f"{component}.{number}: absolute maximum {pin['absolute_max_v']} V was NOT converted to a "
                "rule; absolute maximums are not operating limits. Reviewer must decide."
            )
    for requirement in facts.get("requirements") or []:
        if not isinstance(requirement, dict):
            continue
        kind = str(requirement.get("kind", "")).lower()
        applies = [a.strip() for a in str(requirement.get("applies_to", "")).split(",") if a.strip()]
        detail = str(requirement.get("detail", "")).strip()
        try:
            cited = Citation(
                page=_first(requirement.get("cited_page", "")),
                quote=str(requirement.get("cited_quote", "")),
                section=_first(requirement.get("cited_section", "")),
            ).as_dict()
        except Exception:  # noqa: BLE001
            notes.append(f"Requirement dropped (no usable citation): {detail or kind}")
            continue
        value = requirement.get("max_value") or requirement.get("min_value")
        if isinstance(value, (int, float)) and value > 0 and not quote_supports(
                str(cited.get("quote", "")), [float(value)]):
            notes.append(
                f"{kind} on {applies}: recommended {value:g} {requirement.get('unit', '')} "
                "is not present in the cited quote. Requirement WITHHELD.")
            value = None
        if "pull" in kind and isinstance(value, (int, float)) and value > 0:
            low, high = int(value * 0.5), int(value * 2)
            emitted = 0
            for name in applies:
                match = next((p for p in pins if str(p.get("name", "")).lower() == name.lower()), None)
                if match is None:
                    notes.append(f"{kind} on {name}: pin not in the datasheet pin table; skipped.")
                    continue
                number = str(match.get("number"))
                bound = design.pin(component, number) if design else None
                if design is not None and bound is None:
                    notes.append(f"{kind} on {name} (pin {number}): pin absent from this netlist; skipped.")
                    continue
                if not bound or not bound.net:
                    notes.append(f"{kind} on {name} (pin {number}): no net in this netlist; rule will fail closed.")
                rule_id = _rule_id(pack_id, "pullup", component, number)
                if any(r["id"] == rule_id for r in pack["rules"]):
                    notes.append(
                        f"{kind} on {name}: a pull-up rule for pin {number} was already proposed by an "
                        "earlier datasheet section; duplicate skipped.")
                    continue
                pack["rules"].append({
                    "id": rule_id,
                    "type": "resistor_between",
                    "net_a": bound.net if bound else f"{component}_{name}",
                    "net_b": _rail_for(design, component, number) or "3V3",
                    "min_ohms": low,
                    "max_ohms": high,
                    "citation": cited,
                    "note": (f"Datasheet recommends {value:g} {requirement.get('unit', 'ohm')} "
                             f"for {name}. The accepted window {low}-{high} is a REVIEW PROPOSAL "
                             "derived from that single value, not a documented range. Confirm before vetting."),
                })
                emitted += 1
            if emitted:
                notes.append(
                    f"{kind}: {emitted} pull-up rule(s) proposed at {low}-{high} ohm from the "
                    f"recommended {value:g} {requirement.get('unit', 'ohm')} (p.{cited['page']}). "
                    "The window is a proposal, not a datasheet range.")
        else:
            notes.append(f"{kind or 'requirement'}: {detail or 'stated in the datasheet'} (p.{cited['page']}) "
                         "- not machine-checkable yet; record it in review.")

    # de-duplicate review notes while preserving order (models repeat requirements across sections)
    pack["pack"]["review_notes"] = list(dict.fromkeys(notes))
    if not pack["rules"] and notes:
        raise PackError(
            "No rule could be proposed with a citation. Refusing to emit an empty or uncited pack; "
            "a proposal that cannot be traced to a page is not a starting point for review."
        )
    return validate_pack(pack, f"proposal:{pack_id}", require_vetted=False)


def diff_against(previous: Path | None, proposal: dict) -> list[str]:
    if previous is None or not previous.is_file():
        return []
    try:
        old = load_pack(previous, require_vetted=False)
    except PackError:
        return [f"previous pack at {previous} could not be read; review as a new pack"]
    old_lines = dumps(old["rules"]).splitlines()
    new_lines = dumps(proposal["rules"]).splitlines()
    return list(
        difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"{previous.name} (current)",
            tofile="proposal (AI-extracted)",
            lineterm="",
            n=2,
        )
    )


def vet(proposal_path: Path, reviewer: str, out: Path | None = None) -> dict:
    reviewer = reviewer.strip()
    if not reviewer:
        raise PackError("--reviewer is required: a vetted pack must name the human who accepted it")
    pack = load_pack(proposal_path, require_vetted=False)
    for rule in pack["rules"]:
        if "citation" not in rule:
            raise PackError(
                f"cannot vet {rule['id']!r}: no citation. An uncited rule must be deleted, not approved."
            )
    pack["pack"]["status"] = "vetted"
    pack["pack"]["reviewed_by"] = reviewer
    pack["pack"]["reviewed_at"] = utc_now()
    pack["pack"]["review_notes"] = [
        f"Vetted by {reviewer} on {pack['pack']['reviewed_at']}. Citations were re-checked against the source document."
    ] + list(pack["pack"].get("review_notes") or [])
    validate_pack(pack, proposal_path, require_vetted=True)
    destination = Path(out) if out else proposal_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(dumps(pack), encoding="utf-8")
    return pack
