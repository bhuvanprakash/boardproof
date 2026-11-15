# BoardProof — design system (master)

Resolved with `ui-ux-pro-max` for the query **"hardware verification engineering dashboard dense"**
(dials: variance 4, motion 3, density 8). Style match: **Data-Dense Dashboard**, light + dark.

## Verified, and adopted

| Guidance from the dataset | Adopted as |
| --- | --- |
| Data-Dense Dashboard style; KPI cards, minimal padding, maximum data visibility | the four-tile strip, 12 px grid gutters, hairline tables |
| Density 8 → 8–32 px spacing scale | section head 36 px, card padding 15–17 px, tile padding 14 px |
| `requires: contrast-text-4.5, keyboard, visible-focus, reduced-motion` | `tests/test_contrast.py` enforces all four |
| "Minimum 4.5:1 ratio for normal text" | all four ink roles re-cut: `#6b7889→#5f6c7d`, `#98a3b3→#647085` (light), `#5d6d80→#8b9aae` (dark) |
| "Visible focus ring on every interactive control" | `:focus-visible` ring on buttons, chips, links, selects, the dropzone |
| "Keyboard focus must not be obscured by persistent UI" | `html { scroll-padding-top: 84px }` under the sticky bar, plus a skip link |
| "Reduced motion" | `prefers-reduced-motion` kills transitions/animation globally |
| Enterprise/data mood | system sans for human text, system mono for machine output |

## Verified, and deliberately deviated

| Dataset said | We did | Why |
| --- | --- | --- |
| Primary `#1E40AF`, accent `#D97706` | teal `#0b7a5f` | the product's colour is *semantic*: teal = verified, red = blocked, amber = unverified scope. A brand navy would collide with the "verified" signal. |
| Fira Sans / Fira Code via Google Fonts | system `ui-sans-serif` / `ui-monospace` | `report.html` and `passport.html` must open from `file://` with **no network** and stay single-file. |
| GSAP scroll reveal | none | same reason: no JS dependency in the artifacts; motion is limited to 150 ms hover/press transitions. |
| "Enterprise Gateway" landing pattern (mega menu, contact sales) | not used | this is a tool surface, not a marketing site; the pattern resolves from the query's "enterprise" term, not from the product. |

## Tokens

Source of truth: `boardproof/brand.py` → `PALETTE`, `TOKENS`, `mark()`, `icon()`.
Prose version: `docs/DESIGN.md`. The dashboard, the check report and the passport all import it.

Contrast contract (enforced in CI): every ink role ≥ **4.5:1** against both `page` and `card`,
in both themes, with `ink > ink2 > ink3 > ink4` hierarchy preserved.

## Components

- **Run panel** — one primary (`Prove it`), grouped secondaries (`circuit` / `layout` / `evidence`),
  icon-only refresh, `aria-busy` + focus moves to the output log when a run ends.
- **Board preview** — gallery card: dotted measuring grid, `VERIFIED`/`BLOCKED` stamp, definition
  grid for specs, checks grouped by circuit vs layout.
- **Passport** — paper theme, monochrome mark, mandatory unverified column.
- **Report** — dark-on-light CI artifact with the same tokens and the same mark.

## Anti-patterns to avoid (from the dataset, all honoured)

- Ornate design → no gradients except two soft background washes.
- No filtering → artifact search + kind chips exist.
- Emoji as icons → inline SVG set of 9, `currentColor`, 16 px optic grid.
