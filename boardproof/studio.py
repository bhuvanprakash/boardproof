"""The studio: a tiny local/Cloud Run service that *runs* BoardProof on click.

No shell, no arbitrary arguments. Every action below is a fixed function from
this package, called with paths that were discovered inside the workspace.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
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
    "prove": "Run circuit and placement checks; review routing before release",
    "design": "Generate the editable KiCad candidate + preview",
    "pcb": "Verify the selected board, including copper connectivity",
    "gerbers": "Export the selected board's Gerbers and drill files",
    "redteam": "Inject faults and score the rule set",
    "passport": "Build a revision record from current circuit and board evidence",
    "diff": "Compare two saved hardware-check reports",
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
    configs = discover_configs(root, config_limit)
    rule_packs = []
    workspace_root = Path(root).resolve()
    for config in configs:
        candidate = (workspace_root / config["path"]).resolve()
        if workspace_root not in candidate.parents or not candidate.is_file():
            continue
        try:
            source = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(source, dict):
            continue
        pack = source.get("pack") if isinstance(source.get("pack"), dict) else {}
        rules = source.get("rules") if isinstance(source.get("rules"), list) else []
        rule_packs.append({
            "path": config["path"],
            "netlist": config.get("netlist"),
            "status": pack.get("status") or source.get("status") or "not recorded",
            "rules": [{
                "id": str(rule.get("id") or f"Rule {index + 1}"),
                "type": str(rule.get("type") or "unknown"),
                "severity": str(rule.get("severity", "error")),
                "component": str(rule.get("component") or ""),
                "pin": str(rule.get("pin") or ""),
                "net": str(rule.get("net") or ""),
                "status": str(rule.get("status") or pack.get("status") or "not recorded"),
                "citation": rule.get("citation") if isinstance(rule.get("citation"), dict) else None,
            } for index, rule in enumerate(rules) if isinstance(rule, dict)],
        })
    recent_runs = []
    for path, report in sorted(found["reports"], key=lambda item: item[0].stat().st_mtime_ns, reverse=True)[:50]:
        counts = report.get("counts") if isinstance(report.get("counts"), dict) else {}
        findings = report.get("findings") if isinstance(report.get("findings"), list) else []
        recent_runs.append({
            "file": path.name,
            "status": str(report.get("status") or "unknown"),
            "config": str(report.get("config") or ""),
            "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            "counts": {key: int(counts.get(key) or 0) for key in ("error", "warning", "info")},
            "findings": [{
                key: str(finding.get(key) or "")[:500]
                for key in ("severity", "code", "message", "component", "pin", "net")
            } for finding in findings[:100] if isinstance(finding, dict)],
        })
    return {
        "tool": "BoardProof",
        "configs": configs,
        "rule_packs": rule_packs,
        "runs": recent_runs,
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
               base: str | None = None, head: str | None = None,
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

    if action == "diff":
        try:
            with _LOCK:
                output_root = out_dir.resolve()

                def load_report(name: str | None) -> tuple[Path, dict]:
                    if not name or Path(name).name != name or "\\" in name:
                        raise ValueError("Choose a report from this workspace")
                    path = (output_root / name).resolve()
                    if path.parent != output_root or path.suffix.lower() != ".json":
                        raise ValueError("Reports must be JSON files in this workspace")
                    if not path.is_file():
                        raise ValueError(f"Report not found: {name}")
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if (not isinstance(data, dict) or data.get("tool") != "BoardProof"
                            or not isinstance(data.get("findings"), list)
                            or any(not isinstance(item, dict) for item in data["findings"])):
                        raise ValueError(f"Not a BoardProof hardware-check report: {name}")
                    return path, data

                base_path, base_data = load_report(base)
                head_path, head_data = load_report(head)
                if base_path == head_path:
                    raise ValueError("Choose two different reports")

                from .diff import compare

                result = compare(base_data, head_data)
                diff_path = out_dir / f"{base_path.stem}-to-{head_path.stem}.diff.json"
                diff_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
                introduced = result["summary"]["introduced"]
                fixed = result["summary"]["fixed"]
                persisting = result["summary"]["persisting"]
                regressed = result["regressed"]
                return {
                    "ok": not regressed,
                    "code": 1 if regressed else 0,
                    "file": diff_path.name,
                    "seconds": round(time.time() - started, 2),
                    "log": [
                        f"Compared {base_path.name} → {head_path.name}",
                        f"{introduced} new error(s), {fixed} fixed, {persisting} still open",
                    ],
                }
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            return {"ok": False, "code": 2,
                    "log": [f"{type(exc).__name__}: {exc}"],
                    "seconds": round(time.time() - started, 2)}

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

                label = "-".join(revision.lower().split())
                label = "".join(char for char in label if char.isalnum() or char == "-")[:48].strip("-")
                suffix = f"-{label}" if label else ""
                report_path = out_dir / f"{candidate.stem}{suffix}.json"
                write_reports(data, report_path, out_dir / f"{candidate.stem}{suffix}.html")
                log = [f"{data['status'].upper()}: {data['counts']['error']} error(s), "
                       f"{data['counts']['warning']} warning(s)"]
                log += [f"[{f.severity.upper()}] {f.code}: {f.message}" for f in findings]
                payload = {"ok": code == 0, "code": code, "file": report_path.name}

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
                result = check_board(board_path, design, require_routing=True, packages=packages,
                                     net_currents=spec.get("net_currents") or {},
                                     copper_oz=float(spec.get("copper_oz", 1.0)))
                result.update({"config": str(candidate), "svg": str(board_path.with_suffix(".svg")),
                               "board_sha256": hashlib.sha256(board_path.read_bytes()).hexdigest()})
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
                board_path = selected_board(out_dir, board) if board else newest_board(out_dir)
                if board and board_path is None:
                    return {"ok": False, "code": 2, "log": ["Select a board from the workspace"]}
                document = build_document(out_dir, revision or candidate.stem,
                                          report=report, config=candidate, board=board_path)
                (out_dir / "passport.html").write_text(document["html"], encoding="utf-8")
                (out_dir / "passport.json").write_text(json.dumps(document["json"], indent=2) + "\n",
                                                       encoding="utf-8")
                counts = document["json"]["counts"]
                log = [f"{document['json']['status'].upper()}: {counts['critical']} critical, "
                       f"{counts['unverified']} unverified",
                       f"hash {document['json']['passport_hash'][:16]}"]
                cleared = document["json"]["status"] == "cleared"
                payload = {"ok": cleared, "code": 0 if cleared else 1}

            else:  # pragma: no cover - guarded above
                return {"ok": False, "code": 2, "log": ["unhandled action"]}

            if render_dashboard:
                (out_dir / "index.html").write_text(render(collect(out_dir)), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - surfaced to the browser, never swallowed
            return {"ok": False, "code": 2,
                    "log": [f"{type(exc).__name__}: {exc}"], "seconds": round(time.time() - started, 2)}

    payload.update({"seconds": round(time.time() - started, 2), "log": log})
    return payload
