"""Bring your own board: upload a netlist, layout, schematic, photo, or a brief.

No shell, no network unless a datasheet is genuinely needed, and nothing that is
generated here can block a build until a human promotes it.
"""
from __future__ import annotations

import re
from pathlib import Path

import boardproof.datasheets as datasheets
from .checks import run_checks
from .init import write_draft
from .model import Component, Design, Pin
from .netlist import NetlistError, load_enet
from .providers import ProviderError, get_provider

MAX_BYTES = 8 * 1024 * 1024
UPLOAD_DIR = "uploads"
PART_KEYS = ("Manufacturer Part", "DeviceName", "Value")
SUFFIXES = (
    ".enet", ".json", ".kicad_pcb", ".kicad_sch", ".txt", ".md",
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
)
MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif",
    ".kicad_sch": "text/plain", ".txt": "text/plain", ".md": "text/plain",
}


class UploadError(ValueError):
    pass


def _safe_name(name: str) -> str:
    base = Path(str(name or "board.enet")).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip(".-")
    lower = cleaned.lower()
    if not any(lower.endswith(suffix) for suffix in SUFFIXES):
        cleaned += ".enet"
    return cleaned or "board.enet"


def _part_of(component) -> str:
    for key in PART_KEYS:
        value = str(component.attributes.get(key) or "").strip()
        if value and value.upper() not in {"SIM_ONLY", "SYNTH", "DEMO-GENERIC"}:
            return value
    return ""


def _classify(filename: str, kind: str, content: bytes, brief: str) -> str:
    requested = (kind or "").strip().lower()
    if requested in {"photo", "brief", "pcb", "schematic", "enet"}:
        return requested
    lower = filename.lower()
    if lower.endswith(".kicad_pcb"):
        return "pcb"
    if lower.endswith((".kicad_sch", ".sch")):
        return "schematic"
    if lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "photo"
    if lower.endswith((".txt", ".md")):
        return "brief"
    if brief and not (content or b"").strip():
        return "brief"
    return "enet"


def _downloads(stem: str, gerbers: dict) -> list[dict]:
    items = [
        {"label": "KiCad board", "file": f"{stem}.kicad_pcb"},
        {"label": "2D view", "file": f"{stem}.svg"},
        {"label": "3D view", "file": f"{stem}-3d.svg"},
    ]
    if gerbers.get("archive"):
        items.append({"label": "Gerbers (zip)", "file": gerbers["archive"]})
    return items


def _layout_from_pcb(out_dir: Path, filename: str, content: bytes, note: str = "") -> dict:
    from .gerber import export as export_gerbers
    from .pcb import read_kicad
    from .pcbview import write_previews

    text = content.decode("utf-8", errors="replace")
    if "(kicad_pcb" not in text:
        raise UploadError("not a KiCad PCB file")
    board = read_kicad(text)
    stem = Path(_safe_name(filename)).stem or "board"
    board_path = out_dir / f"{stem}.kicad_pcb"
    board_path.write_text(text, encoding="utf-8")
    write_previews(board, out_dir / f"{stem}.svg")
    gerbers = export_gerbers(board_path, out_dir)
    log = [
        f"layout {stem}.kicad_pcb — {len(board.footprints)} footprints, "
        f"{board.width:g}×{board.height:g} mm",
        "2D and 3D renders written",
        f"Gerbers: {gerbers.get('archive') or gerbers.get('note') or gerbers.get('error')}",
    ]
    if note:
        log.insert(0, note)
    return {
        "ok": True,
        "kind": "pcb",
        "board": board_path.name,
        "components": len(board.footprints),
        "nets": len(board.nets()),
        "pins": len(board.pads()),
        "parts": [],
        "downloads": _downloads(stem, gerbers),
        "gerbers": gerbers,
        "log": log,
        "next": [
            f"open {board_path.name}",
            "download the Gerber zip for fabrication",
        ],
    }


def design_from_proposal(data: dict, source: str) -> Design:
    components: dict[str, Component] = {}
    nets: dict[str, list[tuple[str, str]]] = {}
    connectors = 0
    for raw in data.get("components") or []:
        ref = str(raw.get("ref") or "").strip()
        if not ref or ref in components:
            continue
        if ref[:1].upper() == "J":
            connectors += 1
            if connectors > 4:
                continue
        pins: dict[str, Pin] = {}
        for item in raw.get("pins") or []:
            number = str(item.get("number") or "").strip()
            if not number or number in pins:
                continue
            net = str(item.get("net") or "").strip()
            pins[number] = Pin(number, str(item.get("name") or ""), net)
            if net:
                nets.setdefault(net, []).append((ref, number))
        if not pins:
            continue
        components[ref] = Component(
            ref, str(raw.get("value") or ""), str(raw.get("part") or ""), pins,
            {"FootprintName": str(raw.get("footprint") or ""),
             "Value": str(raw.get("value") or ""),
             "Manufacturer Part": str(raw.get("part") or "")},
        )
    if not components:
        raise UploadError("the model returned zero components")
    return Design(components, nets, source)


