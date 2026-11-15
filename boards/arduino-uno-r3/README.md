# Arduino Uno R3 — real source files

Downloaded from the open-source project **rheingoldheavy/arduino_uno_r3_from_scratch**
(82★, "Complete KiCad Arduino UNO R3 Schematic and BOM", based on the official
arduino.cc schematic). These are the publisher's files, not a reconstruction.

| file | what it is |
| --- | --- |
| `ATMEGA328P.sch`, `ATMEGA16U2.sch`, `USB_Interface.sch`, `Voltage_Regulator.sch`, `voltage_management.sch`, `Headers.sch`, `Pin_13_LED.sch` | the eight hierarchy sheets |
| `Arduino_Uno_R3_From_Scratch.sch` | root sheet, title block: "Arduino UNO R3 Clone", Rev 1 |
| `*-cache.lib`, `MFN_Atmel.lib`, `MFN_STMicro.lib` | the legacy symbol libraries the sheets reference |
| `sym-lib-table` | added by BoardProof so KiCad can resolve `MFN_Atmel:` / `MFN_STMicro:` |

## Status: blocked by the legacy format, not by BoardProof

    $ kicad-cli sch export netlist --format kicadsexpr -o uno.net Arduino_Uno_R3_From_Scratch.sch
    $ grep -c '(comp (ref' uno.net
    0

KiCad 9's CLI exports **zero components and zero nets** from a *legacy* (version 4/5) `.sch`
hierarchy — silently, with exit code 0. The sub-sheets do contain the parts
(`$Comp L MFN_Atmel:ATMEGA328P-PU U5`), so the data is there; the CLI's legacy loader just
does not build a netlist from it.

## The 5-minute unblock (no guessing, no invented parts)

1. Open `Arduino_Uno_R3_From_Scratch.sch` in KiCad 9 (GUI).
2. **File → Save As** → `uno.kicad_sch` (converts the whole hierarchy to the modern format).
3. Then:

       kicad-cli sch export netlist --format kicadsexpr -o uno.net uno.kicad_sch
       boardproof import-netlist --netlist uno.net --board "Arduino Uno R3" --out boards/uno

The importer that consumes a KiCad netlist into a BoardProof design is the one piece not yet
written — it is ~120 lines against a documented, simple S-expression format, and it is the
correct next commit rather than fabricating 60 parts from memory.

## Why we did not fake it

An Uno R3 has ~60 parts and ~90 nets. Writing them from memory produces a file that looks
plausible and is electrically wrong — the failure mode this tool exists to catch.
