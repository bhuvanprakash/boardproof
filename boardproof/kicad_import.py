"""Import a real KiCad project: schematic netlist → Design, board file → Board.

Used to verify an *existing* layout against its own schematic netlist. No
geometry is invented: the pads come from the `.kicad_pcb`, the expected nets come
from the netlist that KiCad itself exported from the `.kicad_sch`.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .model import Component, Design, Pin
from .pcbcheck import find_kicad_cli

TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+')


def parse_sexpr(text: str) -> list:
    """Minimal, robust s-expression reader: 30 lines beats a pile of regexes."""
    stack: list[list] = [[]]
    for match in TOKEN.finditer(text):
        token = match.group(0)
        if token == "(":
            stack.append([])
        elif token == ")":
            if len(stack) < 2:
                continue
            node = stack.pop()
            stack[-1].append(node)
        else:
            if token.startswith('"'):
                token = token[1:-1].replace('\\"', '"')
            stack[-1].append(token)
    return stack[0]


def _children(node: list, head: str) -> list[list]:
    return [item for item in node if isinstance(item, list) and item and item[0] == head]


def _field(node: list, head: str) -> str:
    for item in node:
        if isinstance(item, list) and item and item[0] == head:
            for value in item[1:]:
                if isinstance(value, str):
                    return value
    return ""


class ImportError_(ValueError):
    pass


def export_netlist(schematic: Path, out: Path | None = None) -> Path:
    """Ask KiCad for the netlist. Refuses when the file is not a modern schematic."""
    schematic = Path(schematic)
    cli = find_kicad_cli()
    if not cli:
        raise ImportError_("kicad-cli not found; cannot export a netlist")
    if schematic.suffix == ".sch":
        raise ImportError_(
            f"{schematic.name} is a legacy v4 schematic; KiCad 9 exports an empty netlist from "
            "it. Open it in KiCad 9, File > Save As .kicad_sch, then retry.")
    target = Path(out) if out else schematic.with_suffix(".net")
    proc = subprocess.run([cli, "sch", "export", "netlist", "--format", "kicadsexpr",
                           "-o", str(target), str(schematic)],
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0 or not target.is_file():
        raise ImportError_((proc.stderr or proc.stdout or "netlist export failed").strip()[:300])
    return target


def design_from_netlist(path: Path) -> Design:
    tree = parse_sexpr(Path(path).read_text(encoding="utf-8", errors="replace"))
    root = tree[0] if len(tree) == 1 and tree and isinstance(tree[0], list) else tree
    components_node = next((node for node in root if isinstance(node, list)
                            and node and node[0] == "components"), None)
    nets_node = next((node for node in root if isinstance(node, list)
                      and node and node[0] == "nets"), None)
    if not components_node:
        raise ImportError_(f"{Path(path).name}: no (components ...) block - is this a KiCad netlist?")

    # every pin of every part, including the ones no net touches, so an unconnected
    # board pad is not mistaken for a schematic mismatch
    library: dict[tuple[str, str], dict[str, str]] = {}
    for libparts in _children(root, "libparts"):
        for libpart in _children(libparts, "libpart"):
            lib = _field(libpart, "lib")
            part = _field(libpart, "part")
            pins_node = next((node for node in libpart if isinstance(node, list)
                              and node and node[0] == "pins"), None)
            table: dict[str, str] = {}
            for pin in _children(pins_node or [], "pin"):
                number = _field(pin, "num")
                if number and number not in table:
                    table[number] = _field(pin, "name") or number
            if table:
                library[(lib, part)] = table

    pins: dict[str, dict[str, Pin]] = {}
    components: dict[str, Component] = {}
    for comp in _children(components_node, "comp"):
        ref = _field(comp, "ref")
        if not ref:
            continue
        value = _field(comp, "value")
        footprint = _field(comp, "footprint")
        libsource = next((node for node in comp if isinstance(node, list)
                          and node and node[0] == "libsource"), None)
        lib = _field(libsource, "lib") if libsource else ""
        part = _field(libsource, "part") if libsource else ""
        table = library.get((lib, part), {})
        components[ref] = Component(ref=ref, value=value, part=footprint, pins={},
                                    attributes={"FootprintName": footprint, "Value": value,
                                                "Manufacturer Part": footprint})
        pins[ref] = {number: Pin(number=number, name=name, net="")
                     for number, name in table.items()}
    if not components:
        raise ImportError_(f"{Path(path).name}: zero components")

    nets: dict[str, list[tuple[str, str]]] = {}
    for net in _children(nets_node or [], "net"):
        name = _field(net, "name")
        for node in _children(net, "node"):
            ref = _field(node, "ref")
            number = _field(node, "pin")
            if ref not in components or not number:
                continue
            clean = "" if (not name or name.startswith("unconnected-")) else name
            pins[ref][number] = Pin(number=number, name=_field(node, "pinfunction") or number,
                                    net=clean)
            if clean:
                nets.setdefault(clean, []).append((ref, number))

    rebuilt = {ref: Component(ref=ref, value=c.value, part=c.part, pins=pins[ref],
                              attributes=c.attributes) for ref, c in components.items()}
    return Design(components=rebuilt, nets=nets, source=str(path))
