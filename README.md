# BoardProof · hardware CI starter v0.2

**GitHub Actions for hardware designs.** A conservative tool for checking *known* electrical and firmware constraints against a real EasyEDA Pro netlist **before** PCB fabrication.

Repo: https://github.com/bhuvanprakash/boardproof

The demo deliberately contains a fictional MCU and sensor; it is **not** an ESP32 schematic or a manufacturing-ready circuit. No silicon pinouts or datasheet values are implied by the demo.

## The trust chain

An LLM may **propose** a constraint. It may never **enforce** one. That boundary is code, not a prompt:

```
datasheet.pdf ──► boardproof infer ──► *.propose.json   status=proposed  (untrusted)
                                             │
                                 boardproof vet --reviewer <name>      ← the only promotion path
                                             ▼
                                       packs/*.json     status=vetted, reviewed_by, cited pages
                                             │
board.enet + firmware.h ──► boardproof check ──► findings + provenance
                                             │
                                 boardproof check --explain            ← read-only prose
                                             ▼
                                       report.html / report.json
```

Three invariants are enforced structurally:

1. **No citation, no limit.** A rule asserting `max_v`, `min_v`, `min_ohms` or `max_ohms` without a page number and an exact quote is rejected at load time.
2. **No reviewer, no enforcement.** `check` against a `proposed` pack exits **2** (cannot verify), never **0** (clean).
3. **The model cannot widen the evidence base.** Explanations citing a page BoardProof did not supply are dropped, and an explanation can never change a verdict — there is a test that asserts exactly that.

## Commands

| Command | Purpose | Network |
| --- | --- | --- |
| `boardproof check` | Enforce vetted packs + inline rules. Exit 0 pass / 1 findings / 2 cannot verify | no |
| `boardproof infer` | Read a datasheet PDF, propose cited constraints, diff against the current pack | Gemini (or `--engine offline --fixture`) |
| `boardproof vet` | Human gate: attach a reviewer name, flip `proposed → vetted` | no |
| `boardproof explain` | Grounded explanation of current findings | Gemini (or offline) |
| `boardproof redteam` | Inject faults into a known-good design and score the rule set | no |
| `boardproof diff` | Block a PR only on **newly introduced** violations | no |
| `boardproof bench` | Throughput on a synthetic board; fails a CI perf budget | no |
| `boardproof init` | Draft a `boardproof.json` from a fresh netlist export | no |
| `boardproof passport` | Manufacturing Preflight Passport (printable HTML + hashed JSON) | no |
| `boardproof dashboard` | One page linking every artifact | no |
| `boardproof serve` | Serve the artifacts (Cloud Run compatible, stdlib only) | no |
| `boardproof studio` | Dashboard control room: prove, check, design, passport | no |
| `boardproof design` | Verified schematic → editable `.kicad_pcb` + SVG | no |
| `boardproof pcb-check` | Re-read the board from disk and prove it (KiCad DRC) | no |
| `boardproof pcb-redteam` | Mutate the board, score the layout verifier | no |
| `boardproof prove` | The whole journey in one run, exit code and all | optional |

`venv`/install, then the full chain:

```sh
boardproof infer --pdf examples/demo/demo-mcu-SIMULATED.pdf --component U1 \
  --netlist examples/demo/broken.enet --out packs/u1.propose.json \
  --engine offline --fixture examples/demo/fixtures/demo-mcu.facts.json

boardproof check --config examples/demo/boardproof.pack.json   # exits 2: pack is not vetted
boardproof vet --proposal packs/u1.propose.json --reviewer "Your Name"
boardproof check --config examples/demo/boardproof.pack.json --explain --html artifacts/pack.html
```

## Does the rule set actually work? (red team)

`boardproof redteam` mutates a known-good design in ways a real engineer could: swap a supply
rail, float a ground, delete a pull-up, drift a resistor value 100x, shift a firmware pin.
Faults are derived from the rules themselves, so every targeted fault is relevant by construction.

```
RED TEAM  8/8 targeted faults caught (100%)  ·  1 blind spot(s)  ·  1 unverifiable from a netlist
  [PASS] supply_swap      U1.1 (VDD) reconnected to 5V instead of 3V3
         caught by MAX_VOLTAGE
  [GAP ] net_typo         one-character net rename strands U1.4 (GPIO5, DEBUG)
         nothing constrains this yet
  [SKIP] not_representable symbol pin order disagrees with the physical footprint
         a .enet netlist carries pin numbers, not footprint pads - needs PCB-level data
```

Blind spots are reported with the rule that would close them, and `--min-score 1.0` turns
that into a CI gate: a rule that cannot be mutated is decoration.

