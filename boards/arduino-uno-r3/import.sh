#!/bin/sh
# Convert the legacy Uno sheets once, then import the netlist.
set -e
cd "$(dirname "$0")"
echo "1. open Arduino_Uno_R3_From_Scratch.sch in KiCad 9, File > Save As uno.kicad_sch"
echo "2. then:"
echo "   kicad-cli sch export netlist --format kicadsexpr -o uno.net uno.kicad_sch"
echo "   boardproof import-netlist --netlist uno.net --out boards/uno"
