# Jeden-Board — a real Arduino-compatible board (ATmega328P)

Source: **Wojtekb30/Jeden-board** (GitHub, open hardware). Downloaded unchanged:

| file | size | what it is |
| --- | --- | --- |
| `Jeden-Board.kicad_pcb` | 316 KB | the layout: 29 footprints, 148 pads, 519 tracks, 94 vias |
| `Jeden-Board.kicad_sch` | 230 KB | the schematic |

## What BoardProof does with it

```sh
kicad-cli sch export netlist --format kicadsexpr -o ../jeden.net Jeden-Board.kicad_sch
boardproof verify --board Jeden-Board.kicad_pcb --netlist ../jeden.net --outdir artifacts
```

```
VERIFIED LAYOUT: 29 footprints · 148 pads · 36 nets · 63 × 78.38 mm
  ! copper extends past the routed edge: outline 62.5×61.5 mm, copper 53.8×77.9 mm
  netlist: 29 components, 36 nets
  2 error(s) · 318 warning(s) · 36 notice(s)
  policy: advisory (CLEARANCE, DECOUPLING_DISTANCE, TRACK_CURRENT)
```

- **imported**: components, pins and nets straight from KiCad's own netlist export
- **cross-checked**: every board pad's net against the schematic (`PAD_NET_MISMATCH`)
- **rendered**: 2D top view, isometric 3D, and the 360° spinner model
- **judged**: 2 hard errors (two pads on U2 with no schematic pin), everything geometric is
  *advisory* because KiCad's DRC is the authority on a hand-routed board

## Why the copper note matters

This project's DIP-28 socket (U1) reaches 16 mm past its own `Edge.Cuts` rectangle. The file
says so; BoardProof grows the drawing to cover the copper and records the fact rather than
clipping the part out of the picture.

## Reproduce

```sh
boardproof verify --board boards/jeden-arduino/Jeden-Board.kicad_pcb \
                  --netlist boards/jeden-arduino/jeden.net --outdir artifacts \
                  --title "Jeden Arduino (ATmega328P)"
cp /tmp/jeden.net boards/jeden-arduino/jeden.net   # keep the exported netlist with the board
```
