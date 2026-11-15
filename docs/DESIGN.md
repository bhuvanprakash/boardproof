# BoardProof design system

Source of truth: `boardproof/brand.py` (mark, icons, `TOKENS`). The dashboard,
the check report and the passport all import from it, so the three artifacts
cannot drift apart visually.

## Colour

| role | light | meaning |
| --- | --- | --- |
| surface | `#f4f6f9` / `#ffffff` / `#f4f6fa` | page, card, inset |
| ink | `#101a26` / `#465266` / `#6b7889` / `#98a3b3` | primary, secondary, tertiary, quaternary |
| verified | `#0b7a5f` | a check that passed |
| blocked | `#c0282c` | a violation that stops fabrication |
| caution | `#8a5a00` | scope a pass does not cover |
| reference | `#1f5aa8` | a citation back to the datasheet |

> one accent per meaning; teal is never decorative

## Type

- **display** — `ui-sans-serif 48/1.05 -0.03em 800`
- **title** — `ui-sans-serif 21/1.25 -0.02em 750`
- **body** — `ui-sans-serif 15/1.6 400`
- **label** — `ui-monospace 10/1 .14em uppercase`
- **mono** — `ui-monospace 11.5/1.7`

Mono is reserved for anything a machine produced (net names, page numbers, hashes).
Sans is for anything a human wrote (headlines, explanations, verdicts).

## Space and radius

- space scale: `4 · 8 · 12 · 16 · 22 · 30 · 44 · 60`
- radii: pill 99px · card 14px · panel 16px · button 9px · chip 6px

## Rules

1. hairlines not boxes: prefer 1px var(--line) over a new container
1. one primary action per panel; everything else is a ghost button
1. colour only encodes a verdict, never decoration
1. mono for anything a machine produced, sans for anything a human wrote
1. every number states its unit and its source

## Mark

A rounded board outline, two copper pads, and a route that resolves into a
check. It reads as *verified board*, which is the product, not *PCB tool*.
Inline SVG only — no network, no font dependency, works in a `file://` artifact.

```python
from boardproof.brand import mark, icon, FAVICON
mark(24)                 # header
mark(18, colour='#13171d')  # monochrome, for the paper passport
icon('pcb', 16)          # 16 px optic grid, currentColor
```

## Verification

Contrast is a test, not a review note: `tests/test_contrast.py` computes WCAG ratios for every
ink role against both surfaces in both themes, asserts >= 4.5:1, asserts the hierarchy still
holds, and fails if the CSS drifts from `brand.PALETTE`.

The full resolution (what the `ui-ux-pro-max` dataset recommended, what we adopted, and what we
deviated from with reasons) lives in `design-system/boardproof/MASTER.md`.