## Revision gate, not a backlog

`boardproof diff --base base.json --head pr.json` separates **introduced** from **pre-existing**
violations, so a hardware PR is blocked by the regression it adds, not by history:

```
BoardProof revision diff: 0 error(s) -> 5 error(s)  (passed -> failed)
  [NEW  ] MAX_VOLTAGE: U1.1 on 5V has declared 5 V; allowed 2.7 to 3.6 V  (regression)
  VERDICT: this revision introduces new hardware violations - blocked
```

## Speed

The `resistor_between` check used to scan every component for every rule — O(rules x components).
`boardproof/index.py` builds a net-pair table once per design, so it is O(components + rules).
Net and pin lookups are cached on the design; rule packs and firmware files are validated once per
(path, mtime, size) and handed out as private copies.

```
$ boardproof bench --components 20000 --rules 4000
BoardProof bench  20,000 components · 40,002 nets · 4,000 rules (best of 2)
  netlist parse     156.91 ms
  checks              9.12 ms   (438,833 rules/s)
```

CI enforces a budget (`--max-checks-ms`) so this cannot silently regress.

## Onboarding a real board

```sh
boardproof init --netlist board.enet --firmware src/pins.h   # drafts rules
boardproof check --config boardproof.json                    # exit 0: warnings only
```

`init` emits every rule as `severity: "warning"` with a `DRAFT` note and tells you which
numbers it guessed. A generated rule **cannot** block a build — promotion to `error` is a human
edit. That keeps the same invariant as the AI path: nothing invented is ever enforced.

## Manufacturing Preflight Passport

`boardproof passport` produces a printable one-pager (plus hashed JSON) that answers three
questions in order: **what failed**, **what was actually verified and by whom**, and **what
remains unverified**. The last section is mandatory — a PASS is only as wide as its scope list.
Each passport carries a `passport_hash` over the netlist hash, the packs, the reviewers and the
findings, so two revisions can be compared without trusting either file.

```sh
boardproof passport --config boardproof.json --revision "Rev B" \
  --redteam artifacts/redteam.json --base artifacts/previous.json \
  --out artifacts/passport.html --json artifacts/passport.json
```

## Studio: run it from the dashboard

```sh
boardproof studio --dir artifacts        # http://localhost:8080
```

The dashboard becomes a control room: pick a `boardproof.json`, press **Prove it** and the
whole journey runs in-process, streams its log into the page, rewrites the artifact cards and
reloads. Every action is a fixed function from this package — no shell, no arbitrary paths:
`prove`, `check`, `design`, `pcb`, `redteam`, `passport`, `refresh`. Configs are discovered
inside `--root`, and a request naming a path outside it is refused.

Same process serves Cloud Run (`/healthz`, `PORT`). Opened as a plain file, the buttons are
inert and say so — there is no hidden network dependency.

### The board is on the dashboard

`artifacts/*.svg` is rendered inline, on a grid backdrop, next to the facts that matter: footprints,
pads, board size, copper, the `pcb-check` verdict and the checks that passed — including
*land pattern vs datasheet* and *IPC-2221 current capacity*. When the router declined, the panel
says **routing not attempted**; it never shows a green board that was not verified.

## Demo surface

```sh
boardproof dashboard --dir artifacts   # artifacts/index.html
boardproof serve --dir artifacts       # http://localhost:8080 (+ /healthz for Cloud Run)
```

`serve` is the stdlib HTTP server with a health endpoint, so the same artifacts run locally and
on Cloud Run with `--port $PORT`. `docker build . && docker run -p 8080:8080 <image>` produces a
container whose dashboard is already populated.

## Design & Prove: generate a board, then verify the file

```
boardproof design   --config boardproof.json --outline 44x48mm --route --output board.kicad_pcb
boardproof pcb-check --board board.kicad_pcb --config boardproof.json --require-routing
```

`design` refuses to run while the schematic still has critical violations, so a bad
circuit never becomes a board file. `pcb-check` then **re-reads the file from disk** and
proves, independently of the generator:

- pad-to-net assignment matches the verified netlist (the classic symbol-vs-pad trap)
- every netlist component has exactly one footprint
- every multi-pad net is joined by real copper
- copper clearance, board-outline containment, decoupling distance
- KiCad DRC, when `kicad-cli` is installed

```
DESIGN: 5 footprints, 14 pads on a 44x48 mm board -> board.kicad_pcb
PCB CHECK PASSED: 5 footprints, 14 pads, 5/5 nets fully connected, 37 tracks, 28 vias
  KiCad DRC: 5 violation(s), 0 unconnected, 0 parity
```

