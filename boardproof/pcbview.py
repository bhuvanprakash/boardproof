"""Board renders: a real 2D PCB view and an isometric 3D view.

Both are pure SVG built from the same Board model the checker verifies, so the
picture can never disagree with the geometry. No raster, no JS, no network.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .pcb import Board, FootprintInst

# ENIG on green FR4 (prototype) vs HASL on Arduino-blue soldermask
PROTO = {
    "mask": "#0c4f2e", "mask_light": "#11613a", "mask_dark": "#083a22",
    "trace": "#2e7a52", "trace_b": "#0a3a24",
    "pad": "#d4a24a", "pad_edge": "#9a6c2e", "pad_hi": "#e2b467",
}
ARDUINO = {
    "mask": "#0b4f8a", "mask_light": "#1563a8", "mask_dark": "#083560",
    "trace": "#2a7ab8", "trace_b": "#0a3d6e",
    "pad": "#c9d0d6", "pad_edge": "#8b959e", "pad_hi": "#e6eaee",
}
SILK = "#f3f6f8"
HOLE = "#0a1220"
INK = "#465266"
FAINT = "#8b97a6"
MONO = "ui-monospace,SFMono-Regular,Menlo,monospace"
SANS = "ui-sans-serif,system-ui,sans-serif"

KIND_HEIGHT = {
    "usb": 8.0, "header": 8.5, "dip": 4.2, "ic": 1.5, "electrolytic": 7.0,
    "crystal": 2.4, "led": 1.4, "resistor": 0.5, "cap": 0.55, "diode": 1.1,
    "fuse": 0.5, "bead": 0.9, "smd": 0.6, "jack": 9.0,
}


def kind_of(footprint: FootprintInst) -> str:
    ref = (footprint.ref or "").upper()
    pat = (footprint.pattern or "").upper()
    blob = f"{ref} {pat}"
    if "USB" in blob:
        return "usb"
    if "BARREL" in blob or "PJ-" in blob or "DCJACK" in blob:
        return "jack"
    if "DIP" in pat:
        return "dip"
    if any(token in pat for token in ("SSOP", "SOIC", "QFP", "TQFP", "SOP")):
        return "ic"
    if "PPPC" in pat or "HEADER" in pat or "PINHEADER" in pat:
        return "header"
    if ref.startswith("LED") or "LED" in pat:
        return "led"
    if ref.startswith("Y") or "XO" in pat or "XTAL" in pat or "CRYSTAL" in pat:
        return "crystal"
    if ref.startswith("C") and ("EEE" in pat or footprint.body_h >= 2.4 or footprint.body_w >= 4.5):
        return "electrolytic"
    if ref.startswith("C"):
        return "cap"
    if ref.startswith("R"):
        return "resistor"
    if ref.startswith("D"):
        return "diode"
    if ref.startswith("FB") or "BEAD" in pat:
        return "bead"
    if ref.startswith("F"):
        return "fuse"
    if ref.startswith("U"):
        return "ic"
    if ref.startswith("J"):
        return "header"
    return "smd"


def _is_arduino(board: Board) -> bool:
    blob = " ".join(
        [board.title or ""] + [f"{f.ref} {f.pattern}" for f in board.footprints]
    ).upper()
    return any(token in blob for token in ("DIP-28", "USB", "ATMEGA", "ARDUINO", "JEDEN"))


def _palette(board: Board) -> dict:
    return ARDUINO if _is_arduino(board) else PROTO


def _height(footprint: FootprintInst) -> float:
    return KIND_HEIGHT.get(kind_of(footprint), 0.6)


def _r(value: float) -> float:
    return round(value, 2)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _centre(footprint: FootprintInst) -> tuple[float, float]:
    if footprint.pads:
        return (
            sum(p.x for p in footprint.pads) / len(footprint.pads),
            sum(p.y for p in footprint.pads) / len(footprint.pads),
        )
    return footprint.x + footprint.body_cx, footprint.y + footprint.body_cy


def _span(footprint: FootprintInst) -> tuple[float, float]:
    if not footprint.pads:
        return max(footprint.body_w, 0.6), max(footprint.body_h, 0.4)
    xs = [p.x for p in footprint.pads]
    ys = [p.y for p in footprint.pads]
    pad_w = max(p.w for p in footprint.pads)
    pad_h = max(p.h for p in footprint.pads)
    return max(xs) - min(xs) + pad_w, max(ys) - min(ys) + pad_h


def _dip_size(footprint: FootprintInst) -> tuple[float, float]:
    """Black moulding sits between the two pin rows, not over the pins."""
    if len(footprint.pads) < 4:
        width, height = _span(footprint)
        return max(width * 0.7, 6.0), height
    xs = [p.x for p in footprint.pads]
    ys = [p.y for p in footprint.pads]
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    if span_y >= span_x:
        return max(span_x * 0.72, 6.0), span_y + 0.4
    return span_x + 0.4, max(span_y * 0.72, 6.0)


def _mount_holes(board: Board) -> list[tuple[float, float]]:
    if not _is_arduino(board):
        return []
    inset = 3.2
    return [
        (inset, inset),
        (board.width - inset, inset),
        (inset, board.height - inset),
        (board.width - inset, board.height - inset),
    ]


def _bounds(board: Board) -> tuple[float, float, float, float]:
    xs = [0.0, board.width]
    ys = [0.0, board.height]
    for footprint in board.footprints:
        cx, cy = _centre(footprint)
        kind = kind_of(footprint)
        bw, bh = _visual_size(footprint, kind)
        xs += [cx - bw / 2, cx + bw / 2]
        ys += [cy - bh / 2, cy + bh / 2]
        for pad in footprint.pads:
            xs += [pad.x - pad.w / 2, pad.x + pad.w / 2]
            ys += [pad.y - pad.h / 2, pad.y + pad.h / 2]
    for segment in board.segments:
        xs += [segment.x1, segment.x2]
        ys += [segment.y1, segment.y2]
    for via in board.vias:
        xs += [via.x - via.size / 2, via.x + via.size / 2]
        ys += [via.y - via.size / 2, via.y + via.size / 2]
    return min(xs), min(ys), max(xs), max(ys)


def _visual_size(footprint: FootprintInst, kind: str) -> tuple[float, float]:
    width, height = _span(footprint)
    if kind == "usb":
        return max(width, 12.0), max(height, 12.0)
    if kind == "jack":
        return max(width, 9.0), max(height, 9.0)
    if kind == "dip":
        return _dip_size(footprint)
    if kind == "header":
        return max(width, 2.4), max(height, 2.4)
    if kind == "electrolytic":
        size = max(width, height, 5.0)
        return size, size
    if kind == "crystal":
        return max(width, 10.0), max(height, 4.2)
    return width, height


def _labelled(kind: str) -> bool:
    return kind in {"usb", "jack", "header", "dip", "ic", "crystal", "led", "electrolytic"}


# ------------------------------------------------------------------ 2D view --
def render_2d(board: Board, scale: float = 16.0, dimensions: bool = True) -> str:
    palette = _palette(board)
    min_x, min_y, max_x, max_y = _bounds(board)
    pad_top, pad_left, pad_right, pad_bottom = (
        (26.0, 38.0, 14.0, 16.0) if dimensions else (12.0, 12.0, 12.0, 12.0)
    )
    origin_x = min_x
    origin_y = min_y
    content_w = max_x - min_x
    content_h = max_y - min_y
    svg_w = content_w * scale + pad_left + pad_right
    svg_h = content_h * scale + pad_top + pad_bottom

    def px(x: float) -> float:
        return pad_left + (x - origin_x) * scale

    def py(y: float) -> float:
        return pad_top + (y - origin_y) * scale

    rx = (2.5 if _is_arduino(board) else 1.5) * scale
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w:.1f} {svg_h:.1f}" '
        f'width="100%" role="img" aria-label="PCB top view, {board.width:g} by '
        f'{board.height:g} millimetres">',
        "<defs>",
        f'<linearGradient id="maskg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{palette["mask_light"]}"/>'
        f'<stop offset="1" stop-color="{palette["mask"]}"/></linearGradient>',
        f'<filter id="soft"><feDropShadow dx="0" dy="0.6" stdDeviation="0.7" '
        f'flood-color="#041018" flood-opacity=".28"/></filter>',
        "</defs>",
        f'<rect x="{px(0):.1f}" y="{py(0):.1f}" width="{board.width * scale:.1f}" '
        f'height="{board.height * scale:.1f}" rx="{rx:.1f}" fill="url(#maskg)"/>',
        f'<rect x="{px(0.45):.1f}" y="{py(0.45):.1f}" '
        f'width="{(board.width - 0.9) * scale:.1f}" height="{(board.height - 0.9) * scale:.1f}" '
        f'rx="{max(1.0, rx - 4):.1f}" fill="none" stroke="{SILK}" stroke-width="0.7" opacity=".28"/>',
    ]

    for layer, colour, opacity in (("B.Cu", palette["trace_b"], 0.45),
                                   ("F.Cu", palette["trace"], 0.9)):
        for segment in board.segments:
            if segment.layer != layer:
                continue
            out.append(
                f'<line x1="{px(segment.x1):.1f}" y1="{py(segment.y1):.1f}" '
                f'x2="{px(segment.x2):.1f}" y2="{py(segment.y2):.1f}" stroke="{colour}" '
                f'stroke-width="{max(1.1, segment.width * scale):.1f}" stroke-linecap="round" '
                f'opacity="{opacity}"/>'
            )

    for via in board.vias:
        r = max(1.4, via.size * scale / 2)
        out.append(
            f'<circle cx="{px(via.x):.1f}" cy="{py(via.y):.1f}" r="{r:.1f}" '
            f'fill="{palette["pad"]}" stroke="{palette["pad_edge"]}" stroke-width="0.5"/>'
            f'<circle cx="{px(via.x):.1f}" cy="{py(via.y):.1f}" r="{r * 0.42:.1f}" fill="{HOLE}"/>'
        )

    for footprint in board.footprints:
        for pad in footprint.pads:
            pw, ph = max(1.2, pad.w * scale), max(1.2, pad.h * scale)
            rotate = ""
            if abs(pad.rotation) % 180 > 0.05:
                cx, cy = px(pad.x), py(pad.y)
                rotate = f' transform="rotate({pad.rotation:g} {cx:.1f} {cy:.1f})"'
            out.append(
                f'<rect x="{px(pad.x) - pw / 2:.1f}" y="{py(pad.y) - ph / 2:.1f}" '
                f'width="{pw:.1f}" height="{ph:.1f}" rx="{min(pw, ph) * 0.18:.1f}" '
                f'fill="{palette["pad"]}" stroke="{palette["pad_edge"]}" stroke-width="0.5"{rotate}/>'
            )

    for footprint in board.footprints:
        out.extend(_draw_part_2d(footprint, px, py, scale, palette))

    hole_r = 1.6 * scale
    for hx, hy in _mount_holes(board):
        out.append(
            f'<circle cx="{px(hx):.1f}" cy="{py(hy):.1f}" r="{hole_r + 1.6:.1f}" '
            f'fill="none" stroke="{palette["pad"]}" stroke-width="1.2"/>'
            f'<circle cx="{px(hx):.1f}" cy="{py(hy):.1f}" r="{hole_r:.1f}" fill="{HOLE}"/>'
        )

    if dimensions:
        y_dim = pad_top - 10.0
        x0, x1 = px(0), px(board.width)
        out.append(
            f'<line x1="{x0:.1f}" y1="{y_dim:.1f}" x2="{x1:.1f}" y2="{y_dim:.1f}" '
            f'stroke="{FAINT}" stroke-width="0.8"/>'
            f'<line x1="{x0:.1f}" y1="{y_dim - 3:.1f}" x2="{x0:.1f}" y2="{y_dim + 3:.1f}" '
            f'stroke="{FAINT}" stroke-width="0.8"/>'
            f'<line x1="{x1:.1f}" y1="{y_dim - 3:.1f}" x2="{x1:.1f}" y2="{y_dim + 3:.1f}" '
            f'stroke="{FAINT}" stroke-width="0.8"/>'
            f'<text x="{(x0 + x1) / 2:.1f}" y="{y_dim - 5:.1f}" font-family="{MONO}" '
            f'font-size="11" fill="{INK}" text-anchor="middle">{board.width:g} mm</text>'
        )
        x_dim = pad_left - 14.0
        y0, y1 = py(0), py(board.height)
        mid_y = (y0 + y1) / 2
        out.append(
            f'<line x1="{x_dim:.1f}" y1="{y0:.1f}" x2="{x_dim:.1f}" y2="{y1:.1f}" '
            f'stroke="{FAINT}" stroke-width="0.8"/>'
            f'<line x1="{x_dim - 3:.1f}" y1="{y0:.1f}" x2="{x_dim + 3:.1f}" y2="{y0:.1f}" '
            f'stroke="{FAINT}" stroke-width="0.8"/>'
            f'<line x1="{x_dim - 3:.1f}" y1="{y1:.1f}" x2="{x_dim + 3:.1f}" y2="{y1:.1f}" '
            f'stroke="{FAINT}" stroke-width="0.8"/>'
            f'<text x="{x_dim - 7:.1f}" y="{mid_y:.1f}" font-family="{MONO}" font-size="11" '
            f'fill="{INK}" text-anchor="middle" '
            f'transform="rotate(-90 {x_dim - 7:.1f} {mid_y:.1f})">{board.height:g} mm</text>'
        )
    out.append("</svg>")
    return "".join(out)


def _draw_part_2d(footprint: FootprintInst, px, py, scale: float, palette: dict) -> list[str]:
    kind = kind_of(footprint)
    cx, cy = _centre(footprint)
    bw, bh = _visual_size(footprint, kind)
    x, y, w, h = px(cx) - bw * scale / 2, py(cy) - bh * scale / 2, bw * scale, bh * scale
    # body_w/body_h are already the axis-aligned pad envelope in board space;
    # rotating again would swing a DIP off the outline.
    bits = ["<g>"]
    rx = max(0.8, min(w, h) * 0.12)

    if kind == "usb":
        lip = max(2.4, h * 0.08)
        ow, oh = w * 0.58, h * 0.38
        ox, oy = x + (w - ow) / 2, y + 2.0
        bits.append(
            f'<rect x="{x:.1f}" y="{y - lip:.1f}" width="{w:.1f}" height="{h + lip:.1f}" '
            f'rx="1.8" fill="#c5ccd3" stroke="#6f777f" stroke-width="0.9" filter="url(#soft)"/>'
            f'<rect x="{x + w * 0.12:.1f}" y="{y + h * 0.16:.1f}" width="{w * 0.76:.1f}" '
            f'height="{h * 0.62:.1f}" rx="1.0" fill="#1a1d22"/>'
            f'<polygon points="{ox:.1f},{oy + oh:.1f} {ox + ow:.1f},{oy + oh:.1f} '
            f'{ox + ow * 0.82:.1f},{oy:.1f} {ox + ow * 0.18:.1f},{oy:.1f}" fill="#0b0d10"/>'
        )
    elif kind == "jack":
        bits.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="1.4" '
            f'fill="#1c1c1c" filter="url(#soft)"/>'
            f'<circle cx="{px(cx):.1f}" cy="{py(cy):.1f}" r="{min(w, h) * 0.28:.1f}" '
            f'fill="#0a0a0a" stroke="#444" stroke-width="1.2"/>'
        )
    elif kind == "header":
        bits.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="0.7" '
            f'fill="#161616" stroke="#050505" stroke-width="0.6" filter="url(#soft)"/>'
        )
        for pad in footprint.pads:
            bits.append(
                f'<circle cx="{px(pad.x):.1f}" cy="{py(pad.y):.1f}" '
                f'r="{max(1.1, min(pad.w, pad.h) * scale * 0.22):.1f}" fill="#0a0a0a" '
                f'stroke="{palette["pad_hi"]}" stroke-width="0.6"/>'
            )
    elif kind == "dip":
        notch_r = min(5.0, min(w, h) * 0.16)
        pin1 = next((p for p in footprint.pads if str(p.number) in {"1", "A1"}), None)
        if h >= w:
            ny = y + notch_r + 1.5
            if pin1 is not None and pin1.y > cy:
                ny = y + h - notch_r - 1.5
            nx = px(cx)
        else:
            nx = x + notch_r + 1.5
            if pin1 is not None and pin1.x > cx:
                nx = x + w - notch_r - 1.5
            ny = py(cy)
        bits.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="1.4" '
            f'fill="#1a1a1a" stroke="#050505" stroke-width="0.7" filter="url(#soft)"/>'
            f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="{notch_r:.1f}" fill="#0c0c0c"/>'
            f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="1.3" fill="#ececec" opacity=".55"/>'
        )
    elif kind == "ic":
        bits.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="1" '
            f'fill="#1c1c1c" stroke="#0a0a0a" stroke-width="0.6" filter="url(#soft)"/>'
            f'<circle cx="{x + 3:.1f}" cy="{y + 3:.1f}" r="1.4" fill="#ececec" opacity=".7"/>'
        )
    elif kind == "electrolytic":
        r = min(w, h) / 2
        bits.append(
            f'<circle cx="{px(cx):.1f}" cy="{py(cy):.1f}" r="{r:.1f}" fill="#3e4650" '
            f'stroke="#1c2228" stroke-width="0.7" filter="url(#soft)"/>'
            f'<circle cx="{px(cx):.1f}" cy="{py(cy):.1f}" r="{r * 0.62:.1f}" fill="#cfd5db"/>'
            f'<rect x="{px(cx) - 0.7:.1f}" y="{py(cy) - r * 0.35:.1f}" width="1.4" '
            f'height="{r * 0.7:.1f}" fill="#8a5a00"/>'
        )
    elif kind == "crystal":
        bits.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{min(w, h) * 0.45:.1f}" '
            f'fill="#d8dce0" stroke="#8a9198" stroke-width="0.8" filter="url(#soft)"/>'
            f'<rect x="{x + 2.2:.1f}" y="{y + 1.6:.1f}" width="{max(1, w - 4.4):.1f}" '
            f'height="{max(1, h - 3.2):.1f}" rx="0.8" fill="#eef1f4"/>'
        )
    elif kind == "led":
        colour = "#c0282c" if "1" in footprint.ref else "#0b7a5f"
        bits.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx:.1f}" '
            f'fill="{colour}" stroke="#1a1a1a" stroke-width="0.5" opacity=".92" '
            f'filter="url(#soft)"/>'
            f'<ellipse cx="{px(cx):.1f}" cy="{py(cy) - h * 0.08:.1f}" rx="{w * 0.28:.1f}" '
            f'ry="{h * 0.22:.1f}" fill="#fff" opacity=".28"/>'
        )
    elif kind == "resistor":
        bits.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="0.6" '
            f'fill="#d7b48a" stroke="#8a6a42" stroke-width="0.5"/>'
        )
    elif kind == "cap":
        bits.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="0.5" '
            f'fill="#c4a06a" stroke="#7a6240" stroke-width="0.5"/>'
        )
    elif kind == "diode":
        bits.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="0.5" '
            f'fill="#2a2e33" stroke="#111" stroke-width="0.5"/>'
            f'<rect x="{x + w * 0.72:.1f}" y="{y:.1f}" width="{max(1.2, w * 0.1):.1f}" '
            f'height="{h:.1f}" fill="#d8dce0"/>'
        )
    else:
        bits.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="0.5" '
            f'fill="#3a4048" stroke="#1c2026" stroke-width="0.4" opacity=".92"/>'
        )

    if _labelled(kind):
        size = max(8.5, min(13.0, min(w, h) * 0.38))
        ly = y - 3.5
        if ly < 12:
            ly = y + h / 2 + 4
        bits.append(
            f'<text x="{px(cx):.1f}" y="{ly:.1f}" font-family="{SANS}" font-size="{size:.1f}" '
            f'font-weight="650" fill="{SILK}" text-anchor="middle">{_esc(footprint.ref)}</text>'
        )
    bits.append("</g>")
    return bits


# ------------------------------------------------------------------ 3D view --
def render_3d(board: Board, scale: float = 14.0, board_thickness: float = 1.6) -> str:
    """Isometric board with extruded components, painter's algorithm."""
    palette = _palette(board)
    cos30, sin30 = math.cos(math.radians(30)), math.sin(math.radians(30))
    min_x, min_y, max_x, max_y = _bounds(board)
    span_w, span_h = max_x - min_x, max_y - min_y
    span_x = (span_w + span_h) * cos30 * scale
    span_y = (span_w + span_h) * sin30 * scale
    ox = span_x / 2 + 20
    oy = 36 + span_h * sin30 * scale

    def iso(x: float, y: float, z: float) -> tuple[float, float]:
        dx, dy = x - min_x, y - min_y
        return (ox + (dx - dy) * cos30 * scale,
                oy + (dx + dy) * sin30 * scale - z * scale)

    def poly(points: list[tuple[float, float]], fill: str, stroke: str | None = None,
             opacity: float = 1.0) -> str:
        pts = " ".join(f"{_r(a)},{_r(b)}" for a, b in points)
        line = f' stroke="{stroke}" stroke-width="0.6" stroke-linejoin="round"' if stroke else ""
        return f'<polygon points="{pts}" fill="{fill}" opacity="{opacity}"{line}/>'

    width = span_x + 40
    height = oy + span_y + 40
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="100%" role="img" aria-label="PCB isometric view, {board.width:g} by '
        f'{board.height:g} millimetres">',
        "<defs>",
        '<linearGradient id="m3" x1="0" y1="0" x2="0.6" y2="1">'
        f'<stop offset="0" stop-color="{palette["mask_light"]}"/>'
        f'<stop offset="1" stop-color="{palette["mask"]}"/></linearGradient>',
        "</defs>",
        f'<ellipse cx="{_r(ox + (span_w - span_h) * cos30 * scale / 2)}" '
        f'cy="{_r(oy + (span_w + span_h) * sin30 * scale + 8)}" '
        f'rx="{_r((span_w + span_h) * cos30 * scale / 2.4)}" '
        f'ry="12" fill="#0a1420" opacity="0.12"/>',
    ]

    corners = [(0, 0), (board.width, 0), (board.width, board.height), (0, board.height)]
    top = [iso(x, y, board_thickness) for x, y in corners]
    out.append(poly([top[3], top[2], (top[2][0], top[2][1] + board_thickness * scale),
                     (top[3][0], top[3][1] + board_thickness * scale)], palette["mask_dark"]))
    out.append(poly([top[1], top[2], (top[2][0], top[2][1] + board_thickness * scale),
                     (top[1][0], top[1][1] + board_thickness * scale)], palette["mask_dark"],
                    opacity=0.92))
    out.append(poly(top, "url(#m3)", stroke=palette["mask_dark"]))
    for hx, hy in _mount_holes(board):
        vx, vy = iso(hx, hy, board_thickness)
        out.append(
            f'<circle cx="{_r(vx)}" cy="{_r(vy)}" r="{_r(1.6 * scale)}" fill="{HOLE}"/>'
        )

    for segment in board.segments:
        x1, y1 = iso(segment.x1, segment.y1, board_thickness)
        x2, y2 = iso(segment.x2, segment.y2, board_thickness)
        colour = palette["trace"] if segment.layer == "F.Cu" else palette["trace_b"]
        opacity = 0.85 if segment.layer == "F.Cu" else 0.4
        out.append(
            f'<line x1="{_r(x1)}" y1="{_r(y1)}" x2="{_r(x2)}" y2="{_r(y2)}" '
            f'stroke="{colour}" stroke-width="{_r(segment.width * scale * 0.9)}" '
            f'stroke-linecap="round" opacity="{opacity}"/>'
        )

    for footprint in sorted(board.footprints, key=lambda f: f.x + f.y):
        kind = kind_of(footprint)
        w, d = _visual_size(footprint, kind)
        h = _height(footprint)
        cx, cy = _centre(footprint)
        x0, y0 = cx - w / 2, cy - d / 2
        x1, y1 = cx + w / 2, cy + d / 2
        quad = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        z0, z1 = board_thickness, board_thickness + h
        base = [iso(px_, py_, z0) for px_, py_ in quad]
        cap = [iso(px_, py_, z1) for px_, py_ in quad]
        fill_top, fill_a, fill_b = _kind_colours(kind)
        out.append(poly([base[1], base[2], cap[2], cap[1]], fill_b))
        out.append(poly([base[2], base[3], cap[3], cap[2]], fill_a))
        out.append(poly(cap, fill_top, stroke="#0f1216"))
        for pad in footprint.pads:
            pw, pd = pad.w / 2, pad.h / 2
            pad_quad = [
                iso(pad.x - pw, pad.y - pd, z0), iso(pad.x + pw, pad.y - pd, z0),
                iso(pad.x + pw, pad.y + pd, z0), iso(pad.x - pw, pad.y + pd, z0),
            ]
            out.append(poly(pad_quad, palette["pad_hi"], stroke=palette["pad_edge"]))
        if _labelled(kind):
            lx, ly = iso(cx, cy, z1)
            out.append(
                f'<text x="{_r(lx)}" y="{_r(ly - 2)}" font-family="{SANS}" font-size="10" '
                f'fill="{SILK}" text-anchor="middle" opacity=".9">{_esc(footprint.ref)}</text>'
            )

    for via in board.vias:
        vx, vy = iso(via.x, via.y, board_thickness)
        out.append(
            f'<circle cx="{_r(vx)}" cy="{_r(vy)}" r="{_r(via.size * scale / 2.4)}" '
            f'fill="{palette["pad"]}" opacity=".9"/>'
        )
    out.append("</svg>")
    return "".join(out)


