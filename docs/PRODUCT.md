# BoardProof Product Brief · Buildathon MVP

## Claim
BoardProof reviews the *connections between design representations*, not just a schematic in isolation. It checks that a real netlist aligns with explicitly reviewed component limits and simple firmware mappings, and makes risky changes visible during code review.

## User and pain
Early-stage hardware teams using EasyEDA often maintain schematics, firmware GPIO constants, and manufacturer datasheets in different places. Reviewing inconsistencies before manufacturing requires manual cross-checking and can lead to costly prototype respins.

## Ideal first customer
1–5-person board development teams shipping multiple PCB revisions. Begin with teams already using GitHub and EasyEDA Pro. The buyer is the electronics team lead, not the consumer.

## Three key workflows
1. Engineering change: schematic update -> re-export .enet -> PR hardware CI.
2. Firmware pin remap -> commit -> CI verifies signal's actual MCU pin label.
3. New part: datasheet PDF -> Gemini candidate facts -> engineer approves explicit voltage/net rules.

## Must-show demo
Start with green check, introduce a wrong MCU GPIO mapping and wrong power net, get failed check, show exact expected vs observed hardware state, correct and return to green.

## Honest competitive positioning
Unlike generic design review descriptions, BoardProof's v0.1 uses real exported net connectivity, deterministic constraints, and firmware source. It is NOT yet a comprehensive EDA verification platform, it does NOT replace existing ERC/DRC, and manual rule authoring creates onboarding cost.

## Measurements for validation
- Detection rate on 20 injected error cases in a real EasyEDA board
- False-positive count on a known-good, manually reviewed board
- Time to set up first board and review constraints
- Repeated PR use by >=3 external hardware developers

## Judge questions
- Why doesn't ERC/DRC catch this? Because these are cross-artifact constraints (e.g. firmware pin mapping and datasheet limits) rather than solely electrical connectivity checks.
- Why Google AI? Reading a 400-page datasheet and emitting *cited* candidate constraints is the expensive expert step. Gemini does that pass; the citation gate and the reviewer make the output usable in CI. The model is the labour, not the authority.
- Is this a startup? Potentially paid CI/review features and verified device-rule packs; customer demand and pricing need testing.
- What is proven? The parser/check engine, the propose→vet→enforce trust chain, and a live demo of all three. The Gemini path is implemented against structured output with citation redaction and is exercised by the offline engine in tests; a live keyed call with a real datasheet is the next validation step, not a claim we make.
- What is NOT claimed? That an AI can sign off a board. The enforcement layer is deterministic and the model cannot alter a verdict - there is a test asserting exactly that.

## The one-sentence pitch (use this verbatim)

> Hardware CI that reads your datasheet, but will not enforce a number a model produced:
> Gemini proposes cited constraints, a human vets them, a deterministic engine fails the PR.
