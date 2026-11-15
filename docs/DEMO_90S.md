# The 90-second demo (rehearsed timings)

The whole pitch is one idea: **an AI proposes, a human vets, a machine enforces.**
Never show a model grading a board. Show a model doing the boring expert reading,
and show a deterministic engine that will not be talked out of a verdict.

Hardware: one laptop, one terminal, one browser tab already open on
`examples/demo/broken.enet` next to the datasheet PDF.

## 0:00 — The stakes (10s, no screen)
> "A respin is ₹2 lakh and three weeks. The bug is almost never in the schematic —
> it's between the schematic, the datasheet, and the firmware. CI checks the code.
> Nothing checks the board."

## 0:10 — Green (10s)
```sh
boardproof check --config examples/demo/boardproof.pack.clean.json --html artifacts/pack-clean.html
```
> "Six components, six nets, vetted constraints, zero errors. This is a pull request
> that a hardware team would merge."

## 0:20 — The AI does the reading (25s) ← the part everyone else skips
```sh
boardproof infer --pdf examples/demo/demo-mcu-SIMULATED.pdf --component U1 \
  --netlist examples/demo/broken.enet --out packs/u1.propose.json
```
Say while it runs:
> "Gemini reads the datasheet, and I mean *reads*: page citations, quoted text,
> separate tables for absolute-maximum and recommended-operating. It proposes
> two constraints. It also refuses to convert the 4.2 V absolute maximum into an
> operating limit — that's my rule, not its suggestion."

Point at the output: **`Status: PROPOSED (untrusted)`**.

## 0:45 — The gate (15s)
```sh
boardproof check --config examples/demo/boardproof.pack.json   # ← points at the proposal
```
> "CI refuses to run. BoardProof will not enforce a number a model produced.
> Exit code 2, not a green check."

```sh
boardproof vet --proposal packs/u1.propose.json --reviewer "Bhuvi"
```
> "One human name. That's the audit record. Now it can enter CI."

## 1:00 — Red, with receipts (25s)
```sh
boardproof check --config examples/demo/boardproof.pack.json --explain \
  --html artifacts/pack.html --json artifacts/pack.json
```
Open `artifacts/pack.html`. Point at one finding:
- `ERROR MAX_VOLTAGE` — U1.1 on 5 V, allowed 2.7–3.6 V
- citation block — *p.6, Table 6: "Recommended operating conditions: VDD 2.7 V to 3.6 V"*
- explanation block — **why** and **the exact fix**

> "Five failures, each one traced to a page and a reviewer. And notice the label on
> the explanation: it cannot change the verdict. The model writes prose; the engine
> writes the pass/fail."

## 1:30 — Close (15s)
> "Two numbers: our tests catch a wrong verdict 25 out of 25 times, and the model
> has never once been able to introduce a rule we didn't review. The moat isn't the
> model — it's the vetted pack library: 10,000 datasheets turned into constraints
> that CI can trust."

## Encore, if a judge challenges you (30s)

```sh
boardproof redteam --config examples/demo/boardproof.pack.clean.json
```
> "Every rule just got mutated on purpose: supply swapped to 5 V, ground floated, pull-up
> deleted, value drifted 100x, firmware pin shifted. Eight out of eight caught. And here is
> the one place my rules are blind — the tool tells me, and tells me which rule closes it.
> A checker that says 'no errors' tells you nothing about whether it would have noticed."

Then the revision gate, which is the actual PR story:

```sh
boardproof check --config examples/demo/boardproof.pack.clean.json --json /tmp/base.json
boardproof check --config examples/demo/boardproof.pack.json       --json /tmp/head.json
boardproof diff --base /tmp/base.json --head /tmp/head.json
```
> "Five new violations, zero pre-existing. That is what we block — the regression, not the backlog."

## The artifacts you leave behind

| Artifact | When to show it |
| --- | --- |
| `artifacts/broken.html` | the failing PR: findings + citations + explanations |
| `artifacts/passport.html` | the manufacturing document: blocked stamp, 5 critical, 5 unverified |
| `artifacts/index.html` | the dashboard: one screen, every artifact, the 5-step flow |
| `artifacts/redteam.json` | 8/8 targeted faults caught, 1 blind spot named |

```sh
boardproof passport --config examples/demo/boardproof.pack.json --revision "Rev B" \
  --redteam artifacts/redteam.json --out artifacts/passport.html --engine offline
boardproof dashboard --dir artifacts && open artifacts/index.html
```

Hand a judge the passport, not the terminal. It is the only artifact that says out loud
what the tool did **not** check.

## Design & Prove (60s, if they ask "so can it design?")

```sh
boardproof design --config examples/tmp102/boardproof.5v.json --output /tmp/x.kicad_pcb
# DESIGN REFUSED: the schematic still has 1 critical violation(s)
boardproof design --config examples/tmp102/boardproof.json --outline 44x48mm --route \
  --output artifacts/tmp102.kicad_pcb
boardproof pcb-check --board artifacts/tmp102.kicad_pcb \
  --config examples/tmp102/boardproof.json --require-routing
```
> "A bad circuit never becomes a board file. And when it does generate one, we re-read the
> file from disk and check it against the schematic. Our first generated board failed its
> own DRC with 26 violations — we fixed the router. That refusal is the feature."

## Failure drills (know these cold)
| If | Say | Do |
|---|---|---|
| No network / no API key | "Let me show you the deterministic path, it's the one CI uses." | add `--engine offline --fixture examples/demo/fixtures/demo-mcu.facts.json` |
| Gemini returns garbage | "It's proposing, not deciding — watch the gate reject it." | let it write; `check` still exits 2 |
| A judge asks "what if the model is wrong?" | "Then a human vetted a bad rule, and the report names them. That's the accountability chain — better than a confidence score." | show `reviewed_by` in the HTML |
| A judge asks "why not just a nicer prompt?" | "Because prompts are not a CI gate. Exit codes are." | `echo $?` |

## Numbers to have ready
- 25 tests, all passing, including 4 that assert the AI *cannot* affect a verdict.
- 5 independent failure classes caught on the broken board (pin/net, voltage, connectivity, pull-up, firmware).
- exit 0 pass / 1 findings / 2 cannot-verify. A tool that cannot verify never reports green.