def _kind_colours(kind: str) -> tuple[str, str, str]:
    table = {
        "usb": ("#c5ccd3", "#8b949e", "#6f777f"),
        "jack": ("#1a1a1a", "#111", "#0a0a0a"),
        "header": ("#1a1a1a", "#111", "#0a0a0a"),
        "dip": ("#1c1c1c", "#141414", "#0d0d0d"),
        "ic": ("#222", "#161616", "#0e0e0e"),
        "electrolytic": ("#cfd5db", "#3e4650", "#1c2228"),
        "crystal": ("#e8ebef", "#b0b6bc", "#8a9198"),
        "led": ("#c0282c", "#8a1c1f", "#5c1214"),
        "resistor": ("#d7b48a", "#8a6a42", "#6a5030"),
        "cap": ("#c4a06a", "#7a6240", "#5a4830"),
        "diode": ("#2a2e33", "#191c20", "#101214"),
    }
    return table.get(kind, ("#3a4048", "#2a2e33", "#1a1d22"))


def board_model(board: Board, thickness: float = 1.6) -> dict:
    """Everything the 360-degree view needs, small enough to inline."""
    return {
        "w": round(board.width, 2),
        "h": round(board.height, 2),
        "t": thickness,
        "look": "arduino" if _is_arduino(board) else "proto",
        "holes": [[round(x, 2), round(y, 2)] for x, y in _mount_holes(board)],
        "parts": [
            {
                "ref": f.ref, "rot": round(f.rotation, 2), "kind": kind_of(f),
                "x": round(_centre(f)[0], 2), "y": round(_centre(f)[1], 2),
                "w": round(_visual_size(f, kind_of(f))[0], 2),
                "d": round(_visual_size(f, kind_of(f))[1], 2),
                "quad": [
                    [round(_centre(f)[0] - _visual_size(f, kind_of(f))[0] / 2, 2),
                     round(_centre(f)[1] - _visual_size(f, kind_of(f))[1] / 2, 2)],
                    [round(_centre(f)[0] + _visual_size(f, kind_of(f))[0] / 2, 2),
                     round(_centre(f)[1] - _visual_size(f, kind_of(f))[1] / 2, 2)],
                    [round(_centre(f)[0] + _visual_size(f, kind_of(f))[0] / 2, 2),
                     round(_centre(f)[1] + _visual_size(f, kind_of(f))[1] / 2, 2)],
                    [round(_centre(f)[0] - _visual_size(f, kind_of(f))[0] / 2, 2),
                     round(_centre(f)[1] + _visual_size(f, kind_of(f))[1] / 2, 2)],
                ],
                "z": _height(f),
                "pads": [{"x": round(p.x, 2), "y": round(p.y, 2),
                          "w": round(p.w, 2), "d": round(p.h, 2)} for p in f.pads],
            }
            for f in board.footprints
        ],
        "tracks": [{"x1": round(s.x1, 2), "y1": round(s.y1, 2),
                    "x2": round(s.x2, 2), "y2": round(s.y2, 2),
                    "w": round(s.width, 2), "b": s.layer == "B.Cu"}
                   for s in board.segments],
        "vias": [{"x": round(v.x, 2), "y": round(v.y, 2), "s": round(v.size, 2)}
                 for v in board.vias],
    }


def render_pair(board: Board) -> tuple[str, str]:
    return render_2d(board), render_3d(board)


def write_previews(board: Board, svg: Path) -> None:
    """Write the three companion files for an imported or generated board."""
    top, iso = render_pair(board)
    model = json.dumps(board_model(board), separators=(",", ":")) + "\n"
    svg.parent.mkdir(parents=True, exist_ok=True)
    for path, content in (
        (svg, top), (svg.with_name(svg.stem + "-3d.svg"), iso),
        (svg.with_name(svg.stem + "-model.json"), model),
    ):
        path.write_text(content, encoding="utf-8")
