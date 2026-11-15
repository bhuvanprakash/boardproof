"""Approximate land patterns for board-level verification.

HONESTY: these are simplified two-layer land patterns with the correct pin
*order* and realistic geometry. They are NOT manufacturer-recommended patterns
and must be replaced with the fab-approved library before fabrication. Every
generated board carries that warning in the passport.

Geometry is millimetres, measured from the footprint origin.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pad:
    number: str
    x: float
    y: float
    w: float
    h: float
    kind: str = "smd"


@dataclass(frozen=True)
class LandPattern:
    name: str
    body_w: float
    body_h: float
    pads: tuple[Pad, ...]
    side_mount: bool = False


def _sot563_6() -> LandPattern:
    # 1-3 on the left (top to bottom), 6-4 on the right (top to bottom),
    # matching TI's SOT563 top view for the TMP102 family.
    pads = []
    # TI DRL0006A: 6 leads, 0.5 mm pitch, body 1.6 x 1.2 mm, lead width 0.1-0.3 mm.
    # Pad height is capped at 0.22 mm so the 0.28 mm mask gap clears the 0.25 mm rule.
    for number, y in (("1", -0.5), ("2", 0.0), ("3", 0.5)):
        pads.append(Pad(number, -0.75, y, 0.8, 0.22))
    for number, y in (("6", -0.5), ("5", 0.0), ("4", 0.5)):
        pads.append(Pad(number, 0.75, y, 0.8, 0.22))
    return LandPattern("SOT563-6", 1.6, 1.2, tuple(pads))


def _r0603() -> LandPattern:
    return LandPattern("R0603", 1.6, 0.8,
                       (Pad("1", -0.75, 0.0, 0.9, 0.95), Pad("2", 0.75, 0.0, 0.9, 0.95)))


def _c0603() -> LandPattern:
    return LandPattern("C0603", 1.6, 0.8,
                       (Pad("1", -0.75, 0.0, 0.9, 0.95), Pad("2", 0.75, 0.0, 0.9, 0.95)))


def _pin_header(*, count: int = 4, pitch: float = 2.54) -> LandPattern:
    middle = (count - 1) / 2
    pads = tuple(Pad(str(i + 1), 0.0, (i - middle) * pitch, 1.7, 1.7) for i in range(count))
    return LandPattern(f"PinHeader_1x{count}_P{pitch:g}mm", 2.54, (count - 1) * pitch + 2.54, pads)


def _dip(count: int) -> LandPattern:
    half = count // 2
    pitch, row = 2.54, 7.62
    pads = []
    for i in range(half):
        y = (i - (half - 1) / 2) * pitch
        pads.append(Pad(str(i + 1), -row / 2, y, 1.6, 1.6))
        pads.append(Pad(str(count - i), row / 2, y, 1.6, 1.6))
    return LandPattern(f"DIP-{count}", 6.6, (half - 1) * pitch + 2.54, tuple(pads))


def _led0603() -> LandPattern:
    return LandPattern("LED0603", 1.6, 0.8,
                       (Pad("1", -0.75, 0.0, 0.9, 0.95), Pad("2", 0.75, 0.0, 0.9, 0.95)))


def _hc49() -> LandPattern:
    return LandPattern("HC-49", 10.0, 3.8,
                       (Pad("1", -2.5, 0.0, 1.6, 1.6), Pad("2", 2.5, 0.0, 1.6, 1.6)))


LIBRARY = {
    "SOT563-6": _sot563_6(),
    "SOT-563": _sot563_6(),
    "SOT-563-6": _sot563_6(),
    "R0603": _r0603(),
    "C0603": _c0603(),
    "0603": _r0603(),
    "LED0603": _led0603(),
    "HC-49": _hc49(),
    "PinHeader_1x4_P2.54mm": _pin_header(),
}
LIBRARY.update({f"DIP-{n}": _dip(n) for n in (8, 14, 16, 18, 20, 24, 28, 40)})

DESIGNATORS = {"R": "R0603", "C": "C0603", "U": "SOT563-6", "J": "PinHeader_1x4_P2.54mm"}


class FootprintError(ValueError):
    pass


SOURCES = ("export", "library", "designator")


def resolve(ref: str, part: str, footprint_hint: str, pin_numbers: list[str],
            allow_generic: bool = True) -> tuple[LandPattern, str]:
    """Map a schematic component to a land pattern and say *where the geometry came from*.

    source == "export"     the netlist named the footprint
    source == "library"    the manufacturer part number matched the library
    source == "designator" guessed from the reference prefix - a fallback, flagged in
                           the report and refused outright when allow_generic is False
    """
    hint = (footprint_hint or "").strip()
    if hint and hint in LIBRARY:
        return LIBRARY[hint], "export"
    part_key = (part or "").strip()
    if part_key and part_key in LIBRARY:
        return LIBRARY[part_key], "library"
    for token, pattern in LIBRARY.items():
        if token and token.lower() in hint.lower():
            return pattern, "export"
    upper_ref = (ref or "").upper()
    n_pins = len(pin_numbers)
    if upper_ref.startswith("LED") and "LED0603" in LIBRARY:
        return LIBRARY["LED0603"], "designator"
    if upper_ref.startswith("Y") and "HC-49" in LIBRARY:
        return LIBRARY["HC-49"], "designator"
    if n_pins >= 8 and n_pins % 2 == 0 and n_pins <= 40:
        if "DIP" in hint.upper() or upper_ref.startswith(("U", "Q")):
            return _dip(n_pins), "designator"
    if upper_ref.startswith("J") or "HEADER" in hint.upper() or "PINHEADER" in hint.upper():
        count = min(max(n_pins or 4, 1), 16)
        return _pin_header(count=count), "designator"
    if not allow_generic:
        raise FootprintError(
            f"{ref}: no land pattern for part {part!r} / footprint {hint!r} (pins {pin_numbers}). "
            "Refusing to guess from the designator - name the footprint in the export, add the "
            "part to boardproof.footprints.LIBRARY, or pass --allow-generic-footprints.")
    guess = DESIGNATORS.get(ref[:1].upper())
    if guess and guess in LIBRARY:
        pattern = LIBRARY[guess]
        if set(pin_numbers) <= {p.number for p in pattern.pads}:
            return pattern, "designator"
    raise FootprintError(
        f"{ref}: no land pattern for part {part!r} / footprint {hint!r} "
        f"(pins {pin_numbers}). Refusing to invent geometry - add it to boardproof.footprints.LIBRARY."
    )


def pad_span(pattern: LandPattern) -> tuple[float, float]:
    xs = [p.x + p.w / 2 for p in pattern.pads] + [p.x - p.w / 2 for p in pattern.pads]
    ys = [p.y + p.h / 2 for p in pattern.pads] + [p.y - p.h / 2 for p in pattern.pads]
    return max(xs) - min(xs), max(ys) - min(ys)


def outline_of(pattern: LandPattern) -> tuple[float, float]:
    """Bounding box of the copper, plus a small margin for the silkscreen."""
    w, h = pad_span(pattern)
    return max(w, pattern.body_w) + 0.4, max(h, pattern.body_h) + 0.4
