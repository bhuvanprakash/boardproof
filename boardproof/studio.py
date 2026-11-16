"""The studio: a tiny local/Cloud Run service that *runs* BoardProof on click.

No shell, no arbitrary arguments. Every action below is a fixed function from
this package, called with paths that were discovered inside the workspace.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .checks import run_checks
from .cli_support import analyse, load_reviewed
from .dashboard import collect, render
from .design import build_board, write_board
from .package import load_spec
from .pcb_redteam import run_pcb_redteam
from .pcbcheck import check_board
from .prove import run_prove
from .redteam import run_redteam

ACTION_HELP = {
    "check": "Run the deterministic checks on this config",
    "prove": "Full journey: check → design → pcb-check → red team → passport",
    "design": "Generate the editable KiCad candidate + preview",
    "pcb": "Verify the newest .kicad_pcb against the schematic",
    "gerbers": "Export the selected board's Gerbers and drill files",
    "redteam": "Inject faults and score the rule set",
    "passport": "Rebuild the Manufacturing Preflight Passport",
    "refresh": "Rescan the workspace and rebuild this dashboard",
}

_LOCK = threading.Lock()


def discover_configs(root: Path, limit: int | None = 12) -> list[dict]:
    configs: list[dict] = []
    paths: set[Path] = set()
    for directory, folders, files in os.walk(root):
        folders[:] = [name for name in folders if name not in {".venv", ".next", "node_modules", ".git", "artifacts"}]
        paths.update(Path(directory) / name for name in files
                     if name.endswith(".json") and (name.startswith("boardproof") or name.endswith(".boardproof.json")))
    for path in sorted(paths):
        if any(part in {".venv", "node_modules", ".git", "artifacts"} for part in path.parts):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("schema_version") != 1 or "netlist" not in data:
            continue
        configs.append({
            "path": str(path.relative_to(root)),
            "netlist": data.get("netlist"),
            "rules": len(data.get("rules") or []),
            "packs": len(data.get("packs") or []),
            "packages": len(data.get("packages") or []),
        })
        if limit is not None and len(configs) >= limit:
            break
    configs.sort(key=lambda c: (-c["packages"], -c["packs"], c["path"]))
    return configs


def newest_board(out_dir: Path) -> Path | None:
    boards = sorted(Path(out_dir).glob("*.kicad_pcb"), key=lambda p: p.stat().st_mtime, reverse=True)
    return boards[0] if boards else None


def selected_board(out_dir: Path, name: str | None) -> Path | None:
    if not name or Path(name).name != name or not name.endswith(".kicad_pcb"):
        return None
    path = (out_dir / name).resolve()
    return path if path.parent == out_dir.resolve() and path.name == name and path.is_file() else None


def state(root: Path, out_dir: Path, *, config_limit: int | None = 12) -> dict:
    found = collect(out_dir, include_visuals=False)
    board = newest_board(out_dir)
    return {
        "tool": "BoardProof",
        "configs": discover_configs(root, config_limit),
        "board": str(board) if board else None,
        "artifacts": {
            "reports": [p.name for p, _ in found["reports"]],
            "passport": found["passport"][0].name if found["passport"] else None,
            "red_teams": [p.name for p, _ in found.get("redteams") or []],
            "designs": [p.name for p, _ in found.get("designs") or []],
            "pcb_checks": [p.name for p, _ in found.get("pcb_checks") or []],
            "diffs": [p.name for p, _ in found["diffs"]],
        },
        "actions": ACTION_HELP,
        "modes": {"route": False},
    }


def run_action(root: Path, out_dir: Path, action: str, config: str | None,
               revision: str = "", *, board: str | None = None,
               render_dashboard: bool = True) -> dict:
    if action not in ACTION_HELP:
        return {"ok": False, "code": 2, "log": [f"unknown action {action!r}"]}
    root, out_dir = Path(root), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    if action == "refresh":
        if not render_dashboard:
            return {"ok": True, "code": 0, "log": ["Workspace refreshed"]}
        (out_dir / "index.html").write_text(render(collect(out_dir)), encoding="utf-8")
        return {"ok": True, "code": 0, "seconds": round(time.time() - started, 2),
                "log": ["rescanned workspace", f"dashboard rebuilt at {out_dir / 'index.html'}"]}

    if action == "gerbers":
        from .gerber import export

        board_path = selected_board(out_dir, board)
        if board_path is None:
            return {"ok": False, "code": 2, "log": ["Select a board from the workspace"]}
        with _LOCK:
            exported = export(board_path, out_dir)
        archive = exported.get("archive")
        return {"ok": bool(archive), "code": 0 if archive else 1,
                "log": [f"Wrote {archive}" if archive else exported.get("note") or exported["error"]]}

    if not config:
        return {"ok": False, "code": 2, "log": ["pick a configuration first"]}
    candidate = (root / config).resolve()
    if root.resolve() not in candidate.parents and candidate.parent != root.resolve():
        return {"ok": False, "code": 2, "log": ["configuration is outside the workspace"]}
    if not candidate.is_file():
        return {"ok": False, "code": 2, "log": [f"config not found: {candidate}"]}

    with _LOCK:
        try:
            if action == "check":
                data, findings, code = analyse(candidate, True, "offline", None, None, False)
                from .report import write_reports

                write_reports(data, out_dir / f"{candidate.stem}.json",
                              out_dir / f"{candidate.stem}.html")
                log = [f"{data['status'].upper()}: {data['counts']['error']} error(s), "
                       f"{data['counts']['warning']} warning(s)"]
                log += [f"[{f.severity.upper()}] {f.code}: {f.message}" for f in findings]
                payload = {"ok": code == 0, "code": code}

            elif action == "prove":
                result = run_prove(candidate, out_dir, "44x52mm", False, revision, "offline", True,
                                   dashboard=render_dashboard)
                log = [f"[{s['status'].upper()}] {s['step']}: {s['detail']}" for s in result["steps"]]
                payload = {"ok": result["exit_code"] == 0, "code": result["exit_code"],
                           "board": result["board"]}

            elif action == "design":
                spec, _raw, design = load_reviewed(candidate, False)
                blocking = [f for f in run_checks(design, spec, candidate) if f.severity == "error"]
                if blocking:
                    return {"ok": False, "code": 1,
                            "log": [f"DESIGN REFUSED: {len(blocking)} critical violation(s)",
                                    *[f"[{f.code}] {f.message}" for f in blocking[:5]]],
                            "seconds": round(time.time() - started, 2)}
                board, report = build_board(design, None, None,
                                            title=f"{candidate.stem} candidate", route=False)
                board_path = out_dir / f"{candidate.stem}.kicad_pcb"
                write_board(board, board_path, out_dir / f"{candidate.stem}.svg")
                report.update({"kind": "design", "tool": "BoardProof", "config": str(candidate),
                               "status": "generated", "census": report["board"],
                               "output": str(board_path),
                               "svg": str(out_dir / f"{candidate.stem}.svg")})
                (out_dir / "design.json").write_text(json.dumps(report, indent=2) + "\n",
                                                     encoding="utf-8")
                log = [f"{report['board']['footprints']} footprints, {report['board']['pads']} pads "
                       f"on {report['board']['width_mm']:g}x{report['board']['height_mm']:g} mm",
                       f"routing: {'attempted' if report['routing']['attempted'] else 'not attempted'}",
                       f"wrote {board_path.name} and {board_path.with_suffix('.svg').name}"]
                payload = {"ok": True, "code": 0, "board": board_path.name}

            elif action == "pcb":
                spec, _raw, design = load_reviewed(candidate, False)
                board_path = selected_board(out_dir, board) if board else newest_board(out_dir)
                if board and board_path is None:
                    return {"ok": False, "code": 2, "log": ["Select a board from the workspace"]}
                if board_path is None:
                    return {"ok": False, "code": 2, "log": ["no .kicad_pcb in the artifacts directory"]}
                packages = []
                for reference in spec.get("packages") or []:
                    entry = reference if isinstance(reference, dict) else {"path": reference}
                    packages.append(load_spec((candidate.parent / str(entry["path"])).resolve(),
                                              require_vetted=True))
                result = check_board(board_path, design, packages=packages,
                                     net_currents=spec.get("net_currents") or {},
                                     copper_oz=float(spec.get("copper_oz", 1.0)))
                result.update({"config": str(candidate), "svg": str(board_path.with_suffix(".svg"))})
                (out_dir / "pcb-check.json").write_text(json.dumps(result, indent=2) + "\n",
                                                        encoding="utf-8")
                log = [f"{result['status'].upper()}: {result['counts']['error']} error(s), "
                       f"{result['counts']['warning']} warning(s)",
                       f"{result['nets']['fully_connected']}/{result['nets']['total']} nets connected"]
                log += [f"[{f['severity'].upper()}] {f['code']}: {f['message']}"
                        for f in result["findings"][:8]]
                payload = {"ok": result["counts"]["error"] == 0, "code": 0
                           if result["counts"]["error"] == 0 else 1}

            elif action == "redteam":
                spec, _raw, design = load_reviewed(candidate, False)
                result = run_redteam(design, spec, candidate)
                (out_dir / "redteam.json").write_text(json.dumps(result, indent=2) + "\n",
                                                      encoding="utf-8")
                score = result["score"]
                log = [f"{score['caught']}/{score['targeted']} targeted faults caught, "
                       f"{score['gaps']} blind spot(s)"]
                log += [f"[{f['status'].upper()}] {f['kind']}: {f['summary']}" for f in result["faults"]]
                payload = {"ok": score["gaps"] == 0, "code": 0 if score["gaps"] == 0 else 1}

            elif action == "passport":
                from .passport import build_document

                report, _, _ = analyse(candidate, True, "offline", None, None, False)
                document = build_document(out_dir, revision or candidate.stem,
                                          report=report, config=candidate)
                (out_dir / "passport.html").write_text(document["html"], encoding="utf-8")
                (out_dir / "passport.json").write_text(json.dumps(document["json"], indent=2) + "\n",
                                                       encoding="utf-8")
                counts = document["json"]["counts"]
                log = [f"{document['json']['status'].upper()}: {counts['critical']} critical, "
                       f"{counts['unverified']} unverified",
                       f"hash {document['json']['passport_hash'][:16]}"]
                payload = {"ok": document["json"]["status"] == "cleared", "code": 0}

            else:  # pragma: no cover - guarded above
                return {"ok": False, "code": 2, "log": ["unhandled action"]}

            if render_dashboard:
                (out_dir / "index.html").write_text(render(collect(out_dir)), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - surfaced to the browser, never swallowed
            return {"ok": False, "code": 2,
                    "log": [f"{type(exc).__name__}: {exc}"], "seconds": round(time.time() - started, 2)}

    payload.update({"seconds": round(time.time() - started, 2), "log": log})
    return payload
