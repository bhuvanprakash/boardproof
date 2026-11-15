"""BoardProof visual identity, as code.

One mark, one icon set, one token contract. Everything is inline SVG so the
reports and the passport stay single-file artifacts that open from `file://`.
"""
from __future__ import annotations

# ---------------------------------------------------------------- the mark ---
# A board outline with rounded corners, two copper pads, and a check routed
# between them: "this board was verified", not "this is a PCB tool".
MARK = (
    '<svg class="bp-mark" viewBox="0 0 24 24" width="{size}" height="{size}" '
    'fill="none" aria-hidden="true">'
    '<defs><linearGradient id="bpg" x1="2" y1="1" x2="22" y2="23" gradientUnits="userSpaceOnUse">'
    '<stop stop-color="#149b7c"/><stop offset="1" stop-color="#0a5f4c"/></linearGradient></defs>'
    '<rect x="1" y="1" width="22" height="22" rx="6" fill="url(#bpg)"/>'
    '<rect x="1" y="1" width="22" height="22" rx="6" stroke="#ffffff" stroke-opacity=".18"/>'
    '<path d="M6.6 12.4l3.4 3.3 7.4-7.2" stroke="#ffffff" stroke-width="2.1" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<rect x="4.9" y="10.7" width="3.4" height="3.4" rx="1" fill="#ffffff" fill-opacity=".22"/>'
    '<rect x="15.7" y="6.4" width="3.4" height="3.4" rx="1" fill="#ffffff" fill-opacity=".22"/>'
    "</svg>"
)

FAVICON = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E"
    "%3Crect width='24' height='24' rx='6' fill='%23149b7c'/%3E"
    "%3Cpath d='M6.6 12.4l3.4 3.3 7.4-7.2' stroke='white' stroke-width='2.4' "
    "stroke-linecap='round' stroke-linejoin='round' fill='none'/%3E%3C/svg%3E"
)


def mark(size: int = 22, colour: str | None = None) -> str:
    """The logo mark. `colour` swaps the gradient for a flat fill."""
    markup = MARK.format(size=size)
    if colour:
        markup = markup.replace('fill="url(#bpg)"', f'fill="{colour}"')
    return markup


# --------------------------------------------------------------- icon set ---
# 16 px optical grid, 1.6 stroke, `currentColor` so buttons can tint them.
_PATHS = {
    "prove": '<path d="M5.5 3.9l8.6 5.1-8.6 5.1z" fill="currentColor" stroke="none"/>',
    "check": '<path d="M3.5 8.6l3 3 6-6.4"/><circle cx="8" cy="8" r="6.5"/>',
    "design": '<rect x="2.5" y="2.5" width="11" height="11" rx="2"/>'
              '<path d="M6 13.5v-.01M9.9 13.5v-.01M13.5 6v.01M13.5 9.9v.01"/>',
    "pcb": '<path d="M8 2.6l5.4 2.7v5.4L8 13.4 2.6 10.7V5.3z"/><path d="M2.6 5.3L8 8l5.4-2.7M8 8v5.4"/>',
    "redteam": '<path d="M8 2.8v2M8 11.2v2M3.4 6.4l1.4.8M11.2 8.8l1.4.8M3.4 9.6l1.4-.8M11.2 5.2l1.4-.8"/>'
               '<circle cx="8" cy="8" r="3.2"/>',
    "passport": '<rect x="3.4" y="2.6" width="9.2" height="10.8" rx="1.6"/>'
                '<path d="M5.9 6h4.2M5.9 8.4h4.2M5.9 10.8h2.4"/>',
    "refresh": '<path d="M13 8a5 5 0 1 1-1.6-3.6"/><path d="M13.2 2.4v2.4h-2.4"/>',
    "upload": '<path d="M8 10.5V2.8"/><path d="M5.2 5.5L8 2.7l2.8 2.8"/>'
              '<path d="M2.8 10v2.4c0 .6.5 1.1 1.1 1.1h8.2c.6 0 1.1-.5 1.1-1.1V10"/>',
    "board": '<rect x="2.4" y="2.4" width="11.2" height="11.2" rx="2"/>'
             '<path d="M5.4 5.4h2.2v2.2H5.4zM8.4 8.4h2.2v2.2H8.4z" fill="currentColor" stroke="none"/>',
}


def icon(name: str, size: int = 16, stroke: float = 1.6) -> str:
    path = _PATHS.get(name)
    if not path:
        return ""
    return (
        f'<svg class="bp-icon" viewBox="0 0 16 16" width="{size}" height="{size}" fill="none" '
        'stroke="currentColor" stroke-width="' + str(stroke) + '" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">' + path + "</svg>"
    )


# ----------------------------------------------------------------- tokens ---
# Any change here must keep every text role >= 4.5:1 on its own surface.
# tests/test_contrast.py enforces that, and that the CSS uses these exact values.
PALETTE = {
    "light": {"page": "#f4f6f9", "card": "#ffffff",
              "ink": "#101a26", "ink2": "#465266", "ink3": "#5f6c7d", "ink4": "#647085"},
    "dark": {"page": "#0b1119", "card": "#111a25",
             "ink": "#e8f0fa", "ink2": "#a7b6c9", "ink3": "#93a3b6", "ink4": "#8b9aae"},
}


TOKENS = {
    "colour": {
        "surface": ["#f4f6f9", "#ffffff", "#f4f6fa"],
        "ink": ["#101a26", "#465266", "#6b7889", "#98a3b3"],
        "signal": {"verified": "#0b7a5f", "blocked": "#c0282c", "caution": "#8a5a00",
                   "reference": "#1f5aa8"},
        "note": "one accent per meaning; teal is never decorative",
    },
    "type": {
        "display": "ui-sans-serif 50/1.05 -0.03em 800",
        "title": "ui-sans-serif 23/1.25 -0.02em 750",
        "body": "ui-sans-serif 17/1.6 400",
        "label": "ui-monospace 12/1 .14em uppercase",
        "mono": "ui-monospace 13.5/1.7",
    },
    "space": [4, 8, 12, 16, 22, 30, 44, 60],
    "radius": {"pill": "99px", "card": "14px", "panel": "16px", "button": "9px", "chip": "6px"},
    "rules": [
        "hairlines not boxes: prefer 1px var(--line) over a new container",
        "one primary action per panel; everything else is a ghost button",
        "colour only encodes a verdict, never decoration",
        "mono for anything a machine produced, sans for anything a human wrote",
        "every number states its unit and its source",
    ],
}
