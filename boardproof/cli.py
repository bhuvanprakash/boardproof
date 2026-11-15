from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .bench import format_bench, run as bench_run
from .checks import run_checks
from .dashboard import collect as collect_artifacts
from .dashboard import render as render_dashboard
from .diff import compare, format_diff
import boardproof.datasheets as datasheets
from boardproof.package import (empty_spec, load_spec, validate_spec, vet_spec)
from .design import build_board, parse_outline, write_board
from .kicad_import import design_from_netlist, export_netlist
from .explain import attach, explain_findings
from .pcb import census as pcb_census
from .pcb_redteam import run_pcb_redteam
from .pcbcheck import check_board, format_report as format_pcb
from .prove import run_prove
from .init import write_draft
from .infer import diff_against, proposal_from_pins, vet
from .netlist import NetlistError, load_enet
from .passport import build as build_passport
from .passport import render as render_passport
from .packs import PackError, resolve_config
from .provenance import sha256_file, utc_now
from .providers import ProviderError, get_provider
from .redteam import format_report as format_redteam
from .redteam import run_redteam
from .report import summary, write_reports

EXIT_OK, EXIT_FINDINGS, EXIT_USAGE = 0, 1, 2

DEFAULT_UNVERIFIED = [
    "PCB trace geometry, impedance, crosstalk and RF performance",
    "Schematic ERC, footprint-to-symbol pin mapping and pad assignments",
    "Thermal, power-integrity and inrush behaviour under load",
    "Mechanical fit, connector mating and manufacturing tolerances (DFM)",
    "Any component datasheet not captured in a vetted rule pack",
]


