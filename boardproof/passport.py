"""Manufacturing Risk Passport: the one page a judge (or a factory) keeps.

Answers exactly three questions, in this order:
  1. what failed?
  2. what was actually verified, and by whom?
  3. what remains unverified before anyone manufactures this?

Deliberately rendered as a paper document rather than a dashboard: it is an
artifact you attach to a revision, not a view you refresh.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any

from .brand import mark as _mark

CSS = """
:root{--paper:#f6f5f1;--ink:#13171d;--ink2:#4b5563;--ink3:#7b8494;--rule:#d9d6cd;
--teal:#0c6b58;--red:#a51f1a;--amber:#8a5a00;--mono:ui-monospace,SFMono-Regular,Menlo,monospace;
--sans:ui-sans-serif,-apple-system,'Segoe UI',system-ui,sans-serif;--serif:ui-serif,Georgia,'Times New Roman',serif}
*{box-sizing:border-box}
body{margin:0;background:#e7e5df;color:var(--ink);font:16px/1.6 var(--sans);
  -webkit-font-smoothing:antialiased;padding:28px 16px}
.sheet{max-width:880px;margin:0 auto;background:var(--paper);position:relative;
  padding:52px 56px 44px;box-shadow:0 1px 2px rgba(0,0,0,.08),0 18px 50px -24px rgba(0,0,0,.45)}
.sheet:before{content:'';position:absolute;inset:0;pointer-events:none;
  background-image:radial-gradient(rgba(0,0,0,.028) 1px,transparent 1px);background-size:4px 4px}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;
  border-bottom:2px solid var(--ink);padding-bottom:16px}
.brandline{display:flex;align-items:center;gap:9px;font:600 13px/1 var(--mono);
  letter-spacing:.22em;text-transform:uppercase}
.mark{width:17px;height:17px;background:var(--ink);color:var(--paper);display:grid;place-items:center;
  font:700 13px/1 var(--mono)}
h1{font-family:var(--serif);font-size:33px;line-height:1.16;letter-spacing:-.4px;font-weight:600;
  margin:16px 0 4px}
.meta{font:13.5px/1.7 var(--mono);color:var(--ink3)}
.stamp{border:2.5px solid var(--red);color:var(--red);padding:9px 18px;transform:rotate(-4deg);
  font:700 21px/1 var(--mono);letter-spacing:.16em;text-transform:uppercase;white-space:nowrap}
.stamp.clear{border-color:var(--teal);color:var(--teal)}
.counters{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin:26px 0 4px;
  border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}
.counters div{padding:16px 4px}
.counters div+div{border-left:1px solid var(--rule);padding-left:22px}
.counters span{display:block;font:600 11.5px/1 var(--mono);letter-spacing:.16em;
  text-transform:uppercase;color:var(--ink3);margin-bottom:8px}
.counters strong{font-family:var(--serif);font-size:36px;font-weight:600;letter-spacing:-1px;display:block}
.counters .bad strong{color:var(--red)}.counters .warn strong{color:var(--amber)}
.counters em{display:block;font-style:normal;font-size:13.5px;color:var(--ink3);margin-top:2px}
h2{font:600 12px/1 var(--mono);letter-spacing:.2em;text-transform:uppercase;color:var(--ink2);
  margin:34px 0 12px;padding-bottom:7px;border-bottom:1px solid var(--rule)}
