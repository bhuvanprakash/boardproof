"""Preview assets: datasheet pages rendered from the real PDF, and a schematic
derived from the netlist connectivity.

Nothing here invents geometry. The datasheet page is the publisher's page; the
schematic is a drawn graph of the same pins the checker verified.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .model import Design

MONO = "ui-monospace,SFMono-Regular,monospace"


# --------------------------------------------------------------- datasheets --
def render_pdf_page(pdf: Path, page: int | str, out_png: Path, dpi: int = 110) -> dict:
    """Rasterise one page of a real PDF. Reports honestly when it cannot."""
    pdf, out_png = Path(pdf), Path(out_png)
    if not pdf.is_file():
        return {"available": False, "note": f"datasheet not on disk: {pdf.name}"}
    tool = shutil.which("pdftoppm")
    if not tool:
        return {"available": False, "note": "pdftoppm (poppler) not installed"}
    try:
        page_number = max(1, int(str(page).strip()))
    except (TypeError, ValueError):
        return {"available": False, "note": f"page {page!r} is not a number"}
    out_png.parent.mkdir(parents=True, exist_ok=True)
    prefix = out_png.with_suffix("")
    try:
        proc = subprocess.run(
            [tool, "-f", str(page_number), "-l", str(page_number), "-r", str(dpi),
             "-png", "-singlefile", str(pdf), str(prefix)],
            capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "note": f"pdftoppm failed: {exc}"}
    produced = prefix.with_suffix(".png")
    if proc.returncode != 0 or not produced.is_file():
        return {"available": False,
                "note": (proc.stderr or "pdftoppm produced no image").strip()[:200]}
    return {"available": True, "page": page_number, "image": produced.name,
            "pdf": pdf.name, "bytes": produced.stat().st_size}


# --------------------------------------------------------------- schematic ---
def render_schematic(design: Design, width: float = 980) -> str:
    """A schematic drawn from the netlist: blocks for parts, rails for nets.

    This is *derived connectivity*, not the original drawing — it carries the label
    to say so. It exists so a reviewer can see the circuit before downloading.
    """
    components = [c for c in design.components.values()]
    components.sort(key=lambda c: (c.ref[:1].upper() != "U", c.ref))
    nets = sorted(design.nets)
    row_h = 74
    pad_top, pad_left = 54, 168
    height = max(240, pad_top + row_h * max(len(components), len(nets)) + 40)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
           f'width="100%" role="img" aria-label="schematic derived from the netlist">',
           f'<rect width="100%" height="100%" fill="#ffffff"/>',
           f'<text x="20" y="26" font-family="{MONO}" font-size="11" fill="#6b7889">'
           f'schematic · derived from {Path(design.source).name} connectivity</text>',
           f'<text x="{width - 320:.0f}" y="26" font-family="{MONO}" font-size="11" '
           f'fill="#98a3b3">{len(components)} parts · {len(nets)} nets</text>']

    # parts, left column
    for index, comp in enumerate(components):
        y = pad_top + index * row_h
        pins = len(comp.pins)
        box = 20 + pins * 11
        out.append(f'<rect x="24" y="{y}" width="132" height="{box}" rx="3" fill="#f7f9fc" '
                   f'stroke="#465266" stroke-width="1"/>')
        out.append(f'<text x="32" y="{y + 15}" font-family="{MONO}" font-size="11" '
                   f'fill="#101a26" font-weight="600">{comp.ref}</text>')
        out.append(f'<text x="32" y="{y + 29}" font-family="{MONO}" font-size="9" '
                   f'fill="#6b7889">{(comp.part or comp.value)[:20]}</text>')
        for pin_index, pin in enumerate(sorted(comp.pins.values(), key=lambda p: p.number)):
            py = y + 42 + pin_index * 11
            out.append(f'<line x1="156" y1="{py}" x2="176" y2="{py}" stroke="#465266" '
                       f'stroke-width="1"/>')
            out.append(f'<text x="150" y="{py + 3}" font-family="{MONO}" font-size="8" '
                       f'fill="#98a3b3" text-anchor="end">{pin.number}</text>')
            out.append(f'<text x="180" y="{py + 3}" font-family="{MONO}" font-size="8.5" '
                       f'fill="#465266">{pin.name or "—"}</text>')

    # nets, right column: one rail per net, with every pin that lands on it
    rail_x = 420
    for index, net in enumerate(nets):
        y = pad_top + 18 + index * 42
        members = design.nets[net]
        reach = max(240, 90 + len(members) * 46)
        colour = "#0b7a5f" if net.upper() in {"3V3", "5V", "VCC", "VDD"} else (
            "#8a5a00" if net.upper() in {"GND", "VSS"} else "#1f5aa8")
        out.append(f'<line x1="{rail_x}" y1="{y}" x2="{rail_x + reach}" y2="{y}" '
                   f'stroke="{colour}" stroke-width="1.6"/>')
        out.append(f'<text x="{rail_x - 8}" y="{y + 3}" font-family="{MONO}" font-size="10" '
                   f'fill="{colour}" text-anchor="end" font-weight="600">{net}</text>')
        for member_index, (ref, number) in enumerate(members):
            tx = rail_x + 26 + member_index * 46
            out.append(f'<circle cx="{tx}" cy="{y}" r="2.4" fill="{colour}"/>')
            out.append(f'<text x="{tx}" y="{y - 6}" font-family="{MONO}" font-size="8" '
                       f'fill="#6b7889" text-anchor="middle">{ref}.{number}</text>')

    # a note, because a derived drawing must say so
    out.append(f'<text x="24" y="{height - 16}" font-family="{MONO}" font-size="9.5" '
               f'fill="#98a3b3">derived connectivity, not the original schematic sheet — '
               f'net names and pin numbers come from the export</text>')
    out.append("</svg>")
    return "".join(out)
