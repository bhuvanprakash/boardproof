"""One command: verify → generate → verify again → passport.

This is the whole product journey in a single reproducible pipeline, so the demo
cannot drift from what CI actually runs.
"""
from __future__ import annotations

import json
from pathlib import Path

from .checks import run_checks
from .cli_support import DEFAULT_UNVERIFIED, analyse
from .design import build_board, parse_outline, write_board
from .explain import attach, explain_findings
from .report import write_reports
from .pcb import render_svg
from .pcb_redteam import run_pcb_redteam
from .pcbcheck import check_board
from .provepkg import build_document
from .redteam import run_redteam

STEPS = ("check", "design", "pcb-check", "red-team", "layout-red-team", "passport")


def run_prove(config: Path, out_dir: Path, outline: str = "44x48mm", route: bool = True,
              revision: str = "", engine: str = "offline", explain: bool = True) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    width, height = parse_outline(outline)
    log: list[dict] = []

    def record(step: str, status: str, detail: str, **extra) -> None:
        log.append({"step": step, "status": status, "detail": detail, **extra})

    # 1. schematic verification
    data, findings, exit_code = analyse(config, explain, engine, None, None, False)
    write_reports(data, out_dir / "report.json", out_dir / "report.html")
    record("check", data["status"], f"{data['counts']['error']} error(s)")

    # 2. layout generation, refused while the circuit is broken
    design_board = None
    if exit_code != 0:
        record("design", "refused",
               "critical schematic violations must be fixed before a board is generated")
    else:
        spec, _raw, design = __import__("boardproof.cli", fromlist=["x"]).load_reviewed(config, False)
        routing_note = ""
        try:
            design_board, design_report = build_board(design, width, height,
                                                      title=f"{config.stem} candidate",
                                                      route=route, allow_generic=True)
        except ValueError as exc:
            # The router refused its own geometry check. Emit the verified placement
            # board instead of an unsafe routed one, and say so out loud.
            if not route:
                raise
            route = False
            routing_note = f"routing refused: {exc}"
            design_board, design_report = build_board(design, width, height,
                                                      title=f"{config.stem} candidate", route=False)
        board_path = out_dir / "board.kicad_pcb"
        write_board(design_board, board_path, out_dir / "board.svg")
        design_report.update({"kind": "design", "tool": "BoardProof", "config": str(config),
                              "status": "generated", "census": design_report["board"],
                              "output": str(board_path), "svg": str(out_dir / "board.svg")})
        (out_dir / "design.json").write_text(json.dumps(design_report, indent=2) + "\n",
                                             encoding="utf-8")
        record("design", "generated",
               f"{design_report['board']['footprints']} footprints, "
               f"{design_report['board']['pads']} pads"
               + (f" · {routing_note}" if routing_note else ""))

        # 3. independent physical verification
        packages = []
        for reference in spec.get("packages") or []:
            entry = reference if isinstance(reference, dict) else {"path": reference}
            from .package import load_spec

            packages.append(load_spec((Path(config).parent / str(entry["path"])).resolve(),
                                      require_vetted=True))
        pcb = check_board(board_path, design, require_routing=route, packages=packages,
                          net_currents=spec.get("net_currents") or {},
                          copper_oz=float(spec.get("copper_oz", 1.0)))
        pcb.update({"config": str(config), "svg": str(out_dir / "board.svg")})
        (out_dir / "pcb-check.json").write_text(json.dumps(pcb, indent=2) + "\n", encoding="utf-8")
        record("pcb-check", pcb["status"],
               f"{pcb['nets']['fully_connected']}/{pcb['nets']['total']} nets connected, "
               f"{pcb['counts']['error']} error(s)")

        # preview assets: derived schematic + the cited datasheet pages
        from .package import load_spec
        from .preview import render_pdf_page, render_schematic

        preview_dir = out_dir / "preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        (preview_dir / "schematic.svg").write_text(render_schematic(design), encoding="utf-8")
        for reference in spec.get("packages") or []:
            entry = reference if isinstance(reference, dict) else {"path": reference}
            try:
                package_spec = load_spec((Path(config).parent / str(entry["path"])).resolve(),
                                         require_vetted=False)
            except Exception:  # noqa: BLE001
                continue
            cited = (package_spec.get("geometry") or {}).get("citation") or {}
            document = str((package_spec.get("package") or {}).get("source", {}).get("document") or "")
            pdf = Path("datasheets") / Path(document).name
            if not pdf.is_file():
                continue
            render_pdf_page(pdf, cited.get("page", 1),
                            preview_dir / ("datasheet-" + pdf.stem + ".png"))

        # 4. does the schematic rule set catch real faults?
        rules = run_redteam(design, spec, Path(config).resolve())
        rules["config"] = str(config)
        (out_dir / "redteam.json").write_text(json.dumps(rules, indent=2) + "\n", encoding="utf-8")
        record("red-team", "passed" if rules["score"]["ratio"] >= 1.0 else "gaps",
               f"{rules['score']['caught']}/{rules['score']['targeted']} targeted faults caught")

        # 5. does the layout verifier catch real faults?
        layout = run_pcb_redteam(board_path, design)
        layout["config"] = str(config)
        (out_dir / "pcb-redteam.json").write_text(json.dumps(layout, indent=2) + "\n",
                                                  encoding="utf-8")
        record("layout-red-team", "passed" if layout["score"]["ratio"] >= 1.0 else "gaps",
               f"{layout['score']['caught']}/{layout['score']['faults']} layout faults caught")

    # 6. the artifact a human signs
    document = build_document(out_dir, revision or f"{config.stem} @ {width:g}x{height:g} mm")
    (out_dir / "passport.html").write_text(document["html"], encoding="utf-8")
    (out_dir / "passport.json").write_text(json.dumps(document["json"], indent=2) + "\n",
                                           encoding="utf-8")
    record("passport", document["json"]["status"],
           f"{document['json']['counts']['critical']} critical, "
           f"{document['json']['counts']['unverified']} unverified")

    from .dashboard import collect, render as render_dashboard

    (out_dir / "index.html").write_text(render_dashboard(collect(out_dir)), encoding="utf-8")
    return {"steps": log, "exit_code": exit_code, "out": str(out_dir)}