.item{display:grid;grid-template-columns:auto 1fr;gap:10px;padding:11px 0;border-bottom:1px solid #e6e3da}
.item:last-child{border-bottom:0}
.tag{font:700 11px/1 var(--mono);letter-spacing:.1em;padding:4px 6px;color:var(--red);
  background:#f6e7e5;align-self:start;margin-top:3px;white-space:nowrap}
.tag.ok{color:var(--teal);background:#e3efe9}
.tag.gap{color:var(--amber);background:#f4eddc}
.item h3{margin:0;font-size:15.5px;font-weight:600;line-height:1.45}
.item p{margin:3px 0 0;font-size:14.5px;color:var(--ink2)}
.item .fix{margin-top:4px;font-size:14.5px;color:var(--teal)}
.expect{font-family:var(--mono);font-size:13.5px;color:var(--ink2);margin-top:4px}
.expect b{font-weight:600;color:var(--ink)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:28px}
ul.plain{margin:0;padding:0;list-style:none}
ul.plain li{font-size:14.5px;color:var(--ink2);padding:4px 0 4px 15px;position:relative;line-height:1.5}
ul.plain li:before{position:absolute;left:0;font-size:12px;top:6px}
ul.chk li:before{content:'✓';color:var(--teal)}
ul.unk li:before{content:'×';color:var(--amber);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:14px}
th{font:600 11px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink3);
  text-align:left;padding:0 10px 7px 0}
td{padding:8px 10px 8px 0;border-top:1px solid #e6e3da;color:var(--ink2);vertical-align:top}
td.mono{font-family:var(--mono);font-size:13px}
.sign{display:flex;justify-content:space-between;gap:24px;margin-top:34px;padding-top:14px;
  border-top:2px solid var(--ink);font-size:13px;color:var(--ink3)}
.sign div{flex:1}
.sign em{display:block;font:12px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;
  color:var(--ink3);margin-bottom:15px;font-style:normal}
.sign b{display:block;border-top:1px solid var(--ink3);padding-top:5px;font-weight:500;color:var(--ink2)}
.hash{font-family:var(--mono);font-size:12.5px;color:var(--ink3);word-break:break-all}
.note{font-size:13px;color:var(--ink3);margin-top:10px;line-height:1.6}
.boardwrap{margin:6px 0 2px;border:1px solid var(--rule);border-radius:6px;padding:10px;
  background:#fff;max-width:520px}
.boardwrap svg{display:block;width:100%;height:auto}
@media print{
  body{background:#fff;padding:0}
  .sheet{box-shadow:none;max-width:none;padding:0}
  @page{size:A4;margin:14mm}
  h2{break-after:avoid}.item,table{break-inside:avoid}
}
@media(max-width:720px){.sheet{padding:30px 22px}.counters{grid-template-columns:1fr}
  .counters div+div{border-left:0;border-top:1px solid var(--rule);padding-left:4px}
  .two{grid-template-columns:1fr}.stamp{transform:none;font-size:17px;padding:7px 12px}}
"""


def passport_hash(data: dict) -> str:
    payload = {
        "netlist_sha256": data.get("netlist_sha256"),
        "config": data.get("config"),
        "packs": [(p.get("id"), p.get("reviewed_by"), p.get("status")) for p in data.get("packs") or []],
        "findings": [[f.get("code"), f.get("message"), f.get("severity")] for f in data.get("findings") or []],
        "unverified": data.get("unverified_scope") or [],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return digest


def build(data: dict, revision: str = "", base: dict | None = None,
          redteam: dict | None = None) -> dict:
    """Compose the passport document model from a check summary."""
    from .diff import compare

    errors = [f for f in data.get("findings") or [] if f.get("severity") == "error"]
    warnings = [f for f in data.get("findings") or [] if f.get("severity") == "warning"]
    by_type = data.get("verified_by_type") or {}
    checks_passed = sum(int(v) for v in by_type.values()) - len(errors)
    document = {
        "tool": "BoardProof",
        "kind": "manufacturing-preflight-passport",
        "revision": revision or data.get("revision") or "unlabelled revision",
        "status": "blocked" if errors else "cleared",
        "generated_at": data.get("generated_at"),
        "netlist": data.get("netlist"),
        "netlist_sha256": data.get("netlist_sha256"),
        "config": data.get("config"),
        "components": data.get("components"),
        "nets": data.get("nets"),
        "counts": {
            "checks_passed": max(0, checks_passed),
            "critical": len(errors),
            "warnings": len(warnings),
            "unverified": len(data.get("unverified_scope") or []),
        },
        "failures": errors,
        "warnings": warnings,
        "verified_by_type": by_type,
        "packs": data.get("packs") or [],
        "unverified_scope": data.get("unverified_scope") or [],
        "redteam": redteam,
        "delta": compare(base, data) if base else None,
        "note": ("A passport is a statement of scope, not a manufacturing certification. "
                 "Unverified items must be closed by the responsible engineer."),
    }
    document["passport_hash"] = passport_hash({**data, **document})
    return document


def _failure(item: dict) -> str:
    ev = item.get("evidence") or {}
    prov = ev.get("provenance") or {}
    cite = prov.get("citation") or {}
    expl = ev.get("explanation") or {}
    expected = ""
    code = item.get("code")
    if code == "MAX_VOLTAGE":
        expected = (f"<div class=\"expect\">observed <b>{ev.get('voltage')} V</b> on "
                    f"{ev.get('net')} · approved <b>{ev.get('min_v')}–{ev.get('max_v')} V</b></div>")
    elif code == "PIN_NET":
        expected = (f"<div class=\"expect\">observed <b>{ev.get('observed_net') or 'unconnected'}</b> · "
                    f"approved <b>{' or '.join(str(x) for x in ev.get('expected_nets') or [])}</b></div>")
    elif code == "FIRMWARE_GPIO":
        expected = (f"<div class=\"expect\">firmware <b>{ev.get('define')}={ev.get('firmware_gpio')}</b> · "
                    f"netlist <b>{ev.get('component')}.{ev.get('pin')}=GPIO{ev.get('schematic_gpio')}</b></div>")
    elif code == "RESISTOR_BETWEEN":
        def val(x):
            return f"{x:g}" if isinstance(x, (int, float)) else "?"

        expected = (f"<div class=\"expect\">{ev.get('net_a')} ↔ {ev.get('net_b')} · "
                    f"approved <b>{val(ev.get('min_ohms'))}–{val(ev.get('max_ohms'))} Ω</b></div>")
    elif code == "CONNECTED":
        expected = f"<div class=\"expect\">observed <b>no net</b> · required <b>connected</b></div>"
    cite_line = ""
    if cite.get("page"):
        loc = f"p.{cite['page']}"
        if cite.get("table"):
            loc += f" Table {cite['table']}"
        cite_line = (f"<p><span class=\"hash\">{html.escape(loc)}</span> &nbsp;"
                     f"&ldquo;{html.escape(str(cite.get('quote', '')))}&rdquo;</p>")
    fix = expl.get("suggested_fix")
    return (
        '<div class="item"><span class="tag">critical</span><div><h3>'
        + html.escape(str(item.get("message", "")).split("] ", 1)[-1]) + "</h3>"
        + expected + cite_line
        + (f'<p class="fix">{html.escape(fix)}</p>' if fix else "")
        + "</div></div>"
    )


def render(document: dict) -> str:
    counts = document["counts"]
    blocked = document["status"] == "blocked"
    failures = "".join(_failure(f) for f in document["failures"]) or (
        '<div class="item"><span class="tag ok">pass</span><div><h3>No violations of the approved rules'
        "</h3><p>Every configured cross-layer constraint held. This does not certify the board.</p></div></div>")
    verified_rows = "".join(
        f"<li>{html.escape(label)} <span class=\"hash\">×{count}</span></li>"
        for label, count in (
            ("Pin → net assignments", document["verified_by_type"].get("pin_net", 0)),
            ("Supply and voltage limits", document["verified_by_type"].get("max_voltage", 0)),
            ("Required connections", document["verified_by_type"].get("connected", 0)),
            ("Pull-ups and resistor values", document["verified_by_type"].get("resistor_between", 0)),
            ("Firmware ↔ schematic pin contract", document["verified_by_type"].get("firmware_gpio", 0)),
        ) if count
    ) or "<li>No rule classes configured</li>"
    unverified = "".join(f"<li>{html.escape(str(i))}</li>" for i in document["unverified_scope"])
    packs = "".join(
        "<tr><td class=\"mono\">" + html.escape(str(p.get("id"))) + "</td><td class=\"mono\">"
        + html.escape(str(p.get("status"))) + "</td><td>" + html.escape(str(p.get("reviewed_by") or "—"))
        + "</td><td class=\"mono\">" + str(p.get("rules", 0)) + "</td></tr>"
        for p in document["packs"]
    ) or '<tr><td colspan="4">no rule pack loaded - only inline rules</td></tr>'

    reviewers = ", ".join(sorted(
        {str(p.get("reviewed_by") or "") for p in document["packs"]} - {""}))
    rt = document.get("redteam") or {}
    rt_score = rt.get("score") or {}
    redteam = ""
    if rt_score:
        redteam = (
            '<h2>Fault coverage · mutation test of the rule set</h2>'
            '<div class="counters"><div><span>targeted faults caught</span><strong>'
            + f"{rt_score.get('caught', 0)}/{rt_score.get('targeted', 0)}" + "</strong>"
            f"<em>{int(round((rt_score.get('ratio') or 0) * 100))}% of faults aimed at an existing rule</em></div>"
            '<div><span>blind spots</span><strong>' + str(rt_score.get("gaps", 0)) + "</strong>"
            "<em>faults no current rule could catch</em></div>"
            '<div><span>not representable</span><strong>' + str(rt_score.get("unverifiable", 0))
            + "</strong><em>needs data a netlist does not carry</em></div></div>"
            + "".join(
                f'<div class="item"><span class="tag {"ok" if f.get("status") == "caught" else "gap"}">'
                f'{html.escape(str(f.get("status")))}</span><div><h3>{html.escape(str(f.get("summary")))}</h3>'
                + (f'<p class="expect">caught by <b>{html.escape(", ".join(f.get("caught_by") or []))}</b></p>'
                   if f.get("caught_by") else "")
                + (f'<p>{html.escape(str(f.get("note")))}</p>' if f.get("note") else "")
                + "</div></div>"
                for f in rt.get("faults") or []
            )
        )

    pcb = document.get("pcb")
    pcb_html = ""
    if pcb:
        census = pcb.get("census") or {}
        pcb_html = (
            '<h2>Physical design · generated layout</h2>'
            f'<p class="meta">{census.get("footprints", 0)} footprints · {census.get("pads", 0)} pads · '
            f'{census.get("nets", 0)} nets · {census.get("segments", 0)} tracks · '
            f'{census.get("vias", 0)} vias · {census.get("width_mm", 0):g}×{census.get("height_mm", 0):g} mm</p>'
            '<div class="two"><div><h2>Layout verified</h2><ul class="plain chk">'
            + "".join(f"<li>{html.escape(str(v))}</li>" for v in pcb.get("verified") or [])
            + '</ul></div><div><h2>Layout not verified</h2><ul class="plain unk">'
            + "".join(f"<li>{html.escape(str(v))}</li>" for v in pcb.get("unverified") or [])
            + "</ul></div></div>"
        )

    svg = document.get("pcb_svg")
    if svg:
        pcb_html = (
            '<div class="boardwrap">' + svg
            + '<p class="note">Generated candidate board · '
            + html.escape(str((document.get("pcb") or {}).get("census", {}).get("width_mm", "")))
            + ' mm · footprints and pad-to-net mapping verified against the schematic. '
            "Not a fabrication release.</p></div>" + pcb_html
        )

    layout_rt = document.get("layout_redteam") or {}
    if (layout_rt.get("score") or {}).get("faults"):
        score = layout_rt["score"]
        pcb_html += (
            '<h2>Layout verifier · mutation test</h2>'
            '<div class="counters"><div><span>layout faults caught</span><strong>'
            + f"{score['caught']}/{score['faults']}" + "</strong><em>swapped nets, dropped parts, "
            "deleted tracks, nudged copper, shifted footprints</em></div>"
            '<div><span>layout blind spots</span><strong>' + str(score["gaps"]) + "</strong>"
            "<em>faults the physical check would miss</em></div>"
            '<div><span>verdict source</span><strong style="font-size:22px">engine</strong>'
            "<em>re-read from the .kicad_pcb file, not the generator</em></div></div>"
            + "".join(
                f'<div class="item"><span class="tag {"ok" if f.get("status") == "caught" else "gap"}">'
                f'{html.escape(str(f.get("status")))}</span><div><h3>{html.escape(str(f.get("summary")))}</h3>'
                + (f'<p class="expect">caught by <b>{html.escape(", ".join(f.get("caught_by") or []))}</b></p>'
                   if f.get("caught_by") else "")
                + "</div></div>"
                for f in layout_rt.get("faults") or []
            )
        )

    delta = document.get("delta")
    delta_html = ""
    if delta:
        delta_html = (
            '<h2>Change since previous revision</h2>'
            f'<p class="meta">{delta["base"]["errors"]} error(s) → {delta["head"]["errors"]} error(s) · '
            f'{delta["summary"]["introduced"]} introduced · {delta["summary"]["fixed"]} fixed · '
            f'{delta["summary"]["persisting"]} pre-existing</p>'
        )

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light">'
        "<title>BoardProof · Manufacturing Preflight Passport</title>"
        "<style>" + CSS + "</style></head><body><div class=\"sheet\">"
        "<header><div>"
        '<div class="brandline"><span class="mark">/</span>BoardProof</div>'
        "<h1>Manufacturing Preflight Passport</h1>"
        '<div class="meta">' + html.escape(str(document["revision"])) + " &nbsp;·&nbsp; netlist "
        + html.escape(Path(str(document["netlist"] or "")).name) + " &nbsp;·&nbsp; "
        + html.escape(str(document["generated_at"] or "")) + " &nbsp;·&nbsp; config "
        + html.escape(str(document["config"] or "-")) + "</div></div>"
        '<div class="stamp' + ("" if blocked else " clear") + '">'
        + ("BLOCKED" if blocked else "CLEARED") + "</div></header>"
        '<div class="counters">'
        '<div><span>checks passed</span><strong>' + str(counts["checks_passed"]) + "</strong>"
        "<em>approved cross-layer constraints that held</em></div>"
        '<div class="bad"><span>critical failures</span><strong>' + str(counts["critical"]) + "</strong>"
        "<em>must be fixed before fabrication</em></div>"
        '<div class="warn"><span>unverified</span><strong>' + str(counts["unverified"]) + "</strong>"
        "<em>outside this tool's scope</em></div></div>"
        "<h2>Critical failures</h2>" + failures + pcb_html + redteam + delta_html
        + '<div class="two"><div><h2>Verified by this run</h2><ul class="plain chk">' + verified_rows
        + '</ul></div><div><h2>Not verified — do not assume</h2><ul class="plain unk">'
        + unverified + "</ul></div></div>"
        "<h2>Rule packs of record</h2><table><thead><tr><th>pack</th><th>status</th>"
        "<th>vetted by</th><th>rules</th></tr></thead><tbody>" + packs + "</tbody></table>"
        '<div class="sign"><div><em>reviewed by</em><b>'
        + html.escape(reviewers or "no vetted pack")
        + '</b></div><div><em>tool</em><b>BoardProof deterministic engine · '
        + str(document["components"]) + " components · " + str(document["nets"]) + " nets</b></div>"
        '<div><em>passport hash</em><b class="hash">' + html.escape(document["passport_hash"][:32])
        + "</b></div></div>"
        '<p class="note">' + html.escape(str(document["note"]))
        + " A model proposed constraints and wrote prose; it did not compute this verdict."
        " Verify every limit against the authoritative datasheet for the exact part number,"
        " package and operating conditions.</p></div></body></html>"
    )


def _read_evidence(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def build_document(out_dir: Path, revision: str, *, report: dict | None = None,
                   config: Path | None = None, include_board: bool = True) -> dict:
    out_dir = Path(out_dir)
    report = report or _read_evidence(out_dir / "report.json")
    if report is None:
        raise ValueError("Run a circuit check before building a passport")

    def evidence(name: str) -> dict | None:
        data = _read_evidence(out_dir / name)
        if config is not None and data and data.get("config") != str(config):
            return None
        return data

    pcb = evidence("pcb-check.json") if include_board else None
    rules = evidence("redteam.json") if include_board else None
    layout = evidence("pcb-redteam.json") if include_board else None
    document = build(report, revision, None, rules)
    document["layout_redteam"] = layout
    if pcb:
        document["pcb"] = pcb
        svg = (out_dir / Path(pcb.get("svg") or "").name).resolve()
        if svg.parent == out_dir.resolve() and svg.is_file():
            document["pcb_svg"] = svg.read_text(encoding="utf-8")
            document["pcb"]["inline_svg"] = True
    return {"json": document, "html": render(document)}
