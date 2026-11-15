# Architecture: the trust chain

```
datasheet.pdf ──► [AI extract] ──► *propose.json   status=proposed, untrusted
                                         │
                              [human review gate]  ← the only step that can promote
                                         ▼
                                   pack.json       status=vetted, reviewed_by=<name>
                                         │
board.enet + firmware.h ──► [deterministic engine] ──► findings + provenance
                                         │
                              [AI explain] (read-only, cannot alter verdict)
                                         ▼
                                   report.html / report.json
```

## The three invariants (enforced in code, not in a prompt)

1. **A numeric limit cannot enter CI without a citation.**
   `packs.validate_pack` rejects any rule with `max_v`/`min_v`/`min_ohms`/`max_ohms`
   whose `citation` lacks a page or an exact quote. There is no override flag.

2. **An unreviewed proposal cannot be enforced.**
   `packs.load_pack(require_vetted=True)` raises, so `check` exits **2** (cannot
   verify) rather than **0** (clean). A missing reviewer name is the same class of
   failure as a missing netlist.

3. **The model cannot widen the evidence base.**
   `providers.redact_explanations` discards any explanation whose `rule_index` is not
   a real finding, and any `cited_page` that BoardProof did not itself hand to the
   model. Citations are inputs to the model, never outputs from it.

## Why the verdict is deterministic
`checks.run_checks` is pure: same netlist + same config → same findings, no network,
no sampling, no temperature. `--explain` is a *second, optional pass over results that
already exist*. Deleting the AI layer changes the wording and nothing else — there is
a test (`test_explanation_never_changes_the_verdict`) that asserts this.

## Failure modes it names out loud
- `VOLTAGE_UNKNOWN` — a net has no declared voltage, so a rating cannot be confirmed.
- `MISSING_PIN` / `MISSING_COMPONENT` — the rule refers to something absent.
- `FW_UNKNOWN` — macro missing or not a simple numeric `#define`.
- `GPIO_UNKNOWN` — pin name has no GPIO number; no guessed pass.
- `MCU_NET_AMBIGUOUS` — more than one pin on the net; refuse to pick one.

Each is an **error**, never a silent pass. Exit code 2 is reserved for input we could
not read at all, so CI can tell "board is broken" apart from "we could not look".

## Packs are the compounding asset
A pack is `{part, manufacturer, package, source document sha256, reviewer, rules[]}`.
Vetting a new board means diffing a new proposal against an existing pack
(`infer --previous packs/foo.json` writes `*.diff`). That is how a reviewed library of
datasheets compounds into a moat while every individual change stays auditable.

## What is deliberately absent
No PCB DRC, no schematic ERC, no electrical simulation, no arbitrary C++ analysis,
no auto-import of AI rules. Those are either solved by the EDA vendor or unsafe to
automate without a human. The value is the *seam* between artifacts, which nothing
else checks.

## Complexity budget

| Stage | Before | Now |
| --- | --- | --- |
| netlist parse | O(components) | O(components), unchanged (it is the floor) |
| `resistor_between` | O(rules x components) | O(components) once + O(1) per rule |
| pin/voltage/connected | O(1) per rule | O(1) per rule |
| firmware parse | re-read per run | cached on (path, mtime, size) |
| pack validation | re-validated per reference | cached, handed out as a deep copy |

4,000 rules over 20,000 components: **9.12 ms of checking**. The bench is a test, not a
claim - CI fails if the check stage exceeds its budget.

## Red team (mutation testing of the rules)

`redteam.build_faults` derives faults from the rules, applies them to an in-memory `Design`
(frozen dataclasses rebuilt with `replace`, nets re-derived), and re-runs the *same* pure
engine. A targeted fault that does not fire means the rule aimed at it is not working; a
fault with no applicable rule is reported as a gap, not as a pass. Unrepresentable classes
(symbol-to-footprint mapping) are labelled, never counted as caught.

This keeps the honesty property: the score measures rule strength, and it cannot be improved
by deleting the faults it fails.
