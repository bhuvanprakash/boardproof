"""HTML/JSON report.

The report is the pitch artifact: it has to prove, on one screen, that a model
touched this result without owning it.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .brand import FAVICON, mark
from .model import Design, Finding

CSS = """
:root{
  --bg:#f4f6f9; --bg2:#fafbfd; --surface:#ffffff; --surface2:#f4f6fa;
  --line:#e4e8ef; --line2:#d3dae4;
  --ink:#101a26; --ink2:#465266; --ink3:#6b7889; --ink4:#98a3b3;
  --teal:#0b7a5f; --teal-dim:#e8f6f1; --red:#c0282c; --red-dim:#fdeceb;
  --amber:#8a5a00; --amber-dim:#fbf1de; --blue:#1f5aa8; --blue-dim:#eaf1fb;
  --mono:ui-monospace,SFMono-Regular,SF Mono,Menlo,monospace;
  --sans:ui,-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
  --shadow:0 1px 2px rgba(16,26,38,.05),0 8px 24px -18px rgba(16,26,38,.35);
}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--ink);font:17px/1.6 var(--sans);-webkit-font-smoothing:antialiased;
  background-image:radial-gradient(760px 380px at 10% -8%,rgba(11,122,95,.07),transparent 62%),
                   radial-gradient(680px 340px at 92% -6%,rgba(31,90,168,.06),transparent 60%)}
main{max-width:1120px;margin:0 auto;padding:0 24px 92px}

.top{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:20px 0;
  border-bottom:1px solid var(--line);font-size:14px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3)}