def _emit_from_design(out_dir: Path, design: Design, stem: str, log: list[str]) -> dict:
    from .design import build_board, write_board
    from .gerber import export as export_gerbers

    count = max(1, len(design.components))
    last_error: Exception | None = None
    board = report = None
    for width in (None, max(80.0, 16.0 * count), max(120.0, 22.0 * count)):
        for route in (True, False):
            try:
                board, report = build_board(design, width, width, title=stem, route=route)
                last_error = None
                break
            except ValueError as exc:
                last_error = exc
        if board is not None:
            break
    if last_error is not None or board is None or report is None:
        raise last_error or ValueError("could not place the proposed board")
    board_path = out_dir / f"{stem}.kicad_pcb"
    write_board(board, board_path, out_dir / f"{stem}.svg")
    gerbers = export_gerbers(board_path, out_dir)
    routed = (report.get("routing") or {}).get("attempted")
    log.append(
        f"board generated: {report['board']['width_mm']}×{report['board']['height_mm']} mm, "
        f"{report['board']['footprints']} footprints"
        + ("; copper routed" if routed else "; placement only (router refused a short)")
    )
    log.append("2D and 3D renders written")
    log.append(f"Gerbers: {gerbers.get('archive') or gerbers.get('note') or gerbers.get('error')}")
    return {
        "ok": True,
        "kind": "proposed",
        "board": board_path.name,
        "components": len(design.components),
        "nets": len(design.nets),
        "pins": sum(len(c.pins) for c in design.components.values()),
        "parts": [{"part": c.part or c.value, "refs": [c.ref], "document": "",
                   "status": "proposed"} for c in design.components.values()],
        "downloads": _downloads(stem, gerbers),
        "gerbers": gerbers,
        "log": log,
        "next": [
            f"open {board_path.name}",
            "download the Gerber zip for fabrication",
            "land patterns are approximate until a human vets the pack",
        ],
    }


def _from_intent(root: Path, out_dir: Path, filename: str, brief: str, kind: str,
                 content: bytes = b"", engine: str = "auto") -> dict:
    target = root / UPLOAD_DIR / "intent.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    body = brief.strip() or f"uploaded {filename} ({kind})"
    if target.exists():
        target.write_text(target.read_text(encoding="utf-8") + "\n---\n" + body + "\n",
                          encoding="utf-8")
    else:
        target.write_text(body + "\n", encoding="utf-8")
    mime = MIME.get(Path(filename).suffix.lower(), "application/octet-stream")
    attachments = [(content, mime, filename)] if content else []
    try:
        provider = get_provider(engine)
        proposal = provider.propose_circuit(brief or body, attachments)
    except ProviderError as exc:
        raise UploadError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface model failures in the studio
        raise UploadError(f"circuit proposal failed: {type(exc).__name__}: {exc}") from exc

    design = design_from_proposal(proposal, f"{kind}:{filename}")
    stem = Path(filename).stem or "proposed"
    log = [
        f"{provider.name} proposed {len(design.components)} component(s), "
        f"{len(design.nets)} net(s)",
        str(proposal.get("summary") or proposal.get("title") or ""),
    ]
    try:
        return _emit_from_design(out_dir, design, stem, log)
    except Exception as exc:  # noqa: BLE001 - placement/export errors
        raise UploadError(f"layout failed: {type(exc).__name__}: {exc}") from exc


def _build_from_upload(root: Path, out_dir: Path, upload: dict) -> dict:
    """After an upload: generate the board, render both views, export Gerbers."""
    from .cli_support import load_reviewed
    from .design import build_board, write_board
    from .pcbcheck import check_board
    from .gerber import export as export_gerbers

    log: list[str] = []
    config = root / upload["config"]
    try:
        spec, _raw, design = load_reviewed(config, True)
        findings = run_checks(design, spec, config)
        blocking = [f for f in findings if f.severity == "error"]
        if blocking:
            return {"board": None, "downloads": [],
                    "log": log + [f"board not generated: {len(blocking)} blocking finding(s); "
                                  "this upload is a draft with warning-severity rules only"]}
        board, report = build_board(design, None, None,
                                    title=Path(upload["netlist"]).stem, route=False)
        stem = Path(upload["netlist"]).stem
        board_path = out_dir / f"{stem}.kicad_pcb"
        write_board(board, board_path, out_dir / f"{stem}.svg")
        pcb = check_board(board_path, design, packages=[], net_currents={})
        gerbers = export_gerbers(board_path, out_dir)
        log.append(f"board generated: {report['board']['width_mm']}×"
                   f"{report['board']['height_mm']} mm, {report['board']['footprints']} footprints")
        log.append("2D and 3D renders written")
        log.append(f"Gerbers: {gerbers.get('archive') or gerbers.get('note') or gerbers.get('error')}")
        downloads = _downloads(stem, gerbers)
        return {"board": board_path.name, "downloads": downloads, "log": log,
                "pcb_status": pcb["status"], "gerbers": gerbers}
    except Exception as exc:  # noqa: BLE001 - surfaced in the browser
        return {"board": None, "downloads": [],
                "log": log + [f"board generation failed: {type(exc).__name__}: {exc}"]}


