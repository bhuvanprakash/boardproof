"""Shared check pipeline, kept out of cli.py so prove.py can reuse it."""
from __future__ import annotations

from pathlib import Path

from .checks import run_checks
from .explain import attach, explain_findings
from .netlist import load_enet
from .packs import resolve_config
from .provenance import sha256_file, utc_now
from .providers import get_provider
from .report import summary

EXIT_OK, EXIT_FINDINGS, EXIT_USAGE = 0, 1, 2

DEFAULT_UNVERIFIED = [
    "PCB trace geometry, impedance, crosstalk and RF performance",
    "Schematic ERC, footprint-to-symbol pin mapping and pad assignments",
    "Thermal, power-integrity and inrush behaviour under load",
    "Mechanical fit, connector mating and manufacturing tolerances (DFM)",
    "Any component datasheet not captured in a vetted rule pack",
]

def load_reviewed(config_file, allow_unvetted: bool = False):
    import json
    spec = json.loads(Path(config_file).read_text(encoding='utf-8'))
    if 'netlist' not in spec:
        raise ValueError("boardproof.json is missing 'netlist'")
    resolved = resolve_config(spec, Path(config_file), require_vetted=not allow_unvetted)
    netlist_file = (Path(config_file).parent / spec['netlist']).resolve()
    design = load_enet(netlist_file)
    design.net_voltages = {str(k): float(v) for k, v in (resolved.get('net_voltages') or {}).items()}
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