Honest scope, stated in the artifact itself: land patterns are **approximate** (replace
with fab-approved footprints), and routing is only attempted with `--route`. Without it
you get a verified placement and pad mapping — reported as notices, not as a pass.

## One command for the whole journey

```sh
boardproof prove --config boardproof.json --outline 44x48mm --revision "Rev A"
```
```
BOARDPROOF PROVE
  [PASS ] check            0 error(s)
  [DONE ] design           5 footprints, 14 pads
  [PASS ] pcb-check        5/5 nets connected, 0 error(s)
  [PASS ] red-team         8/8 targeted faults caught
  [PASS ] layout-red-team  5/5 layout faults caught
  [CLEAR] passport         0 critical, 5 unverified
```

A broken circuit stops at step two (`design` refuses), so the pipeline cannot produce a
manufacturing artifact from a board that failed review:

```
  [FAIL ] check     5 error(s)
  [STOP ] design    critical schematic violations must be fixed before a board is generated
  [BLOCK] passport  5 critical, 5 unverified
```

## Datasheet-driven layout verification

The strongest link in the chain: the layout is checked against the part's own drawing.

```sh
boardproof datasheet --part TMP102AIDRLR              # fetch, hash, register the PDF
boardproof package   infer --pdf datasheets/tmp102aidrlr.pdf --part TMP102AIDRLR \
                     --out packs/packages/tmp102.propose.json --engine gemini
boardproof package   vet   --proposal packs/packages/tmp102.propose.json --reviewer "Your Name"
```

`infer` reads the mechanical drawing and returns pin count, pad pitch, body size and lead
width **with the page and the quoted dimension string**. `vet` is the human gate, exactly
as for rule packs. The board config then references the spec:

```json
{ "packages": ["packs/packages/tmp102.json"],
  "net_currents": { "3V3": 0.05 },
  "copper_oz": 1.0 }
```

This closed two entries in the passport's "not verified" list:

```
+ land pattern vs datasheet SOT-5X3 (DRL) (p.30)
+ track current capacity (IPC-2221, 1 oz copper)
```

And it immediately caught a real error in our own library:

```
[ERROR] LAND_PATTERN_MISMATCH: U1 (SOT563-6): library pitch 0.65 mm vs datasheet 0.5 mm
        (SOT-5X3 (DRL) drawing, p.30)
```

The library had been guessed at 0.65 mm; TI's DRL0006A drawing says `4X 0.5`. Correcting it
then exposed a second, deeper issue — a 0.6 mm via cannot fan out from a 0.5 mm-pitch row,
so the router now **refuses to emit copper** rather than ship a short, and the pipeline falls
back to a verified placement board that says so.

## Verified input and limitations

