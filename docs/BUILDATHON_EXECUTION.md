# BoardProof — buildathon execution plan

## One-sentence startup thesis
A pull-request quality gate for hardware teams that checks whether schematic connections, datasheet requirements, and firmware pin definitions agree before a board is fabricated.

## Competitive edge to seek
- Evidence-linked review: every finding identifies *both* the source artifact and the explicit engineering rule used.
- Cross-artifact verification, not a generic screenshot-reading chatbot.
- Conservative unknown handling: important checks fail rather than claiming proof when the underlying data is missing.
- **Unproven differentiation:** faster first-project onboarding, lower false-positive rate, and a growing catalog of reviewed part rules; test these hypotheses with real engineers.

## 20–21 November sprint

### Day 1
- Test exporter against an actual EasyEDA Pro `.enet` export from a permissioned real design.
- Map at least one MCU and one peripheral using verified manufacturer datasheet PDF(s).
- Run optional Gemini extraction and have an engineer approve explicit rules.
- Add a visual diff that shows the affected net and pin, plus the source PDF passage.

### Day 2
- Make two realistic deliberate mistakes (e.g., firmware GPIO mismatch and power-domain limit violation).
- Run on a real PR in GitHub Actions and record the red-to-green remediation.
- Interview three engineering teams/individual developers; write down evidence of actual willingness to use it.
- Present one verified, reproducible 90-second demo; avoid new feature requests.

## Acceptance criteria
- 100% of agreed demo faults caught in the fault-injection fixture.
- No uncaught exceptions on missing input; unsupported EasyEDA formats fail explicitly.
- Exact source pin, net, expected rule, and observed value displayed on every error.
- At least one engineer validates the rule against the relevant datasheet.
- CI produces a nonzero exit code for a critical rule violation.

## What must NOT be claimed
- That a passing check certifies electrical or manufacturing correctness.
- That EasyEDA Standard is natively supported in this version.
- That PDF extraction has been live-tested with Gemini without an API key.
- That synthetic demo detection rates are real-world precision or recall.
- That PCB layout DRC or analog simulation has been done.

## Next meaningful integrations after buildathon
1. EasyEDA Std JSON adapter and live EasyEDA Pro extension for one-click export.
2. Source-linked Gemini rule review UI with package-variant confirmation.
3. CMake / PlatformIO / ESP-IDF-aware firmware pin mapping extraction.
4. Validated rules for power domains, decoupling, strap pins, GPIO max-voltage, I2C/SPI bus compatibility.
5. Failure-dataset benchmark: injected faults across 10 reviewed boards.
6. Hosted PR report and GitHub Marketplace app only after useful local adoption.