def _escape_action(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def load_reviewed(config_file: Path, allow_unvetted: bool = False) -> tuple[dict, dict, object]:
    """Read boardproof.json, merge vetted packs, load the netlist. Fail closed."""
    try:
        spec = json.loads(Path(config_file).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{config_file} is not valid JSON: {exc}") from exc
    if "netlist" not in spec:
        raise ValueError("boardproof.json is missing 'netlist'")
    resolved = resolve_config(spec, Path(config_file), require_vetted=not allow_unvetted)
    netlist_file = (Path(config_file).parent / spec["netlist"]).resolve()
    design = load_enet(netlist_file)
    design.net_voltages = {
        str(k): float(v) for k, v in (resolved.get("net_voltages") or {}).items()
    }
    return resolved, spec, design


def analyse(config_file: Path, explain: bool = False, engine: str = "auto",
            fixture: Path | None = None, model: str | None = None,
            allow_unvetted: bool = False) -> tuple[dict, list, int]:
    """Load, merge vetted packs, run the engine, optionally add grounded prose."""
    config_file = Path(config_file)
    spec, _raw, design = load_reviewed(config_file, allow_unvetted)
    findings = run_checks(design, spec, config_file.resolve())
    exit_code = EXIT_FINDINGS if any(f.severity == "error" for f in findings) else EXIT_OK
    try:
        netlist_sha = sha256_file(Path(design.source))[:12]
    except OSError:
        netlist_sha = ""
    meta: dict = {
        "packs": spec.get("_packs", []),
        "explain_engine": None,
        "explain_rejected": [],
        "generated_at": utc_now().replace("+00:00", "Z"),
        "engine_requested": engine,
        "netlist_sha256": netlist_sha,
        "config": config_file.name,
        "command": "boardproof check --config " + str(config_file)
                   + (" --explain" if explain else "")
                   + (" --engine offline" if engine == "offline" else ""),
        "exit_code": exit_code,
        "unverified_scope": list(spec.get("unverified_scope") or DEFAULT_UNVERIFIED),
        "verified_by_type": {
            t: sum(1 for r in spec.get("rules") or [] if r.get("type") == t)
            for t in ("pin_net", "max_voltage", "connected", "resistor_between", "firmware_gpio")
        },
    }
    if explain and findings:
        provider = get_provider(engine, fixture=fixture, model=model)
        bundle = explain_findings(findings, design, provider, spec.get("_packs"))
        attach(findings, bundle["explanations"])
        meta["explain_engine"] = bundle["engine"]
        meta["explain_rejected"] = bundle["rejected"]
    return summary(design, findings, meta), findings, exit_code


def execute(config_file: Path, json_out: Path | None = None, html_out: Path | None = None,
            annotate: bool = False, explain: bool = False, engine: str = "auto",
            fixture: Path | None = None, allow_unvetted: bool = False,
            model: str | None = None) -> int:
    data, findings, exit_code = analyse(config_file, explain, engine, fixture, model, allow_unvetted)
    meta = data
    write_reports(data, json_out, html_out)
    netlist_file = Path(data.get("netlist") or "")
    counts = data["counts"]
    print(f"BoardProof {data['status'].upper()}: {data['components']} components, "
          f"{data['nets']} nets, {counts['error']} error(s), {counts['warning']} warning(s)")
    if meta["packs"]:
        print("Rule packs: " + ", ".join(
            f"{p['id']} ({p['status']}, {p['rules']} rules, reviewer {p.get('reviewed_by') or '-'})"
            for p in meta["packs"]))
    for finding in findings:
        print(f"[{finding.severity.upper()}] {finding.code}: {finding.message}")
        explanation = (finding.evidence or {}).get("explanation")
        if explanation:
            cite = ((finding.evidence.get("provenance") or {}).get("citation") or {})
            loc = f" [datasheet p.{cite['page']}]" if cite.get("page") else ""
            print(f"    why: {explanation.get('plain_english', '')}{loc}")
            fix = explanation.get("suggested_fix")
            if fix:
                print(f"    fix: {fix}")
        if annotate:
            kind = "error" if finding.severity == "error" else "warning" if finding.severity == "warning" else "notice"
            safe_path = _escape_action(str(netlist_file))
            print(f"::{kind} file={safe_path},title=BoardProof {finding.code}::{_escape_action(finding.message)}")
    for rejected in meta["explain_rejected"]:
        print(f"[NOTICE] explanation dropped: {rejected}", file=sys.stderr)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        dest = Path(os.environ["GITHUB_STEP_SUMMARY"])
        with dest.open("a", encoding="utf-8") as handle:
            handle.write(f"## BoardProof: {data['status'].upper()}\n\n")
            handle.write(f"{counts['error']} errors, {counts['warning']} warnings; "
                         f"{data['components']} components.\n\n")
            for finding in findings:
                handle.write(f"- **{finding.severity.upper()}** `{finding.code}`: {finding.message}\n")
                explanation = (finding.evidence or {}).get("explanation")
                if explanation:
                    cite = ((finding.evidence.get("provenance") or {}).get("citation") or {})
                    where = f" (datasheet p.{cite['page']})" if cite.get("page") else ""
                    handle.write(f"  - {explanation.get('plain_english', '')}{where}\n"
                                 f"  - Fix: {explanation.get('suggested_fix', '')}\n")
            handle.write("\nVerdict computed by a deterministic engine. Results are not "
                         "electrical safety certification.\n")
    return exit_code


def cmd_infer(args) -> int:
    pdf = Path(args.pdf)
    if not pdf.is_file():
        raise ValueError(f"Datasheet PDF not found: {pdf}")
    if pdf.suffix.lower() != ".pdf":
        raise ValueError("--pdf must point at a PDF file")
    design = None
    if args.netlist:
        design = load_enet(Path(args.netlist).resolve())
    fixture = Path(args.fixture) if args.fixture else None
    provider = get_provider(args.engine, fixture=fixture, model=args.model)
    facts = provider.extract(pdf, args.component)
    facts.setdefault("_model", getattr(provider, "model", None))
    pack_id = args.pack_id or f"{args.component.lower()}-{pdf.stem.lower()}"[:64]
    proposal = proposal_from_pins(facts, design, args.component, pack_id, pdf, provider.name)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(proposal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    diff = diff_against(Path(args.previous) if args.previous else (out if out.exists() else None),
                        proposal) if args.previous else []
    if diff:
        Path(str(out) + ".diff").write_text("\n".join(diff) + "\n", encoding="utf-8")

    print(f"Proposed {len(proposal['rules'])} constraint(s) for {args.component} "
          f"via {provider.name} -> {out}")
    print(f"Status: PROPOSED (untrusted). CI will refuse this pack until vetted.")
    for rule in proposal["rules"]:
        cite = rule.get("citation") or {}
        limit = rule.get("max_v") if rule["type"] == "max_voltage" else rule.get("max_ohms")
        if rule["type"] == "max_voltage":
            limit = f"{rule.get('min_v'):g}-{rule.get('max_v'):g} V"
        elif rule["type"] == "resistor_between":
            limit = f"{rule.get('min_ohms'):g}-{rule.get('max_ohms'):g} ohm"
        else:
            limit = "must be connected"
        print(f"  - {rule['id']}: {rule['type']} {rule.get('pin', '')} {limit} "
              f"[p.{cite.get('page')}]")
    for note in proposal["pack"].get("review_notes", []):
        print(f"  ! {note}")
    if diff:
        print(f"Review diff written to {out}.diff ({len(diff)} lines)")
    print(f"Next: review the diff, then boardproof vet --proposal {out} --reviewer '<your name>'")
    return EXIT_OK


def cmd_vet(args) -> int:
    pack = vet(Path(args.proposal), args.reviewer, Path(args.out) if args.out else None)
    destination = args.out or args.proposal
    print(f"VETTED {pack['pack']['id']}: {len(pack['rules'])} rule(s) by {args.reviewer} -> {destination}")
    print("CI will now enforce these constraints.")
    return EXIT_OK


def cmd_explain(args) -> int:
    spec, _raw, design = load_reviewed(Path(args.config), args.allow_unvetted)
    findings = run_checks(design, spec, Path(args.config).resolve())
    provider = get_provider(args.engine, fixture=Path(args.fixture) if args.fixture else None,
                            model=args.model)
    bundle = explain_findings(findings, design, provider, spec.get("_packs"))
    data = {"engine": bundle["engine"], "findings": len(findings),
            "explanations": bundle["explanations"], "rejected": bundle["rejected"]}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return EXIT_FINDINGS if any(f.severity == "error" for f in findings) else EXIT_OK


def cmd_redteam(args) -> int:
    spec, _raw, design = load_reviewed(Path(args.config), args.allow_unvetted)
    result = run_redteam(design, spec, Path(args.config).resolve())
    result["config"] = str(args.config)
    print(format_redteam(result))
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    score = result["score"]
    if args.min_score is not None and score["ratio"] < args.min_score:
        print(f"[ERROR] FAULT_COVERAGE: caught {score['caught']}/{score['targeted']} targeted faults "
              f"({score['ratio']:.0%}) below required {args.min_score:.0%}; "
              f"{score['gaps']} blind spot(s) remain", file=sys.stderr)
        return EXIT_FINDINGS
    return EXIT_OK


def cmd_diff(args) -> int:
    base = json.loads(Path(args.base).read_text(encoding="utf-8"))
    head = json.loads(Path(args.head).read_text(encoding="utf-8"))
    result = compare(base, head)
    print(format_diff(result))
    for item in result["introduced"]:
        if args.annotate:
            safe = _escape_action(str(head.get("netlist") or "boardproof"))
            print(f"::error file={safe},title=BoardProof new violation "
                  f"{_escape_action(str(item.get('code')))}::{_escape_action(str(item.get('message')))}")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    if result["regressed"] and not args.no_fail:
        return EXIT_FINDINGS
    return EXIT_OK


def cmd_bench(args) -> int:
    result = bench_run(args.components, args.rules, args.repeat)
    print(format_bench(result))
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.max_checks_ms is not None and result["checks_ms"] > args.max_checks_ms:
        print(f"[ERROR] PERF: checks took {result['checks_ms']} ms "
              f"(budget {args.max_checks_ms} ms)", file=sys.stderr)
        return EXIT_FINDINGS
    return EXIT_OK


def cmd_passport(args) -> int:
    data, _findings, exit_code = analyse(args.config, args.explain, args.engine, args.fixture,
                                         args.model, args.allow_unvetted)
    redteam = None
    if args.redteam:
        redteam = json.loads(Path(args.redteam).read_text(encoding="utf-8"))
    base = json.loads(Path(args.base).read_text(encoding="utf-8")) if args.base else None
    document = build_passport(data, args.revision or "", base, redteam)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_passport(document), encoding="utf-8")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    counts = document["counts"]
    print(f"PASSPORT {document['status'].upper()}: {counts['checks_passed']} checks passed, "
          f"{counts['critical']} critical, {counts['unverified']} unverified")
    print(f"  revision {document['revision']}  hash {document['passport_hash'][:16]}  -> {out}")
    print(f"  exit {exit_code} (the passport records the verdict; it does not change it)")
    return exit_code


def cmd_init(args) -> int:
    netlist = Path(args.netlist)
    design = load_enet(netlist.resolve())
    out = Path(args.out)
    config, notes = write_draft(design, netlist, out, args.firmware, None)
    print(f"Draft config written to {out}: {len(config['rules'])} rule(s), all severity=warning.")
    print("Nothing here can block a build until you review it and set severity to 'error'.")
    for note in notes[:12]:
        print(f"  ! {note}")
    if len(notes) > 12:
        print(f"  ! ... {len(notes) - 12} more note(s) in {out}")
    print(f"Next: review {out}, then boardproof check --config {out}")
    return EXIT_OK


def cmd_dashboard(args) -> int:
    directory = Path(args.dir)
    found = collect_artifacts(directory)
    out = Path(args.out) if args.out else directory / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    page = render_dashboard(found)
    out.write_text(page, encoding="utf-8")
    import hashlib

    stamp = hashlib.sha256(page.encode("utf-8")).hexdigest()[:8]
    versioned = out.with_name(out.stem + "-" + stamp + out.suffix)
    versioned.write_text(page, encoding="utf-8")
    print(f"Dashboard: {out}")
    print(f"  cache-safe copy: {versioned}   (build {stamp})")
    print(f"  ({len(found['reports'])} report(s), "
          f"{len(found.get('redteams') or [])} redteam, {1 if found['passport'] else 0} passport, "
          f"{len(found['diffs'])} diff)")
    return EXIT_OK


def cmd_serve(args) -> int:
    from .serve import main as serve_main

    directory = Path(args.dir)
    if not (directory / "index.html").exists():
        cmd_dashboard(argparse.Namespace(dir=str(directory), out=None))
    return serve_main(directory, args.port, Path(args.root), args.token, args.read_only)


def cmd_studio(args) -> int:
    return cmd_serve(args)


def cmd_design(args) -> int:
    spec, _raw, design = load_reviewed(Path(args.config), args.allow_unvetted)
    findings = run_checks(design, spec, Path(args.config).resolve())
    blocking = [f for f in findings if f.severity == "error"]
    if blocking and not args.force:
        print(f"DESIGN REFUSED: the schematic still has {len(blocking)} critical violation(s). "
              "Fix the circuit before generating a board.", file=sys.stderr)
        for finding in blocking:
            print(f"  [{finding.code}] {finding.message}", file=sys.stderr)
        return EXIT_FINDINGS
    width, height = parse_outline(args.outline)
    board, report = build_board(design, width, height,
                                title=f"{Path(args.config).stem} candidate", route=args.route,
                                allow_generic=not args.strict_footprints)
    out = Path(args.output)
    svg = Path(args.svg) if args.svg else out.with_suffix(".svg")
    write_board(board, out, svg)
    report.update({
        "tool": "BoardProof", "kind": "design", "config": str(args.config),
        "output": str(out), "svg": str(svg),
        "status": "generated", "census": report["board"],
        "warning": "Approximate land patterns. Replace with fab-approved footprints "
                   "and finish routing before fabrication.",
    })
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    counts = pcb_census(board)
    print(f"DESIGN: {counts['footprints']} footprints, {counts['pads']} pads on a "
          f"{counts['width_mm']:g}x{counts['height_mm']:g} mm board -> {out}")
    guessed = report["footprints"]["guessed"]
    if guessed:
        print("  ! footprint guessed from the designator for " + ", ".join(guessed) +
              " - name the footprint in the export, or pass --strict-footprints to refuse"
              " unverified geometry")
    print(f"  routing: {'attempted' if args.route else 'not attempted (a placement board)'}")
    for item in report["placement"]:
        print(f"  {item['ref']:<4} {item['pattern']:<22} ({item['x']:>5}, {item['y']:>5})  "
              f"{'; '.join(item['rules'])}")
    print(f"  next: boardproof pcb-check --board {out} --config {args.config}")
    return EXIT_OK


def cmd_pcb_check(args) -> int:
    spec, _raw, design = load_reviewed(Path(args.config), args.allow_unvetted)
    packages = []
    for reference in spec.get("packages") or []:
        entry = reference if isinstance(reference, dict) else {"path": reference}
        path = (Path(args.config).parent / str(entry["path"])).resolve()
        packages.append(load_spec(path, require_vetted=not args.allow_unvetted))
    result = check_board(Path(args.board), design, require_routing=args.require_routing,
                         packages=packages,
                         net_currents=spec.get("net_currents") or {},
                         copper_oz=float(spec.get("copper_oz", 1.0)))
    result["config"] = str(args.config)
    result["svg"] = str(Path(args.board).with_suffix(".svg"))
    print(format_pcb(result))
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    if args.passport:
        document = build_passport(
            {"netlist": result["board"], "components": result["census"]["footprints"],
             "nets": result["census"]["nets"], "findings": [],
             "unverified_scope": result["unverified"], "verified_by_type": {},
             "counts": {"error": 0, "warning": 0, "info": 0},
             "status": result["status"], "netlist_sha256": ""},
            args.revision or "", None, None)
        document["pcb"] = result
        Path(args.passport).parent.mkdir(parents=True, exist_ok=True)
        Path(args.passport).write_text(render_passport(document), encoding="utf-8")
        print(f"  passport updated -> {args.passport}")
    return EXIT_FINDINGS if result["counts"]["error"] else EXIT_OK


def cmd_datasheet_fetch(args) -> int:
    if (getattr(args, "datasheet_action", "fetch") == "verify") or args.verify:
        result = datasheets.verify(args.part, Path(args.dir))
        status = "OK" if result["ok"] else "HASH MISMATCH"
        print(f"DATASHEET {status}: {result['part']} -> {result['path']}")
        print(f"  expected {str(result['expected_sha256'])[:16]}  actual "
              f"{result['actual_sha256'][:16]}")
        return EXIT_OK if result["ok"] else EXIT_FINDINGS
    entry = datasheets.fetch(args.part, Path(args.dir), args.url, args.refresh)
    print(f"DATASHEET {entry['status'].upper()}: {entry['part']} -> {entry['path']}")
    print(f"  source {entry.get('url') or '(cached)'}")
    print(f"  sha256 {entry['sha256'][:16]}…  {entry.get('bytes', 0):,} bytes")
    print("  next: boardproof package infer --pdf " + entry["path"] +
          f" --part {entry['part']} --engine gemini")
    return EXIT_OK


def cmd_package_infer(args) -> int:
    pdf = Path(args.pdf)
    if not pdf.is_file():
        raise ValueError(f"datasheet not found: {pdf}")
    provider = get_provider(args.engine, fixture=Path(args.fixture) if args.fixture else None,
                            model=args.model)
    facts = provider.extract_package(pdf, args.part)
    spec = empty_spec(args.pack_id or f"{args.part.lower()}-{pdf.stem}", args.part,
                      str(facts.get("package", "")))
    spec["package"]["source"] = {"document": pdf.name, "sha256": sha256_file(pdf),
                                 "url": (datasheets.read_registry(Path("datasheets"))
                                         .get("documents", {})
                                         .get("".join(ch for ch in args.part.lower() if ch.isalnum()), {})
                                         .get("url", ""))}
    spec["package"]["extracted_by"] = {"engine": provider.name, "at": utc_now()}
    spec["geometry"] = {
        "pin_count": facts.get("pin_count"),
        "pitch_mm": facts.get("pitch_mm"),
        "body_w_mm": facts.get("body_w_mm"),
        "body_h_mm": facts.get("body_h_mm"),
        "pad_w_mm": facts.get("pad_w_mm"),
        "pad_h_mm": facts.get("pad_h_mm"),
        "thermal_pad": bool(facts.get("thermal_pad")),
        "citation": {"page": str(facts.get("cited_page", "")),
                     "quote": str(facts.get("cited_quote", ""))},
    }
    spec["limits"]["max_current_per_pin_a"] = facts.get("max_current_per_pin_a")
    if facts.get("uncertainty"):
        spec["notes"].append(str(facts["uncertainty"]))
    validate_spec(spec, f"proposal:{spec['package']['id']}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    geo = spec["geometry"]
    print(f"PACKAGE PROPOSED: {args.part} {spec['package']['package']} -> {out}")
    print(f"  {geo['pin_count']} pins · pitch {geo['pitch_mm']:g} mm · body "
          f"{geo['body_w_mm']}×{geo['body_h_mm']} mm · cited p.{geo['citation']['page']}")
    print(f"  quote: {geo['citation']['quote'][:90]!r}")
    print(f"  next: boardproof package vet --proposal {out} --reviewer '<name>'")
    return EXIT_OK


def cmd_package_vet(args) -> int:
    spec = vet_spec(Path(args.proposal), args.reviewer, Path(args.out) if args.out else None)
    print(f"PACKAGE VETTED: {spec['package']['id']} by {args.reviewer} "
          f"-> {args.out or args.proposal}")
    return EXIT_OK


def cmd_verify_kicad(args) -> int:
    """Verify an existing KiCad layout against its own schematic netlist."""
    import json as _json

    from .pcb import read_kicad
    from .pcbview import board_model, render_2d, render_3d

    board_path = Path(args.board)
    if not board_path.is_file():
        raise ValueError(f"board not found: {board_path}")
    if args.netlist:
        netlist = Path(args.netlist)
    elif args.schematic:
        netlist = export_netlist(Path(args.schematic))
    else:
        raise ValueError("pass --netlist <file.net> or --schematic <file.kicad_sch>")

    design = design_from_netlist(netlist)
    board = read_kicad(board_path.read_text(encoding="utf-8"))
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    stem = board_path.stem.replace(" ", "-")
    (out / f"{stem}.svg").write_text(render_2d(board), encoding="utf-8")
    (out / f"{stem}-3d.svg").write_text(render_3d(board), encoding="utf-8")
    (out / f"{stem}-model.json").write_text(_json.dumps(board_model(board), separators=(",", ":")),
                                            encoding="utf-8")
    advisory = set() if args.strict else {"CLEARANCE", "DECOUPLING_DISTANCE", "TRACK_CURRENT"}
    result = check_board(board_path, design, run_drc=not args.no_drc, advisory=advisory)
    result.update({"svg": str(out / f"{stem}.svg"), "config": str(board_path),
                   "netlist": str(netlist), "title": args.title or stem,
                   "parts": [{"ref": f.ref, "pattern": f.pattern.split(":")[-1],
                              "pads": len(f.pads)} for f in board.footprints]})
    (out / f"{stem}-pcb.json").write_text(_json.dumps(result, indent=2) + "\n", encoding="utf-8")
    counts = result["counts"]
    print(f"VERIFIED LAYOUT {result['status'].upper()}: {result['census']['footprints']} footprints, "
          f"{result['census']['pads']} pads, {result['census']['nets']} nets on a "
          f"{result['census']['width_mm']:g}x{result['census']['height_mm']:g} mm board")
    note = getattr(board, "outline_note", "")
    if note:
        print(f"  ! {note}")
    print(f"  netlist: {Path(netlist).name} ({len(design.components)} components, "
          f"{len(design.nets)} nets) -> {out / (stem + '.svg')}")
    policy = result.get("policy") or {}
    print(f"  {counts['error']} error(s), {counts['warning']} warning(s), "
          f"{counts.get('notice', 0)} notice(s) · policy: "
          f"{'strict' if not policy.get('advisory') else 'advisory (' + ', '.join(policy['advisory']) + ')'}")
    for finding in result["findings"][:6]:
        print(f"  [{finding['severity'].upper()}] {finding['code']}: {finding['message'][:110]}")
    cmd_dashboard(argparse.Namespace(dir=str(out), out=None))
    return EXIT_FINDINGS if counts["error"] else EXIT_OK


def cmd_prove(args) -> int:
    result = run_prove(Path(args.config), Path(args.outdir), args.outline, not args.no_route,
                       args.revision, args.engine, not args.no_explain)
    width = max(len(step["step"]) for step in result["steps"])
    print("BOARDPROOF PROVE")
    marks = {"passed": "PASS", "generated": "DONE", "refused": "STOP", "gaps": "GAP ",
             "failed": "FAIL", "blocked": "BLOCK", "cleared": "CLEAR"}
    for step in result["steps"]:
        mark = marks.get(step["status"], step["status"].upper())
        print("  [" + mark.ljust(5) + "] " + step["step"].ljust(width) + "  " + step["detail"])
    print(f"  artifacts: {result['out']}  (report.html, board.kicad_pcb, board.svg, "
          "pcb-check.json, redteam.json, pcb-redteam.json, passport.html, index.html)")
    return result["exit_code"]


def cmd_pcb_redteam(args) -> int:
    spec, _raw, design = load_reviewed(Path(args.config), args.allow_unvetted)
    result = run_pcb_redteam(Path(args.board), design)
    if not result.get("faults"):
        print(f"LAYOUT RED TEAM skipped: {result.get('reason')}")
        return EXIT_USAGE
    score = result["score"]
    print(f"LAYOUT RED TEAM  {score['caught']}/{score['faults']} injected layout faults caught "
          f"({int(round(score['ratio'] * 100))}%)")
    for fault in result["faults"]:
        print(f"  [{'PASS' if fault['status'] == 'caught' else 'GAP '}] {fault['kind']:<14} "
              f"{fault['summary']}")
        if fault["caught_by"]:
            print(f"         caught by {', '.join(fault['caught_by'])}")
    for text in result.get("suggestions", []):
        print(f"  -> {text}")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return EXIT_FINDINGS if score["gaps"] else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="boardproof",
        description="Hardware CI: AI proposes constraints from datasheets, humans vet them, "
                    "a deterministic engine enforces them.")
    sub = parser.add_subparsers(dest="action", required=True)

    c = sub.add_parser("check", help="Fail CI on violations of vetted rules")
    c.add_argument("--config", type=Path, default=Path("boardproof.json"))
    c.add_argument("--json", type=Path, default=None)
    c.add_argument("--html", type=Path, default=None)
    c.add_argument("--annotate", action="store_true", help="Emit GitHub Actions annotations")
    c.add_argument("--explain", action="store_true", help="Add grounded explanations for findings")
    c.add_argument("--engine", default="auto", choices=["auto", "gemini", "offline"])
    c.add_argument("--fixture", type=Path, default=None)
    c.add_argument("--model", default=None)
    c.add_argument("--allow-unvetted", action="store_true",
                   help="LOCAL DEMO ONLY: run with proposed (unreviewed) packs")

    i = sub.add_parser("infer", help="Propose constraints from a datasheet PDF (AI, untrusted)")
    i.add_argument("--pdf", type=Path, required=True)
    i.add_argument("--component", required=True)
    i.add_argument("--netlist", type=Path, default=None)
    i.add_argument("--out", type=Path, required=True)
    i.add_argument("--previous", type=Path, default=None, help="Existing pack to diff against")
    i.add_argument("--pack-id", default=None)
    i.add_argument("--engine", default="auto", choices=["auto", "gemini", "offline"])
    i.add_argument("--fixture", type=Path, default=None)
    i.add_argument("--model", default=None)

    v = sub.add_parser("vet", help="Human review gate: mark a proposal as vetted")
    v.add_argument("--proposal", type=Path, required=True)
    v.add_argument("--reviewer", required=True)
    v.add_argument("--out", type=Path, default=None)

    e = sub.add_parser("explain", help="Explain current findings with citations")
    e.add_argument("--config", type=Path, default=Path("boardproof.json"))
    e.add_argument("--out", type=Path, default=None)
    e.add_argument("--engine", default="auto", choices=["auto", "gemini", "offline"])
    e.add_argument("--fixture", type=Path, default=None)
    e.add_argument("--model", default=None)
    e.add_argument("--allow-unvetted", action="store_true")

    pp = sub.add_parser("passport", help="Emit a Manufacturing Preflight Passport (HTML + JSON)")
    pp.add_argument("--config", type=Path, default=Path("boardproof.json"))
    pp.add_argument("--out", type=Path, default=Path("artifacts/passport.html"))
    pp.add_argument("--json", type=Path, default=Path("artifacts/passport.json"))
    pp.add_argument("--revision", default="")
    pp.add_argument("--base", type=Path, default=None, help="Previous report for the revision delta")
    pp.add_argument("--redteam", type=Path, default=None, help="Red team JSON to embed")
    pp.add_argument("--explain", action="store_true")
    pp.add_argument("--engine", default="auto", choices=["auto", "gemini", "offline"])
    pp.add_argument("--fixture", type=Path, default=None)
    pp.add_argument("--model", default=None)
    pp.add_argument("--allow-unvetted", action="store_true")

    ini = sub.add_parser("init", help="Generate a draft boardproof.json from a netlist")
    ini.add_argument("--netlist", type=Path, required=True)
    ini.add_argument("--out", type=Path, default=Path("boardproof.json"))
    ini.add_argument("--firmware", default=None, help="Relative path to the firmware header")

    db = sub.add_parser("dashboard", help="Build one page linking every artifact")
    db.add_argument("--dir", default="artifacts")
    db.add_argument("--out", type=Path, default=None)

    sv = sub.add_parser("serve", help="Serve the artifacts (Cloud Run compatible)")
    sv.add_argument("--dir", default="artifacts")
    sv.add_argument("--port", type=int, default=None)
    sv.add_argument("--root", default=".", help="Workspace the studio may run configs from")

    st = sub.add_parser("studio", help="Interactive studio: run the pipeline from the dashboard")
    st.add_argument("--dir", default="artifacts")
    st.add_argument("--port", type=int, default=None)
    st.add_argument("--root", default=".")
    st.add_argument("--token", default=None,
                    help="Require this token for actions (pass ?token=... in the URL)")
    st.add_argument("--read-only", action="store_true",
                    help="Serve the view only; refuse every action (safe for public tunnels)")

    ds = sub.add_parser("datasheet", help="Fetch and pin the datasheet for a part number")
    ds.add_argument("datasheet_action", nargs="?", default="fetch",
                    choices=["fetch", "verify"])
    ds.add_argument("--part", required=True)
    ds.add_argument("--dir", default="datasheets")
    ds.add_argument("--url", default=None)
    ds.add_argument("--refresh", action="store_true")
    ds.add_argument("--verify", action="store_true", help="Re-hash the stored document")

    pk = sub.add_parser("package", help="Datasheet package geometry: infer, then vet")
    pk_sub = pk.add_subparsers(dest="package_action", required=True)
    pk_i = pk_sub.add_parser("infer")
    pk_i.add_argument("--pdf", type=Path, required=True)
    pk_i.add_argument("--part", required=True)
    pk_i.add_argument("--out", type=Path, required=True)
    pk_i.add_argument("--pack-id", default=None)
    pk_i.add_argument("--engine", default="auto", choices=["auto", "gemini", "offline"])
    pk_i.add_argument("--fixture", type=Path, default=None)
    pk_i.add_argument("--model", default=None)
    pk_v = pk_sub.add_parser("vet")
    pk_v.add_argument("--proposal", type=Path, required=True)
    pk_v.add_argument("--reviewer", required=True)
    pk_v.add_argument("--out", type=Path, default=None)

    vk = sub.add_parser("verify", help="Verify an existing KiCad board against its schematic")
    vk.add_argument("--board", type=Path, required=True)
    vk.add_argument("--netlist", type=Path, default=None)
    vk.add_argument("--schematic", type=Path, default=None)
    vk.add_argument("--outdir", default="artifacts")
    vk.add_argument("--title", default=None)
    vk.add_argument("--no-drc", action="store_true")
    vk.add_argument("--strict", action="store_true",
                    help="Treat our geometric clearance pass as blocking (default on imported "
                         "boards: advisory, because KiCad DRC is the authority)")

    pv = sub.add_parser("prove", help="verify -> generate -> verify again -> passport, in one run")
    pv.add_argument("--config", type=Path, default=Path("boardproof.json"))
    pv.add_argument("--outdir", default="artifacts")
    pv.add_argument("--outline", default="auto")
    pv.add_argument("--revision", default="")
    pv.add_argument("--engine", default="offline", choices=["auto", "gemini", "offline"])
    pv.add_argument("--no-route", action="store_true")
    pv.add_argument("--no-explain", action="store_true")

    prt = sub.add_parser("pcb-redteam", help="Mutate the board and score the layout verifier")
    prt.add_argument("--board", type=Path, required=True)
    prt.add_argument("--config", type=Path, default=Path("boardproof.json"))
    prt.add_argument("--json", type=Path, default=None)
    prt.add_argument("--allow-unvetted", action="store_true")

    dz = sub.add_parser("design", help="Generate an editable PCB candidate from a verified design")
    dz.add_argument("--config", type=Path, default=Path("boardproof.json"))
    dz.add_argument("--outline", default="auto",
                    help="WxHmm, or 'auto' to fit the outline to the copper")
    dz.add_argument("--layers", type=int, default=2, choices=[2])
    dz.add_argument("--output", type=Path, default=Path("artifacts/board.kicad_pcb"))
    dz.add_argument("--svg", type=Path, default=None)
    dz.add_argument("--json", type=Path, default=None)
    dz.add_argument("--route", action="store_true", help="Also attempt copper routing")
    dz.add_argument("--force", action="store_true",
                    help="Generate even though the schematic still has critical violations")
    dz.add_argument("--allow-unvetted", action="store_true")
    dz.add_argument("--strict-footprints", action="store_true", default=False,
                    help="Refuse to generate when the export does not name a footprint "
                         "(otherwise the fallback is used and flagged in the report)")

    pc = sub.add_parser("pcb-check", help="Independently verify a generated board")
    pc.add_argument("--board", type=Path, required=True)
    pc.add_argument("--config", type=Path, default=Path("boardproof.json"))
    pc.add_argument("--json", type=Path, default=None)
    pc.add_argument("--passport", type=Path, default=None)
    pc.add_argument("--revision", default="")
    pc.add_argument("--require-routing", action="store_true",
                    help="Treat unrouted nets as errors")
    pc.add_argument("--allow-unvetted", action="store_true")

    rt = sub.add_parser("redteam", help="Inject realistic faults and score the rule set")
    rt.add_argument("--config", type=Path, default=Path("boardproof.json"))
    rt.add_argument("--json", type=Path, default=None)
    rt.add_argument("--min-score", type=float, default=None,
                    help="Exit 1 if the caught-fault ratio falls below this (0-1)")
    rt.add_argument("--allow-unvetted", action="store_true")

    df = sub.add_parser("diff", help="Compare two reports: block only NEW violations")
    df.add_argument("--base", type=Path, required=True)
    df.add_argument("--head", type=Path, required=True)
    df.add_argument("--json", type=Path, default=None)
    df.add_argument("--annotate", action="store_true")
    df.add_argument("--no-fail", action="store_true", help="Report only; never exit 1")

    b = sub.add_parser("bench", help="Measure engine throughput on a synthetic board")
    b.add_argument("--components", type=int, default=4000)
    b.add_argument("--rules", type=int, default=800)
    b.add_argument("--repeat", type=int, default=3)
    b.add_argument("--max-checks-ms", type=float, default=None)
    b.add_argument("--json", type=Path, default=None)

    args = parser.parse_args(argv)
    try:
        if args.action == "check":
            return execute(args.config, args.json, args.html, args.annotate, args.explain,
                           args.engine, args.fixture, args.allow_unvetted, args.model)
        if args.action == "vet":
            return cmd_vet(args)
        if args.action == "passport":
            return cmd_passport(args)
        if args.action == "init":
            return cmd_init(args)
        if args.action == "dashboard":
            return cmd_dashboard(args)
        if args.action == "serve":
            return cmd_serve(args)
        if args.action == "studio":
            return cmd_studio(args)
        if args.action == "datasheet":
            return cmd_datasheet_fetch(args)
        if args.action == "package":
            if args.package_action == "infer":
                return cmd_package_infer(args)
            return cmd_package_vet(args)
        if args.action == "verify":
            return cmd_verify_kicad(args)
        if args.action == "prove":
            return cmd_prove(args)
        if args.action == "pcb-redteam":
            return cmd_pcb_redteam(args)
        if args.action == "design":
            return cmd_design(args)
        if args.action == "pcb-check":
            return cmd_pcb_check(args)
        if args.action == "redteam":
            return cmd_redteam(args)
        if args.action == "diff":
            return cmd_diff(args)
        if args.action == "bench":
            return cmd_bench(args)
        if args.action == "explain":
            return cmd_explain(args)
        if args.action == "infer":
            return cmd_infer(args)
        return EXIT_USAGE
    except (OSError, ValueError, NetlistError, PackError, ProviderError) as exc:
        print(f"BoardProof ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