- **Implemented:** EasyEDA **Pro** `.enet` JSON, whose `components.*.pinInfoMap` contains pin numbers, names, and nets. [Official specification](https://github.com/easyeda/easyeda-netlist-format/blob/main/easyeda-pro-netlist-format-en.md).
- **Not implemented:** EasyEDA **Standard** `shape`-compressed JSON; Pro `.zip` project files; Allegro and PADS exports; PCB DRC; schematic ERC; electrical simulation; arbitrary C/C++ firmware analysis.
- **Offline checks:** require explicit, engineering-reviewed JSON rules. A failing critical rule produces exit code **1**. A missing or malformed input produces exit code **2**, never a false passing check. Unverifiable explicitly configured checks produce errors by default; you can downgrade an individual rule with `"severity": "warning"`.
- **AI (optional):** Gemini extracts *candidate* datasheet pin information from a PDF, with cited text/page and uncertainty. Output is **NOT** imported automatically as blocking rules. Human review is mandatory.

## Quick start

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v

# Clean board; exits 0
boardproof check --config examples/demo/boardproof.clean.json --html artifacts/clean.html --json artifacts/clean.json

# Same board with a *vetted, cited* rule pack loaded (see "The trust chain")
boardproof check --config examples/demo/boardproof.pack.clean.json --html artifacts/pack-clean.html

# Deliberately broken board, with grounded explanations; exits 1
boardproof check --config examples/demo/boardproof.pack.json --explain --engine offline \
  --html artifacts/broken.html --json artifacts/broken.json
```

Open `artifacts/broken.html` in a browser. Every finding carries the datasheet page, the quoted text, the pack id and the human who vetted it. GitHub Actions CI is included at `.github/workflows/boardproof.yml`. It runs on pushes and pull requests and uploads artifacts.

## What the broken demo catches

| Rule | Demo issue | Proof source |
| --- | --- | --- |
| `pin_net` | U1 VDD accidentally connected to `5V` rather than `3V3` | `.enet` connection and reviewed expected net |
| `max_voltage` | 5.0 V assigned to a simulated 3.6 V maximum VDD input | Explicit `net_voltages` and reviewed limit |
| `connected` | Sensor ground pin left disconnected | `.enet` |
| `resistor_between` | SDA pull-up resistor missing | `.enet` + reviewed I2C requirement |
| `firmware_gpio` | LED connects to GPIO4, firmware defines `LED_PIN=5` | `.enet` pin name + simple numeric C `#define` |

**Notably:** A voltage is not inferred from a net's name alone. It must be declared in `net_voltages`. Ranges are **not** derived from the model by default. Every asserted limit should be verified against an authoritative datasheet for the correct part number, package, and conditions.

## Exporting from EasyEDA Pro

1. Open the schematic/project in **EasyEDA Pro**.
2. Use **File → Export → Export Netlist**.
3. Select **EasyEDA Pro `.enet`** and export the whole project if appropriate.
4. Commit the export and your `boardproof.json` to the repo.
5. Re-export whenever the schematic changes. CI cannot detect stale exports unless you enforce that workflow separately.

For Standard Edition, the current MVP requires a converter from its compressed schematic shape format. Do not rename a Standard `.json` to `.enet`; the tool will reject it. [EasyEDA Pro export documentation](https://prodocs.easyeda.com/en/schematic/export-netlist/).

## Add checks for your board

Create `boardproof.json` next to the export:

```json
{
  "schema_version": 1,
  "netlist": "board.enet",
  "firmware": "firmware/pins.h",
  "net_voltages": {"3V3": 3.3, "5V": 5.0, "GND": 0.0},
  "rules": [
    {"id": "mcu-vdd", "type": "pin_net", "component": "U1", "pin": "1", "net": "3V3"},
    {"id": "mcu-vdd-limit", "type": "max_voltage", "component": "U1", "pin": "1", "min_v": 2.7, "max_v": 3.6},
    {"id": "mcu-ground", "type": "connected", "component": "U1", "pin": "2"},
    {"id": "i2c-sda-pullup", "type": "resistor_between", "net_a": "I2C_SDA", "net_b": "3V3", "min_ohms": 1000, "max_ohms": 10000},
    {"id": "firmware-led-pin", "type": "firmware_gpio", "define": "LED_PIN", "component": "U1", "net": "LED_STATUS"}
  ]
}
```

All relative paths are resolved against the config file. `firmware_gpio` compares a simple numerical `#define` with the MCU pin's name (default `GPIO(\\d+)` or `IO(\\d+)`, or customize `pin_label_regex`). It is **not** a real compiler, does not follow `#include`, and does not understand alternate pin multiplexing or module pin numbering unless explicitly modeled.

## Optional Gemini datasheet proposals

```sh
pip install -e '.[ai]'
export GEMINI_API_KEY='your-key'    # never commit this secret
boardproof infer --pdf datasheets/part.pdf --component U1 --out packs/U1.propose.json
boardproof vet --proposal packs/U1.propose.json --reviewer "Your Name"   # after you check the pages
```

Review cited text, printed page numbers, exact package variant, and operating versus absolute-maximum ratings manually. **Do not import proposals directly into a blocking CI ruleset without verifying them.** This optional API integration was written against the Google Gen AI SDK but has **not** been live-tested with an API key in this environment.

## Demo for judges: 90 seconds

1. Open the green `artifacts/clean.html` report.
2. Switch to `artifacts/broken.html`: five precise cross-layer failures, not generic AI advice.
3. Show `firmware_good.h` → `firmware_broken.h`, where `LED_PIN` changed from 4 to 5; GitHub Actions blocks the PR.
4. Explain that Gemini can convert datasheets into *reviewable candidate rules*. Deterministic checks, not AI opinions, decide whether CI fails.

## Architecture

```
EasyEDA Pro .enet ───┐
                    ├──> Normalized components/pin/net graph
Firmware C defines ─┤                 │
Reviewed rule JSON ──┘                 ▼
                            Deterministic verification
                                       │
               JSON results + HTML report + GitHub annotations

PDF datasheet ──> Gemini proposal (optional) ──> human review ──> rule JSON
```

## Safety and roadmap

A green BoardProof check only means **the configured rules passed**. It is not a claim of electrical correctness, EMC compliance, or readiness to manufacture. Continue to run native EasyEDA ERC/DRC, component review, appropriate simulation and hardware validation.

**Next technical milestones:** real EasyEDA Pro sample fixture compatibility; Standard Edition adapter; board-specific firmware parsers; electrical rules for shared-net drivers and power domains; bill-of-materials consistency; PR commenting; measured detection rates on deliberately fault-injected real boards.

License: MIT. See `LICENSE`.