.brand{display:flex;align-items:center;gap:10px;color:var(--ink);font-weight:700;letter-spacing:.04em;font-size:15px}
.logo{width:22px;height:22px;border-radius:6px;background:linear-gradient(140deg,#13997a,#0b6b55);
  color:#fff;display:grid;place-items:center;font-size:14px;font-weight:900;
  box-shadow:0 4px 12px -6px rgba(11,122,95,.8)}
.top .right{display:flex;gap:18px;font-family:var(--mono);letter-spacing:0;text-transform:none;font-size:13.5px;color:var(--ink3)}
.exit{color:var(--red);font-weight:600}
.exit.ok{color:var(--teal)}

.hero{display:grid;grid-template-columns:1fr auto;gap:32px;align-items:end;padding:54px 0 38px}
.eyebrow{font-family:var(--mono);font-size:13px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--ink3);margin:0 0 18px}
h1{font-size:clamp(36px,5.2vw,56px);line-height:1.03;letter-spacing:-.035em;margin:0;font-weight:800;color:#0b141f}
h1 .muted{color:#8d99a9}
.lede{color:var(--ink2);max-width:56ch;margin:18px 0 0;font-size:17.5px}
.pillrow{display:flex;flex-wrap:wrap;gap:8px;margin-top:24px}
.tag{font-family:var(--mono);font-size:13px;color:var(--ink2);background:var(--surface);
  border:1px solid var(--line2);border-radius:999px;padding:5px 11px;white-space:nowrap}
.tag b{color:var(--ink);font-weight:650}
.tag.teal{color:#0a6a52;border-color:#bfe3d7;background:var(--teal-dim)}
.tag.red{color:#a42226;border-color:#f0cdcd;background:var(--red-dim)}

.verdict{border:1px solid var(--line2);background:var(--surface);border-radius:18px;
  padding:22px 26px;min-width:190px;text-align:center;box-shadow:var(--shadow)}
.verdict .word{font-family:var(--mono);font-size:13.5px;letter-spacing:.22em;text-transform:uppercase;color:var(--ink3)}
.verdict .big{font-size:44px;font-weight:800;letter-spacing:-.03em;line-height:1.15;margin-top:4px}
.verdict.failed .big{color:var(--red)}
.verdict.passed .big{color:var(--teal)}
.verdict.failed{border-color:#f0cdcd;background:linear-gradient(180deg,#fef7f7,#fff)}
.verdict.passed{border-color:#bfe3d7;background:linear-gradient(180deg,#f4fdf9,#fff)}
.verdict .sub{font-family:var(--mono);font-size:13px;color:var(--ink3);margin-top:6px}

.chain{display:grid;grid-template-columns:repeat(3,1fr);gap:0;border:1px solid var(--line);
  border-radius:15px;overflow:hidden;background:var(--surface);margin:8px 0 0;box-shadow:var(--shadow)}
.stage{padding:17px 20px;position:relative}
.stage+.stage{border-left:1px solid var(--line)}
.stage .num{font-family:var(--mono);font-size:12.5px;letter-spacing:.16em;color:var(--ink4)}
.stage .name{font-weight:700;margin-top:6px;font-size:16.5px;letter-spacing:-.01em}
.stage .desc{color:var(--ink3);font-size:14.5px;margin-top:5px;line-height:1.5}
.stage.done .num{color:var(--teal)}
.stage.done .name{color:#0a6a52}
.stage .tick{position:absolute;top:15px;right:18px;color:var(--teal);font-size:14px;font-family:var(--mono)}
.stage.na .name,.stage.na .desc{color:var(--ink4)}

.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:12px 0 0}
.stat{border:1px solid var(--line);background:var(--surface);border-radius:13px;padding:15px 18px;box-shadow:var(--shadow)}
.stat span{display:block;font-family:var(--mono);font-size:12.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--ink3)}
.stat strong{display:block;font-size:28px;font-weight:750;letter-spacing:-.02em;margin-top:4px}
.stat.error strong{color:var(--red)}
.stat.warn strong{color:var(--amber)}

.head{display:flex;align-items:baseline;justify-content:space-between;gap:18px;margin:52px 0 16px;flex-wrap:wrap}
h2{font-size:14.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--ink2);margin:0;font-weight:700}
.head .hint{font-family:var(--mono);font-size:13px;color:var(--ink4)}
.filters{display:flex;gap:6px}
.filters button{font:13px var(--mono);letter-spacing:.06em;color:var(--ink3);background:var(--surface);
  border:1px solid var(--line2);border-radius:999px;padding:4px 11px;cursor:pointer}
.filters button:hover{color:var(--ink);border-color:#b9c3d0}
.filters button.on{background:#eef2f7;color:var(--ink);border-color:#b9c3d0}

.finding{display:grid;grid-template-columns:3px 1fr;border:1px solid var(--line);
  border-radius:14px;background:var(--surface);margin:10px 0;overflow:hidden;box-shadow:var(--shadow)}
.finding .bar{background:var(--red)}
.finding.warning .bar{background:var(--amber)}
.finding.info .bar{background:var(--blue)}
.fbody{padding:16px 20px 16px}
.fhead{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.sev{font-family:var(--mono);font-size:12px;letter-spacing:.14em;font-weight:700;padding:3px 8px;
  border-radius:5px;background:var(--red-dim);color:#a42226}
.sev.warning{background:var(--amber-dim);color:var(--amber)}
.sev.info{background:var(--blue-dim);color:var(--blue)}
.code{font-family:var(--mono);font-size:13px;letter-spacing:.08em;color:var(--ink2)}
.rid{font-family:var(--mono);font-size:12.5px;color:var(--ink4);margin-left:auto;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;max-width:46%}
.rlabel{font-family:var(--mono);font-size:12.5px;color:var(--ink4);margin-top:9px;
  letter-spacing:.03em;overflow-wrap:anywhere}
.finding h3{font-size:17.5px;font-weight:600;letter-spacing:-.01em;margin:10px 0 0;color:#131d29}

.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:13px}
.pair>div{background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.pair label{display:block;font-family:var(--mono);font-size:11.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--ink4);margin-bottom:4px}
.pair code{font-family:var(--mono);font-size:14.5px;word-break:break-word}
.pair .obs code{color:#a42226}
.pair .req code{color:#0a6a52}

.cite{display:grid;grid-template-columns:1fr;gap:8px;margin-top:12px}
.doc{position:relative;background:#f8fbff;border:1px solid #dce7f5;border-left:3px solid #4a86c8;
  border-radius:0 9px 9px 0;padding:12px 15px 12px 15px}
.doc q{display:block;font-size:15.5px;color:#22303f;font-style:italic;line-height:1.55}
.doc .src{font-family:var(--mono);font-size:12.5px;color:#1f5aa8;letter-spacing:.04em;margin-bottom:5px}
.who{font-family:var(--mono);font-size:12.5px;color:var(--ink4);padding-left:2px}
.who b{color:var(--ink2);font-weight:600}

.ai{position:relative;margin-top:12px;border:1px dashed #cdd8e6;border-radius:10px;
  padding:13px 15px;background:linear-gradient(180deg,#f7fafd,#fff)}
.ai .tagline{font-family:var(--mono);font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;
  color:#1f5aa8;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}
.ai .tagline em{font-style:normal;color:var(--ink4)}
.ai p{margin:9px 0 0;font-size:15.5px;color:#2b3947;line-height:1.6}
.ai p b{display:block;font-family:var(--mono);font-size:11.5px;letter-spacing:.14em;
  text-transform:uppercase;color:#1f5aa8;margin-bottom:3px;font-weight:700}
.ai .fix{color:#0a6a52}

details{margin-top:11px}
details summary{cursor:pointer;font-family:var(--mono);font-size:12.5px;color:var(--ink4);
  letter-spacing:.08em;text-transform:uppercase;list-style:none;display:inline-flex;
  align-items:center;gap:6px;white-space:nowrap;padding:2px 0}
details summary:before{content:'▸';color:var(--ink4);font-size:11px}
details[open] summary:before{content:'▾'}
details summary::-webkit-details-marker{display:none}
details summary:hover{color:var(--ink2)}
pre{overflow-x:auto;background:#f7f9fc;border:1px solid var(--line);border-radius:9px;
  padding:12px;font:13.5px/1.6 var(--mono);color:#33404f;margin:8px 0 0}

table{width:100%;border-collapse:collapse;font-size:14.5px;background:var(--surface);
  border:1px solid var(--line);border-radius:12px;overflow:hidden}
th{font-family:var(--mono);font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--ink3);text-align:left;padding:12px 12px 8px;background:var(--surface2);font-weight:600}
td{padding:11px 12px;border-top:1px solid var(--line);color:var(--ink2);vertical-align:top}
td.mono{font-family:var(--mono);font-size:13.5px;color:var(--ink3)}
td b{color:var(--ink);font-weight:650}
.dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--teal);margin-right:7px}
.dot.proposed{background:var(--amber)}
.dot.rejected{background:var(--red)}

.refuse{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.refuse>div{border:1px solid var(--line);background:var(--surface);border-radius:11px;padding:12px 14px;
  font-size:14.5px;color:var(--ink2);box-shadow:var(--shadow)}
.refuse code{font-family:var(--mono);font-size:12.5px;color:#a42226;display:block;margin-bottom:3px;letter-spacing:.04em}

.scope{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.scope>div{border:1px solid var(--line);background:var(--surface);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow)}
.scope span{display:block;font-family:var(--mono);font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;margin-bottom:8px}
.scope .ok span{color:var(--teal)}
.scope .no span{color:var(--amber)}
.scope ul{margin:0;padding:0;list-style:none}
.scope li{font-size:14.5px;color:var(--ink2);padding:3px 0 3px 16px;position:relative;line-height:1.5}
.scope .ok li:before{content:'✓';position:absolute;left:0;color:var(--teal);font-size:12px}
.scope .no li:before{content:'×';position:absolute;left:0;color:var(--amber);font-size:13px}
.scope em{font-style:normal;color:var(--ink4);font-family:var(--mono);font-size:13px}

.term{border:1px solid var(--line2);background:#fbfcfe;border-radius:11px;padding:14px 16px;
  font-family:var(--mono);font-size:14px;color:#22303f;overflow-x:auto;white-space:nowrap;
  display:flex;gap:10px;align-items:center;box-shadow:var(--shadow)}
.term .p{color:var(--teal);user-select:none;font-weight:700}
.term .cm{color:var(--ink4)}
.provenance{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:10px}
.provenance div{border:1px solid var(--line);background:var(--surface);border-radius:11px;padding:11px 13px;box-shadow:var(--shadow)}
.provenance span{display:block;font-family:var(--mono);font-size:11.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--ink4);margin-bottom:3px}
.provenance code{font-family:var(--mono);font-size:13.5px;color:#22303f;overflow-wrap:anywhere}

.empty{border:1px solid #bfe3d7;background:#f2fbf7;color:#0a6a52;padding:16px 18px;border-radius:12px}
footer{margin-top:60px;border-top:1px solid var(--line);padding-top:20px;color:var(--ink3);
  font-size:14px;display:grid;grid-template-columns:1fr auto;gap:18px;align-items:start}
footer b{color:var(--ink2);font-weight:650}
footer .legend{font-family:var(--mono);font-size:13px;text-align:right;line-height:1.9;color:var(--ink4)}
@media(max-width:840px){
  .hero{grid-template-columns:1fr;align-items:start}
  .chain{grid-template-columns:1fr}.stage+.stage{border-left:0;border-top:1px solid var(--line)}
  .stats{grid-template-columns:1fr 1fr}.pair{grid-template-columns:1fr}
  .refuse,.scope{grid-template-columns:1fr}footer{grid-template-columns:1fr}
  footer .legend{text-align:left}.rid{display:none}
  .term{white-space:normal;word-break:break-all;flex-wrap:wrap}
}
@media print{
  body{background:#fff;background-image:none}
  .finding,.stat,.chain,.table,table{box-shadow:none}
  .finding{break-inside:avoid}
}
"""

JS = """
document.querySelectorAll('[data-filter]').forEach(function(b){
  b.addEventListener('click',function(){
    document.querySelectorAll('[data-filter]').forEach(function(x){x.classList.remove('on')});
    b.classList.add('on');
    var want=b.getAttribute('data-filter');
    document.querySelectorAll('.finding').forEach(function(f){
      f.style.display=(want==='all'||f.getAttribute('data-sev')===want)?'':'none';
    });
  });
});
"""


def summary(design: Design, findings: list[Finding], meta: dict[str, Any] | None = None) -> dict:
    data: dict[str, Any] = {
        "tool": "BoardProof",
        "version": "0.2.0",
        "netlist": design.source,
        "components": len(design.components),
        "nets": len(design.nets),
        "counts": {x: sum(f.severity == x for f in findings) for x in ("error", "warning", "info")},
        "findings": [f.as_dict() for f in findings],
        "status": "failed" if any(f.severity == "error" for f in findings) else "passed",
    }
    if meta:
        data.update(meta)
    return data


def _num(value: Any, unit: str = "") -> str:
    if isinstance(value, (int, float)):
        return f"{value:g}{unit}"
    return "?"


def _pair(item: dict) -> tuple[str, str]:
    ev = item.get("evidence") or {}
    code = item.get("code")
    if code == "MAX_VOLTAGE":
        return (f"{_num(ev.get('voltage'), ' V')} on net {ev.get('net')}",
                f"{_num(ev.get('min_v'))} – {_num(ev.get('max_v'), ' V')}")
    if code == "PIN_NET":
        expected = ev.get("expected_nets") or []
        return (f"net {ev.get('observed_net') or '<unconnected>'}",
                " or ".join(str(e) for e in expected) or "?")
    if code == "CONNECTED":
        return "no net attached", "must be connected"
    if code == "RESISTOR_BETWEEN":
        hi = ev.get("max_ohms")
        return (f"none between {ev.get('net_a')} and {ev.get('net_b')}",
                f"{_num(ev.get('min_ohms'))} – " + ("∞" if hi is None else _num(hi)) + " Ω")
    if code == "FIRMWARE_GPIO":
        return (f"{ev.get('define')} = {_num(ev.get('firmware_gpio'))}  (firmware)",
                f"{ev.get('define')} = {_num(ev.get('schematic_gpio'))}  ({ev.get('component')}.{ev.get('pin')})")
    if code == "VOLTAGE_UNKNOWN":
        return f"net {ev.get('net') or '<unconnected>'} has no declared voltage", "declared voltage required"
    return "", ""


def _cite(item: dict) -> str:
    prov = (item.get("evidence") or {}).get("provenance") or {}
    cite = prov.get("citation") or {}
    if not cite:
        return ""
    loc = [f"p.{cite.get('page')}"]
    if cite.get("section"):
        loc.append(f"§{cite['section']}")
    if cite.get("table"):
        loc.append(f"Table {cite['table']}")
    who = []
    if prov.get("part"):
        who.append(html.escape(str(prov["part"])))
    if prov.get("pack_id"):
        who.append("pack " + html.escape(str(prov["pack_id"])))
    if prov.get("reviewed_by"):
        who.append("<b>vetted by " + html.escape(str(prov["reviewed_by"])) + "</b>")
    conf = cite.get("confidence")
    if isinstance(conf, (int, float)):
        who.append(f"extraction confidence {conf:.2f}")
    return (
        '<div class="cite"><div class="doc"><div class="src">'
        + html.escape(" · ".join(loc)) + "</div><q>"
        + html.escape(str(cite.get("quote", ""))) + "</q></div>"
        '<div class="who">' + " · ".join(who) + "</div></div>"
    )


def _ai(item: dict) -> str:
    expl = (item.get("evidence") or {}).get("explanation")
    if not expl:
        return ""
    blocks = []
    for key, label in (("plain_english", "What is wrong"),
                       ("likely_cause", "Most likely cause"),
                       ("suggested_fix", "Change this")):
        text = str(expl.get(key, "") or "").strip()
        if text:
            cls = ' class="fix"' if key == "suggested_fix" else ""
            blocks.append(f"<p{cls}><b>{label}</b>{html.escape(text)}</p>")
    if not blocks:
        return ""
    engine = html.escape(str(expl.get("engine", "model")))
    return ('<div class="ai"><div class="tagline"><span>explanation · ' + engine
            + '</span><em>read-only · cannot change the verdict</em></div>'
            + "".join(blocks) + "</div>")


LABEL = None


def _split_label(message: str) -> tuple[str, str]:
    import re as _re

    match = _re.match(r"^\[(.+?)\]\s*(.*)$", message, _re.S)
    if match:
        return match.group(1), match.group(2)
    return "", message


def _finding(item: dict) -> str:
    sev = str(item.get("severity", "info"))
    prov = (item.get("evidence") or {}).get("provenance") or {}
    observed, required = _pair(item)
    label, text = _split_label(str(item.get("message", "")))
    pair = ""
    if observed or required:
        pair = ('<div class="pair"><div class="obs"><label>observed</label><code>'
                + html.escape(observed) + '</code></div><div class="req"><label>required</label><code>'
                + html.escape(required) + "</code></div></div>")
    raw = {k: v for k, v in (item.get("evidence") or {}).items() if k != "explanation"}
    return (
        f'<article class="finding {html.escape(sev)}" data-sev="{html.escape(sev)}">'
        '<div class="bar"></div><div class="fbody">'
        '<div class="fhead"><span class="sev ' + html.escape(sev) + '">' + html.escape(sev.upper())
        + '</span><span class="code">' + html.escape(str(item.get("code"))) + "</span>"
        + ('<span class="rid">' + html.escape(str(prov.get("pack_id", ""))) + "</span>" if prov.get("pack_id") else "")
        + "</div>" + ('<div class="rlabel">' + html.escape(label) + "</div>"
                      if label and " " in label else "")
        + "<h3>" + html.escape(text) + "</h3>"
        + pair + _cite(item) + _ai(item)
        + '<details><summary>raw evidence</summary><pre>'
        + html.escape(json.dumps(raw, indent=2, ensure_ascii=False)) + "</pre></details>"
        + "</div></article>"
    )


def _ledger(packs: list[dict]) -> str:
    if not packs:
        return ('<p class="who">No rule packs loaded. Only inline rules configured in boardproof.json '
                "were enforced - no datasheet citation applies.</p>")
    rows = "".join(
        "<tr><td><span class=\"dot " + html.escape(str(p.get("status"))) + "\"></span><b>"
        + html.escape(str(p.get("id"))) + "</b></td><td class=\"mono\">"
        + html.escape(str(p.get("status"))) + "</td><td>"
        + html.escape(str(p.get("reviewed_by") or "—")) + "</td><td class=\"mono\">"
        + str(p.get("rules", 0)) + "</td><td class=\"mono\">"
        + html.escape(str(p.get("path", ""))) + "</td></tr>"
        for p in packs
    )
    return ('<table><thead><tr><th>pack</th><th>status</th><th>vetted by</th>'
            "<th>rules</th><th>source</th></tr></thead><tbody>" + rows + "</tbody></table>")


def write_reports(data: dict, output_json: Path | None, output_html: Path | None) -> None:
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not output_html:
        return
    output_html.parent.mkdir(parents=True, exist_ok=True)

    counts = data["counts"]
    failed = data["status"] == "failed"
    packs = data.get("packs") or []
    exit_code = data.get("exit_code", 1 if failed else 0)
    engine = data.get("explain_engine") or "not requested"
    reviewers = sorted({str(p.get("reviewed_by") or "") for p in packs} - {""})
    rules_enforced = sum(int(p.get("rules", 0)) for p in packs)
    cited = sum(1 for f in data["findings"]
                if ((f.get("evidence") or {}).get("provenance") or {}).get("citation"))

    plural = "" if counts["error"] == 1 else "s"
    headline = (f"{counts['error']} failure{plural}<br>"
                "<span class=\"muted\">a compiler cannot see.</span>"
                if failed else
                "This board<br><span class=\"muted\">survives review.</span>")
    lede = (
        f"{counts['error']} independent cross-artifact failure{plural}. "
        f"{'Each is' if counts['error'] == 1 else 'Each is'} traced to a datasheet page "
        "and to the engineer who accepted the rule. The verdict is deterministic; the prose is not the proof."
        if failed else
        "Every configured constraint held. The rules were proposed by a model, accepted by a human, and "
        "then enforced without a model in the loop."
    )
    tags = "".join(
        f'<span class="tag"><b>{html.escape(str(p.get("id")))}</b> · {html.escape(str(p.get("status")))}</span>'
        for p in packs
    ) or '<span class="tag">inline rules only</span>'
    tags += (f'<span class="tag teal">{len(reviewers)} reviewer'
             f'{"s" if len(reviewers) != 1 else ""} of record</span>' if reviewers else
             '<span class="tag">no vetted pack loaded</span>')
    if cited:
        tags += (f'<span class="tag"><b>{cited}</b> finding{"s" if cited != 1 else ""} backed by a '
                 "datasheet page</span>")
    tags += f'<span class="tag"><b>{html.escape(str(data.get("engine_requested") or "offline"))}</b> engine</span>'

    stages = (
        '<div class="chain">'
        '<div class="stage done"><div class="num">01 — extracted</div>'
        f'<div class="name">Model proposes</div><div class="desc">{rules_enforced} constraint(s) read '
        f'from a datasheet with a page quote each.</div><div class="tick">✓</div></div>'
        '<div class="stage ' + ("done" if reviewers else "na") + '"><div class="num">02 — vetted</div>'
        '<div class="name">' + (html.escape(", ".join(reviewers)) if reviewers else "no reviewer") + "</div>"
        '<div class="desc">' + (f"Accepted by name. Nothing below this line is model output."
                                if reviewers else "No pack has been promoted, so no datasheet rule runs.")
        + "</div><div class=\"tick\">" + ("✓" if reviewers else "·") + "</div></div>"
        '<div class="stage done"><div class="num">03 — enforced</div>'
        '<div class="name">Deterministic engine</div>'
        '<div class="desc">Same netlist in, same verdict out. No sampling, no temperature.</div>'
        '<div class="tick">✓</div></div></div>'
    )

    stats = "".join(
        f'<div class="stat {cls}"><span>{label}</span><strong>{value}</strong></div>'
        for label, value, cls in (
            ("components", data["components"], ""),
            ("nets", data["nets"], ""),
            ("errors", counts["error"], "error" if counts["error"] else ""),
            ("warnings", counts["warning"], "warn" if counts["warning"] else ""),
        )
    )

    rendered = "".join(_finding(item) for item in data["findings"])
    findings = rendered or (
        '<div class="empty"><b>No issues detected by the configured checks.</b><br>'
        "That is a statement about these rules, not a manufacturing certification.</div>"
        )
    filters = (
        '<div class="filters">'
        f'<button data-filter="all" class="on">all {len(data["findings"])}</button>'
        f'<button data-filter="error">errors {counts["error"]}</button>'
        f'<button data-filter="warning">warnings {counts["warning"]}</button>'
        "</div>"
    ) if len(data["findings"]) > 1 else ""

    by_type = data.get("verified_by_type") or {}
    scope_rows = [
        ("pin → net assignments", by_type.get("pin_net", 0)),
        ("supply / voltage limits", by_type.get("max_voltage", 0)),
        ("required connections", by_type.get("connected", 0)),
        ("pull-ups and resistor values", by_type.get("resistor_between", 0)),
        ("firmware pin contract", by_type.get("firmware_gpio", 0)),
    ]
    scope_ok = "".join(f"<li>{html.escape(label)} <em>×{count}</em></li>"
                       for label, count in scope_rows if count)
    scope_no = "".join(f"<li>{html.escape(str(item))}</li>"
                       for item in (data.get("unverified_scope") or []))
    scope_html = (
        '<div class="head"><h2>Verification scope</h2>'
        '<span class="hint">a pass is only as wide as this list</span></div>'
        '<div class="scope"><div class="ok"><span>checked by this run</span><ul>'
        + scope_ok + '</ul></div><div class="no"><span>not checked - do not assume</span><ul>'
        + scope_no + "</ul></div></div>"
    )

    refusals = [
        ("VOLTAGE_UNKNOWN", "A net has no declared voltage, so a rating cannot be confirmed."),
        ("MISSING_PIN", "The rule names a pin that is not in the exported netlist."),
        ("FW_UNKNOWN", "Macro missing or an expression this tool will not guess at."),
        ("GPIO_UNKNOWN", "Pin name carries no GPIO number, so nothing is inferred."),
        ("MCU_NET_AMBIGUOUS", "More than one pin on the net; refusing to pick one."),
        ("PACK_NOT_VETTED", "A model proposal tried to reach CI without a human reviewer."),
    ]
    refuse_html = "".join(
        f"<div><code>{html.escape(code)}</code>{html.escape(text)}</div>" for code, text in refusals
    )

    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light">'
        "<title>BoardProof — " + html.escape(str(data["status"])) + "</title>"
        "<style>" + CSS + "</style></head><body><main>"
        '<div class="top"><div class="brand"><span class="logo">/</span>BoardProof</div>'
        '<div class="right"><span>' + html.escape(str(data.get("generated_at", "")))
        + '</span><span class="exit' + ("" if failed else " ok") + '">exit ' + str(exit_code)
        + "</span></div></div>"
        '<section class="hero"><div><p class="eyebrow">hardware CI · easyeda pro netlist</p>'
        "<h1>" + headline + '</h1><p class="lede">' + lede + '</p>'
        '<div class="pillrow">' + tags + "</div></div>"
        '<div class="verdict ' + html.escape(str(data["status"])) + '">'
        '<div class="word">verdict</div><div class="big">'
        + ("FAILED" if failed else "PASSED") + "</div>"
        '<div class="sub">' + str(counts["error"]) + " err · " + str(counts["warning"]) + " warn</div></div>"
        "</section>" + stages + '<section class="stats">' + stats + "</section>"
        '<div class="head"><h2>Findings</h2>' + filters + "</div>" + findings
        + '<div class="head"><h2>Rule pack ledger</h2><span class="hint">'
        "who accepted which number</span></div>" + _ledger(packs)
        + scope_html
        + '<div class="head"><h2>Reproduce this verdict</h2>'
        '<span class="hint">same netlist in, same verdict out - on any machine</span></div>'
        '<div class="term"><span class="p">$</span><span>'
        + html.escape(str(data.get("command") or "boardproof check --config boardproof.json"))
        + '</span><span class="cm"># exit ' + str(exit_code) + "</span></div>"
        '<div class="provenance"><div><span>netlist</span><code>'
        + html.escape(Path(str(data.get("netlist", ""))).name) + " · sha256 "
        + html.escape(str(data.get("netlist_sha256") or "-")) + "</code></div>"
        '<div><span>config</span><code>' + html.escape(str(data.get("config") or "-"))
        + '</code></div><div><span>who decides</span><code>deterministic engine · '
        + html.escape(engine) + " only writes prose</code></div></div>"
        + '<div class="head"><h2>What this refuses to guess</h2>'
        '<span class="hint">an error, never a silent pass</span></div>'
        '<div class="refuse">' + refuse_html + "</div>"
        + "<footer><div><b>The verdict is deterministic; a model cannot change it.</b> "
        "Gemini reads datasheets and writes prose. It cannot introduce a rule, widen a citation set, "
        "or flip a result. Not a substitute for ERC, DRC, simulation, physical testing or sign-off."
        '<br><span class="hint">explanation engine: ' + html.escape(engine) + "</span></div>"
        '<div class="legend">exit 0 · pass<br>exit 1 · findings<br>exit 2 · cannot verify</div></footer>'
        "</main><script>" + JS + "</script></body></html>"
    )
    output_html.write_text(page, encoding="utf-8")