def _emit_from_netlist(root: Path, out_dir: Path, result: dict) -> dict:
    built = _build_from_upload(root, out_dir, result)
    result["board"] = built.get("board")
    result["downloads"] = built.get("downloads") or []
    result["gerbers"] = built.get("gerbers")
    result["log"] = list(result.get("log") or []) + list(built.get("log") or [])
    if built.get("board"):
        result["next"] = [
            f"open {built['board']}",
            "download the Gerber zip for fabrication",
        ] + list(result.get("next") or [])
    return result


def onboard(root: Path, out_dir: Path, filename: str, content: bytes,
            brief: str = "", kind: str = "", engine: str = "auto",
            fetch_datasheets: bool = True) -> dict:
    root, out_dir = Path(root), Path(out_dir)
    if len(content) > MAX_BYTES:
        raise UploadError(f"file is larger than {MAX_BYTES // (1024 * 1024)} MB")
    safe = _safe_name(filename)
    route = _classify(safe, kind, content, brief)
    out_dir.mkdir(parents=True, exist_ok=True)

    if route in {"photo", "brief"}:
        if not (content or b"").strip() and not (brief or "").strip():
            raise UploadError("the uploaded file is empty")
        return _from_intent(root, out_dir, safe, brief, route, content, engine)

    if route == "schematic":
        target = root / UPLOAD_DIR / safe
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        extra = _from_intent(root, out_dir, safe, brief, "schematic", content, engine)
        extra["log"] = [f"stored schematic {target.relative_to(root)}"] + extra["log"]
        extra["netlist"] = str(target.relative_to(root))
        return extra

    if route == "pcb":
        if not (content or b"").strip():
            raise UploadError("the uploaded file is empty")
        return _layout_from_pcb(out_dir, safe, content)

    if not (content or b"").strip():
        raise UploadError("the uploaded file is empty")

    target = root / UPLOAD_DIR / safe
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

    try:
        design = load_enet(target)
    except NetlistError as exc:
        raise UploadError(f"{safe}: {exc}") from exc

    parts: list[dict] = []
    seen: set[str] = set()
    for component in sorted(design.components.values(), key=lambda c: c.ref):
        part = _part_of(component)
        if not part or part in seen:
            continue
        seen.add(part)
        entry = {"part": part, "refs": [], "datasheet": None, "document": "",
                 "status": "", "error": ""}
        if fetch_datasheets:
            try:
                record = datasheets.fetch(part, root / "datasheets")
                entry.update({"datasheet": record.get("url") or record.get("path"),
                              "status": record.get("status", "cached"),
                              "sha256": (record.get("sha256") or "")[:16],
                              "document": record.get("path")})
            except datasheets.DatasheetError as exc:
                entry.update({"status": "not found", "error": str(exc)})
        else:
            entry["status"] = "not requested"
        parts.append(entry)
    for entry in parts:
        entry["refs"] = sorted(c.ref for c in design.components.values()
                               if _part_of(c) == entry["part"])

    config_path = target.with_suffix(".boardproof.json")
    config, notes = write_draft(design, target, config_path)
    findings = run_checks(design, config, config_path)
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    result = {
        "ok": True,
        "kind": "enet",
        "netlist": str(target.relative_to(root)),
        "config": str(config_path.relative_to(root)),
        "components": len(design.components),
        "nets": len(design.nets),
        "pins": sum(len(c.pins) for c in design.components.values()),
        "parts": parts,
        "draft_rules": len(config["rules"]),
        "blocking": len(errors),
        "warnings": len(warnings),
        "notes": notes[:8],
        "findings": [{"code": f.code, "message": f.message} for f in findings[:8]],
        "downloads": [],
        "next": [
            f"review {config_path.relative_to(root)} (every rule is severity=warning)",
            f"boardproof datasheet --part <the part you care about>   # if a datasheet was not found",
            f"boardproof prove --config {config_path.relative_to(root)}",
        ],
        "log": [
            f"parsed {len(design.components)} components, {len(design.nets)} nets",
            f"pulled {sum(1 for p in parts if p['document'])} of {len(parts)} datasheet(s)",
            f"drafted {len(config['rules'])} rule(s) at severity=warning (cannot block a build)",
            f"check: {len(errors)} error(s), {len(warnings)} warning(s)",
        ],
    }
    return _emit_from_netlist(root, out_dir, result)
