"""One page that shows every artifact a judge, a reviewer or a buyer needs.

Reads only what BoardProof already wrote: reports, the passport, the red team
result, and a revision diff. Nothing is recomputed here.
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from .brand import FAVICON, icon, mark

CSS = """
:root{
  --bg:#f4f6f9;--surface:#fff;--surface2:#f4f6fa;--surface3:#eef2f7;--line:#e4e8ef;--line2:#d3dae4;
  --ink:#101a26;--ink2:#465266;--ink3:#5f6c7d;--ink4:#647085;
  --teal:#0b7a5f;--teal-soft:#e8f6f1;--red:#c0282c;--red-soft:#fdeceb;
  --amber:#8a5a00;--amber-soft:#fbf1de;--blue:#1f5aa8;--blue-soft:#eaf1fb;
  --mono:ui-monospace,SFMono-Regular,Menlo,monospace;
  --sans:ui-sans-serif,-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
  --shadow:0 1px 2px rgba(16,26,38,.05),0 10px 28px -22px rgba(16,26,38,.45);
  --ring:0 0 0 3px rgba(11,122,95,.25);
}
[data-theme="dark"]{
  --bg:#0b1119;--surface:#111a25;--surface2:#151f2c;--surface3:#1a2634;--line:#212f3f;--line2:#2c3d50;
  --ink:#e8f0fa;--ink2:#a7b6c9;--ink3:#93a3b6;--ink4:#8b9aae;
  --teal:#3fdcae;--teal-soft:#102a24;--red:#ff6b74;--red-soft:#2a1216;
  --amber:#ffc25c;--amber-soft:#2a2211;--blue:#7cb0ff;--blue-soft:#111d31;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 16px 40px -28px rgba(0,0,0,.9);
  --ring:0 0 0 3px rgba(63,220,174,.3);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:84px}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{animation:none!important;transition:none!important}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 var(--sans);-webkit-font-smoothing:antialiased}
:focus-visible{outline:0;box-shadow:var(--ring);border-radius:2px}
a{color:inherit}

.skip{position:absolute;left:12px;top:-48px;z-index:50;background:var(--ink);color:var(--bg);
  font:14px var(--mono);padding:9px 14px;border-radius:0 0 8px 8px;text-decoration:none;
  transition:top .15s}
.skip:focus{top:0}
.bar{position:sticky;top:0;z-index:20;backdrop-filter:blur(10px);
  background:color-mix(in srgb,var(--bg) 82%,transparent);border-bottom:1px solid var(--line)}
.barin{max-width:1120px;margin:0 auto;padding:12px 24px;display:flex;align-items:center;gap:18px}
.brand{display:flex;align-items:center;gap:9px;font-weight:750;letter-spacing:.02em;font-size:16px}
.logo{width:22px;height:22px;border-radius:6px;background:linear-gradient(140deg,#13997a,#0b6b55);
  display:grid;place-items:center;color:#fff;font-weight:900;font-size:14px}
.anchors{display:flex;gap:18px;margin-left:16px}
.anchors a{font:13.5px var(--sans);color:var(--ink3);text-decoration:none;padding:4px 0;
  border-bottom:2px solid transparent;border-radius:0}
.anchors a:hover{color:var(--ink);background:none;border-bottom-color:var(--ink)}
.barright{margin-left:auto;display:flex;align-items:center;gap:14px}
.pill{font:13px var(--sans);font-weight:650;letter-spacing:0;padding:0;border:0;border-radius:0;
  background:transparent;color:var(--ink2);white-space:nowrap}
.pill.bad{color:var(--red);background:none;border:0}
.pill.ok{color:var(--teal);background:none;border:0}
.pill.warn{color:var(--amber);background:none;border:0}
.iconbtn{width:28px;height:28px;border-radius:2px;border:1px solid var(--line2);background:transparent;
  color:var(--ink2);cursor:pointer;display:grid;place-items:center;font-size:15px}
.iconbtn:hover{color:var(--ink);border-color:var(--ink4)}

main{max-width:1120px;margin:0 auto;padding:0 24px 88px;overflow-x:clip}
.hero{padding:40px 0 28px;max-width:680px}
.kicker{font:13.5px var(--sans);color:var(--ink4);margin:0 0 14px;letter-spacing:-.01em}
h1{font-size:clamp(28px,3.6vw,40px);line-height:1.12;letter-spacing:-.03em;margin:0;font-weight:700}
h1 .muted{color:var(--ink3);font-weight:550}
.lede{color:var(--ink2);font-size:16.5px;margin:14px 0 0;max-width:58ch}
.lede2{color:var(--ink3);font-size:15px;margin:12px 0 0;max-width:54ch;line-height:1.5}
.status{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));
  border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.status>div{padding:14px 20px 16px 0;border-right:1px solid var(--line);min-width:0}
.status>div:last-child{border-right:0;padding-right:0}
.status span{display:block;font:12px var(--sans);color:var(--ink4);margin-bottom:6px}
.status strong{display:block;font:650 22px/1.15 var(--sans);letter-spacing:-.03em}
.status strong.ok{color:var(--teal)}.status strong.bad{color:var(--red)}.status strong.warn{color:var(--amber)}
.status em{display:block;font-style:normal;font:12.5px var(--mono);color:var(--ink3);margin-top:6px;
  overflow-wrap:anywhere}

section{scroll-margin-top:80px}
.head{display:flex;align-items:baseline;gap:14px;margin:40px 0 14px;flex-wrap:wrap}
h2{font:650 18px var(--sans);letter-spacing:-.02em;color:var(--ink);margin:0}
.head .hint{font:13.5px var(--sans);color:var(--ink4)}

.studio{border:0;background:transparent;border-radius:0;padding:4px 0 0}
.studio .row{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center}
select{font:14.5px var(--mono);color:var(--ink);background:transparent;border:0;
  border-bottom:1px solid var(--line2);border-radius:0;padding:8px 0;width:100%}
select:focus{box-shadow:none;border-bottom-color:var(--ink)}
.acts{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
button.act{display:inline-flex;align-items:center;gap:6px;font:13.5px var(--sans);font-weight:600;
  color:var(--ink2);background:none;border:0;border-radius:0;padding:7px 10px;cursor:pointer}
button.act:hover{color:var(--ink);background:var(--surface2)}
button.act:active{transform:none}
button.act .bp-icon{opacity:.75;flex:none}
button.act.icononly{padding:7px}
button.act.icononly span{display:none}
button.act.primary .bp-icon{opacity:1}
.brand .bp-mark{display:block}
button.act.primary{background:var(--teal);border:1px solid var(--teal);color:#fff;
  font-weight:650;border-radius:2px;padding:8px 16px}
button.act.primary:hover{filter:brightness(1.06);background:var(--teal);color:#fff}
button.act:disabled{opacity:.55;cursor:progress}
button.act kbd{font:12px var(--mono);opacity:.75;border:1px solid currentColor;border-radius:2px;
  padding:0 4px;line-height:1.5}
.hints{display:flex;gap:16px;flex-wrap:wrap;margin-top:11px;font:13px var(--mono);color:var(--ink4)}
.hints code{color:var(--ink3)}
.target{display:grid;grid-template-columns:56px 1fr;gap:12px;align-items:baseline}
.target label{font:12px var(--sans);color:var(--ink4)}
.targetmeta{font:12.5px var(--mono);color:var(--ink3);margin:6px 0 0 68px}
.actions{display:flex;flex-wrap:wrap;gap:10px 18px;margin-top:18px;align-items:center}
.primarywrap{display:flex;align-items:baseline;gap:10px}
.primarywrap small{font:12px var(--mono);color:var(--ink4);letter-spacing:.02em}
.secondary{display:flex;flex-wrap:wrap;gap:2px 0;align-items:center}
.grp{display:flex;gap:2px;align-items:center;padding-right:12px;margin-right:4px;
  border-right:1px solid var(--line)}
.grp:last-child{border-right:0;padding-right:0;margin-right:0}
.grplabel{font:11px var(--sans);color:var(--ink4);margin-right:4px}
.or{display:flex;align-items:center;gap:12px;margin:22px 0 10px;color:var(--ink4);
  font:12.5px var(--sans)}
.or:before,.or:after{content:'';height:1px;background:var(--line);flex:1}
.drop{display:flex;align-items:flex-start;gap:0;margin:0;border:1px dashed var(--line2);
  border-radius:2px;background:transparent;padding:14px 16px;color:var(--ink3);cursor:pointer}
.drop:hover,.drop.over{border-color:var(--teal);background:var(--teal-soft);color:var(--teal)}
.dropicon{display:none}
.drop>span{flex:1;text-align:left}
.drop b{display:block;color:var(--ink);font-weight:650;font-size:14.5px;letter-spacing:-.01em}
.drop small{display:block;font:12.5px var(--sans);margin-top:4px;color:var(--ink4)}
.how{margin-top:14px;font:13px var(--sans);color:var(--ink4)}
.how summary{cursor:pointer;color:var(--ink3);list-style:none;display:inline-flex;gap:6px;align-items:center}
.how summary:before{content:'▸';font-size:11px;color:var(--ink4)}
.how[open] summary:before{content:'▾'}
.how ul{margin:8px 0 0;padding-left:16px;line-height:1.7;font:13px var(--mono)}
.how li b{color:var(--ink2);font-weight:600}
.studio-idle{font:13px var(--mono);color:var(--ink4);margin-top:10px}
.upload-out{margin-top:12px;display:none;border:1px solid var(--line);border-radius:2px;
  background:var(--surface2);padding:13px 15px}
.upload-out.on{display:block}
.upload-out h4{margin:0 0 8px;font-size:15.5px}
.upload-out table{width:100%;border-collapse:collapse;font:13.5px var(--mono)}
.upload-out td{padding:4px 8px 4px 0;border-top:1px solid var(--line);color:var(--ink2);vertical-align:top}
.upload-out td:first-child{color:var(--ink);white-space:nowrap}
.upload-out .ok{color:var(--teal)}
.upload-out .miss{color:var(--amber)}
.briefwrap{display:block;margin-top:12px}
.briefwrap>span{display:block;font:12.5px var(--sans);color:var(--ink4);margin-bottom:6px}
.brief{width:100%;min-height:76px;border:1px solid var(--line);border-radius:2px;
  background:var(--surface);color:var(--ink);font:14.5px/1.45 var(--sans);padding:10px 12px;resize:vertical}
.dl{margin-top:10px;display:flex;flex-wrap:wrap;gap:12px 16px}
.dl a{color:var(--teal);font:13.5px var(--sans)}
#log{margin-top:12px;display:none;outline:none;border:1px solid var(--line);border-radius:2px;background:var(--surface2);
  padding:12px 14px;font:13.5px/1.7 var(--mono);color:var(--ink2);max-height:300px;overflow:auto}
#log.on{display:block}
#log .line{display:flex;gap:8px}
#log .ok{color:var(--teal)}#log .bad{color:var(--red)}#log .mut{color:var(--ink3)}
.steps{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.step{font:12px var(--mono);letter-spacing:.02em;color:var(--ink4);border:0;
  border-bottom:1px solid var(--line2);border-radius:0;padding:2px 0;background:none}
.step.done{color:var(--teal);border-color:color-mix(in srgb,var(--teal) 35%,transparent);background:var(--teal-soft)}
.step.bad{color:var(--red);border-color:color-mix(in srgb,var(--red) 35%,transparent);background:var(--red-soft)}
.spin{display:inline-block;width:9px;height:9px;border:2px solid var(--teal);border-right-color:transparent;
  border-radius:50%;animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}

.tools{display:flex;gap:4px 22px;flex-wrap:wrap;align-items:baseline;
  margin:0;padding:0 0 12px;border-bottom:1px solid var(--line)}
.chip{font:13.5px var(--sans);font-weight:600;color:var(--ink3);background:none;border:0;
  border-bottom:2px solid transparent;border-radius:0;padding:4px 0 10px;margin-bottom:-13px;
  cursor:pointer;letter-spacing:-.01em}
.chip:hover{color:var(--ink)}
.chip.on{background:none;color:var(--ink);border-bottom-color:var(--ink)}
#q{font:14px var(--sans);color:var(--ink);background:transparent;border:0;border-radius:0;
  padding:4px 0;min-width:140px;margin-left:auto;max-width:240px}
#q:focus{box-shadow:none;border-bottom:1px solid var(--ink)}
#q::placeholder{color:var(--ink4)}

.arows{border:0;background:transparent}
.agroup{display:flex;align-items:baseline;gap:12px;padding:22px 0 4px;background:transparent;
  font:13px var(--sans);color:var(--ink4)}
.agroup:first-child{padding-top:16px}
.agroup b{color:var(--ink);font-weight:650;letter-spacing:-.01em}
.arow{display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-rows:auto auto;
  column-gap:28px;row-gap:2px;align-items:baseline;padding:13px 0 13px 16px;
  border-top:1px solid var(--line);font-size:14.5px;color:var(--ink2);text-decoration:none;
  min-width:0;position:relative}
.arow:before{content:'';position:absolute;left:0;top:12px;bottom:12px;width:2px;background:var(--line2)}
.arow[data-verdict="ok"]:before{background:var(--teal)}
.arow[data-verdict="bad"]:before{background:var(--red)}
.arow[data-verdict="warn"]:before{background:var(--amber)}
.arow:hover{background:color-mix(in srgb,var(--surface2) 70%,transparent)}
.arow .akind{display:none}
.arow .atitle{grid-column:1;grid-row:1;font-weight:650;color:var(--ink);
  overflow-wrap:anywhere;line-height:1.3;letter-spacing:-.015em}
.arow .atitle em{font-style:normal;color:var(--ink3);font-weight:400}
.arow .averdict{grid-column:2;grid-row:1;font:13px var(--mono);letter-spacing:.01em;
  white-space:nowrap;justify-self:end}
.arow .averdict.ok{color:var(--teal)}
.arow .averdict.bad{color:var(--red)}
.arow .averdict.warn{color:var(--amber)}
.arow .ameta{grid-column:1;grid-row:2;font:12.5px var(--mono);color:var(--ink3);overflow-wrap:anywhere}
.arow .adelta{grid-column:2;grid-row:2;font:12.5px var(--mono);color:var(--ink4);
  justify-self:end;white-space:nowrap}
.arow .adelta.up{color:var(--teal)}
.arow .adelta.down{color:var(--red)}
.arow.empty-row{grid-template-columns:1fr;color:var(--ink3);padding-left:0}
.arow.empty-row:before{display:none}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;min-width:0}
a.card{position:relative;display:block;min-width:0;text-decoration:none;border:1px solid var(--line);
  background:var(--surface);border-radius:4px;padding:15px 17px 15px 19px;
  transition:border-color .15s}
a.card:before{content:'';position:absolute;left:0;top:14px;bottom:14px;width:3px;border-radius:3px;
  background:var(--line2)}
a.card[data-verdict="bad"]:before{background:var(--red)}
a.card[data-verdict="ok"]:before{background:var(--teal)}
a.card[data-verdict="warn"]:before{background:var(--amber)}
a.card:hover{border-color:var(--ink4)}
a.card:focus-visible{box-shadow:var(--ring)}
a.card .kind{font:12px var(--sans);color:var(--ink4)}
a.card h3{margin:7px 0 0;font-size:18px;font-weight:700;letter-spacing:-.01em;overflow-wrap:anywhere}
a.card p{margin:6px 0 0;font-size:14.5px;color:var(--ink2);overflow-wrap:anywhere}
a.card .row{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px;align-items:center}
a.card .go{margin-left:auto;font:13px var(--mono);color:var(--ink4)}
a.card:hover .go{color:var(--teal)}
.empty{color:var(--ink3);font-size:15px;border:1px dashed var(--line2);border-radius:2px;
  padding:14px 16px;background:transparent}
.empty code{font:14px var(--mono);color:var(--ink2);background:var(--surface2);padding:2px 6px;border-radius:5px}

.board{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);
  border:1px solid var(--line);background:var(--surface);border-radius:2px;overflow:hidden}
.boardleft{display:flex;flex-direction:column;min-width:0;position:relative}
.tblock{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr) minmax(0,1fr);
  border-top:1px solid var(--line);background:var(--surface)}
.tblock>div{padding:9px 14px;border-right:1px solid var(--line);min-width:0}
.tblock>div:last-child{border-right:0}
.tblock span{display:block;font:11px var(--sans);color:var(--ink4);margin-bottom:3px;white-space:nowrap}
.tblock strong{font:13px var(--mono);font-weight:600;color:var(--ink2);
  display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tblock .wide{grid-column:1/-1;border-top:1px solid var(--line);display:flex;
  justify-content:space-between;gap:18px;font:12px var(--sans);color:var(--ink4);
  white-space:nowrap;overflow:hidden}
.tblock .wide span{overflow:hidden;text-overflow:ellipsis}
.buildstamp{font:11.5px var(--mono);color:var(--ink4);letter-spacing:.04em}
.boardstage{position:relative;display:flex;align-items:center;justify-content:center;
  padding:28px 18px 18px;background:var(--surface2);min-height:540px;overflow:visible}
.boardstage a.zoomer,.boardstage div.zoomer{display:block;width:100%;max-width:640px}
.boardstage[data-view="3d"] .zoomer{max-width:none;height:480px}
.boardstage svg{width:100%;height:auto;display:block;overflow:visible}
.bp3d{width:100%;height:480px;touch-action:none;cursor:grab}
.bp3d:active{cursor:grabbing}
.bp3d-fallback{display:flex;align-items:center;justify-content:center;width:100%;height:480px}
.bp3d-fallback svg{max-height:100%;width:auto}
.spinhint{position:absolute;left:12px;bottom:10px;font:11px var(--sans);color:var(--ink4);pointer-events:none}
.pvbtn{font:11.5px var(--mono);color:#fff;background:var(--teal);border:1px solid var(--teal);
  border-radius:3px;padding:8px 14px;cursor:pointer;font-weight:600}
.pvbtn:hover{filter:brightness(1.06)}
dialog#bp-preview{border:1px solid var(--line2);border-radius:4px;padding:0;max-width:940px;
  width:calc(100% - 40px);background:var(--surface);color:var(--ink);box-shadow:0 40px 80px -40px #000}
dialog#bp-preview::backdrop{background:rgba(10,20,32,.55);backdrop-filter:blur(2px)}
.pvhead{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 18px;
  border-bottom:1px solid var(--line)}
.pvhead b{font-size:14px}
.pvhead button{background:none;border:0;color:var(--ink3);font-size:18px;cursor:pointer}
.pvtabs{display:flex;gap:2px;padding:0 12px;border-bottom:1px solid var(--line);background:var(--surface2)}
.pvtabs button{font:13px var(--sans);font-weight:600;letter-spacing:-.01em;color:var(--ink3);
  background:none;border:0;border-bottom:2px solid transparent;padding:10px 12px;cursor:pointer}
.pvtabs button.on{color:var(--ink);border-bottom-color:var(--ink)}
.pvbody{padding:16px 18px;max-height:62vh;overflow:auto;background:var(--surface2)}
.pvbody img{width:100%;border:1px solid var(--line2);background:#fff;border-radius:2px}
.pvfoot{display:flex;gap:8px;flex-wrap:wrap;padding:12px 18px;border-top:1px solid var(--line)}
.viewbar{display:flex;align-items:center;justify-content:space-between;gap:12px;
  padding:9px 14px;background:var(--surface);border-bottom:1px solid var(--line);
  position:sticky;top:52px;z-index:4}
.viewlabel{font:12px var(--sans);color:var(--ink3)}
.dlrow{display:flex;flex-wrap:wrap;gap:8px;padding:10px 14px;border-top:1px solid var(--line);
  background:var(--surface)}
.dl{font:12px var(--mono);text-decoration:none;color:var(--ink2);border:1px solid var(--line2);
  border-radius:3px;padding:5px 10px;display:inline-flex;gap:6px;align-items:center}
.dl:hover{color:var(--teal);border-color:var(--teal)}
.viewtoggle{display:flex;gap:0;
  border:1px solid var(--line2);border-radius:2px;overflow:hidden;background:var(--surface);flex:none}
.viewtoggle .vt{font:13px var(--sans);font-weight:600;padding:7px 16px;border:0;
  background:transparent;color:var(--ink3);cursor:pointer;min-width:52px}
.viewtoggle .vt.on{background:var(--ink);color:var(--bg)}
.viewtoggle .vt:hover:not(.on){color:var(--ink);background:var(--surface2)}
.boardstage a:focus-visible{box-shadow:var(--ring)}
.viewtag{position:absolute;right:12px;top:10px;font:12px var(--sans);color:var(--ink4)}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font:12.5px var(--mono);color:var(--ink3)}
.legend b{color:var(--ink2);font-weight:600}
.legend em{font-style:normal;color:var(--ink4)}
.stamp-flag{font:650 13px var(--sans);letter-spacing:0;
  padding:0;border-radius:0;background:none;color:var(--teal);white-space:nowrap}
.stamp-flag.bad{background:none;color:var(--red)}
.stagefoot{position:absolute;right:12px;bottom:10px;font:12px var(--mono);color:var(--ink4);
  letter-spacing:.03em}
.boardmeta{padding:24px 26px 22px;display:flex;flex-direction:column;gap:18px;
  border-left:1px solid var(--line)}
.eyebrow2{font:12px var(--sans);color:var(--ink4);
  display:flex;align-items:center;gap:10px}
.eyebrow2:after{content:'';flex:1;height:1px;background:var(--line)}
.statusline{display:flex;align-items:flex-start;gap:12px;margin-top:-6px}
.statusline h3{margin:0;font-size:22px;line-height:1.2;letter-spacing:-.025em;font-weight:700}
.statusline h3.ok{color:var(--teal)}
.statusline h3.bad{color:var(--red)}
.statusline p{margin:2px 0 0;font-size:14.5px;color:var(--ink2)}
.specs{display:flex;flex-direction:column;border-top:1px solid var(--line)}
.specs div{display:flex;justify-content:space-between;align-items:baseline;gap:16px;
  padding:9px 0;border-bottom:1px solid var(--line)}
.specs span{font:12px var(--sans);color:var(--ink4)}
.specs strong{font:15px var(--mono);font-weight:600;letter-spacing:-.01em;text-align:right}
.tags{display:flex;flex-wrap:wrap;gap:6px}
.tagx{font:12.5px var(--mono);letter-spacing:.02em;color:var(--ink2);border:1px solid var(--line2);
  padding:4px 8px;border-radius:2px}
.tagx.ok{color:var(--teal);border-color:color-mix(in srgb,var(--teal) 38%,transparent)}
.tagx.warn{color:var(--amber);border-color:color-mix(in srgb,var(--amber) 38%,transparent)}
.checks{display:grid;grid-template-columns:1fr 1fr;gap:0 18px}
.checkgrp{display:flex;flex-direction:column;grid-column:span 2}
.checkgrp.two{grid-column:span 2;display:grid;grid-template-columns:1fr 1fr;gap:0 18px}
.checkgrp .gl{font:12px var(--sans);letter-spacing:-.01em;color:var(--ink4);
  padding-bottom:6px;border-bottom:1px solid var(--line);margin-bottom:6px;grid-column:span 2}
.chk{font-size:14px;color:var(--ink2);padding:2px 0 2px 14px;position:relative;line-height:1.45}
.chk:before{content:'✓';position:absolute;left:0;top:2px;color:var(--teal);font-size:11px}
.more{font:12.5px var(--mono);color:var(--ink4);padding-left:14px;grid-column:span 2}
.scope{font-size:13.5px;color:var(--ink3);border-top:1px solid var(--line);padding-top:10px;
  line-height:1.55}
.scope b{color:var(--ink);font-weight:650;font-family:var(--sans);font-size:13px;
  letter-spacing:-.01em;display:block;margin-bottom:4px}
.boardlinks{display:flex;gap:16px;flex-wrap:wrap;margin-top:auto;padding-top:4px}
.boardlinks a{font:13.5px var(--mono);text-decoration:none;color:var(--ink2);
  border-bottom:1px solid var(--line2);padding-bottom:2px;display:inline-flex;gap:6px;align-items:center}
.boardlinks a:hover{color:var(--teal);border-color:var(--teal)}
.thumbs{display:flex;gap:6px;flex-wrap:wrap}
.thumb{width:60px;height:44px;border:1px solid var(--line2);border-radius:2px;background:var(--surface2);
  padding:3px;cursor:pointer;overflow:hidden;display:grid;place-items:center}
.thumb svg{width:100%;height:100%}
.thumb.on{border-color:var(--teal)}
.thumblabel{font:11px var(--mono);color:var(--ink4);text-align:center;margin-top:2px}
.flow{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:0 28px;
  padding:18px 0 4px;border-top:1px solid var(--line);background:transparent}
.wstep{padding:0;min-width:0}
.wstep .wn{display:block;font:11px var(--mono);color:var(--ink4);margin-bottom:8px;letter-spacing:.04em}
.wstep b{display:block;font:600 15px var(--sans);letter-spacing:-.02em;color:var(--ink);margin:0 0 5px}
.wstep span{font-size:13.5px;color:var(--ink3);line-height:1.45;display:block}
.wstep em{display:block;font-style:normal;font:12px var(--mono);color:var(--ink4);margin-top:10px}
footer{margin-top:48px;border-top:1px solid var(--line);padding-top:18px;color:var(--ink3);font-size:14px}
footer b{color:var(--ink2)}
#toast{position:fixed;left:50%;bottom:26px;transform:translate(-50%,20px);opacity:0;pointer-events:none;
  background:var(--ink);color:var(--bg);font:14px var(--mono);padding:10px 16px;border-radius:2px;
  transition:opacity .2s,transform .2s;z-index:40;box-shadow:var(--shadow)}
#toast.on{opacity:1;transform:translate(-50%,0)}
@media(max-width:860px){.board{grid-template-columns:1fr}
  .boardmeta{border-left:0;border-top:1px solid var(--line)}
  .status{grid-template-columns:1fr 1fr}
  .status>div{border-bottom:1px solid var(--line);padding:12px 16px 14px 0}
  .status>div:nth-child(2n){border-right:0;padding-right:0}
  .status>div:nth-last-child(-n+2){border-bottom:0}
  .targetmeta{margin-left:0}.grid{grid-template-columns:1fr}
  .flow{grid-template-columns:1fr;gap:0}.wstep{padding:14px 0;border-top:1px solid var(--line)}
  .wstep:first-child{border-top:0}.anchors{display:none}.barin{padding:10px 16px}main{padding:0 16px 72px}}
"""

FLOW = [
    ("1", "Export", "EasyEDA Pro netlist", "boardproof init"),
    ("2", "Propose", "Gemini reads the datasheet", "boardproof infer"),
    ("3", "Vet", "A person signs each number", "boardproof vet"),
    ("4", "Enforce", "Deterministic CI on the PR", "boardproof check"),
    ("5", "Prove", "Faults injected, scope named", "boardproof redteam"),
]


def collect(directory: Path) -> dict:
    reports, passport, redteam, diffs, redteams = [], None, None, [], []
    designs, pcb_checks = [], []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        page = path.with_suffix(".html")
        if data.get("kind") == "manufacturing-preflight-passport":
            passport = (path, data)
        elif "faults" in data and "score" in data:
            redteams.append((path, data))
            if "targeted" in (data.get("score") or {}) or redteam is None:
                redteam = (path, data)
        elif data.get("kind") == "design":
            designs.append((path, data))
        elif data.get("kind") == "pcb-check":
            pcb_checks.append((path, data))
        elif {"introduced", "regressed"} <= set(data):
            diffs.append((path, data))
        elif data.get("tool") == "BoardProof" and "findings" in data:
            reports.append((path, data))
    boards: list[dict] = []
    for path in sorted(directory.glob("*.svg"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            markup = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "<svg" not in markup:
            continue
        check = next((data for _, data in pcb_checks
                      if Path(str(data.get("svg") or "").split("/")[-1]).name
                      in {path.name, path.stem + "-3d.svg"}), None)
        model = path.with_name(path.stem + "-model.json")
        three_d = path.with_name(path.stem + "-3d.svg")
        boards.append({"file": path.name, "dir": str(directory), "svg": markup,
                       "svg3d": three_d.read_text(encoding="utf-8") if three_d.is_file() else "",
                       "model": (model.read_text(encoding="utf-8").strip()
                                 if model.is_file() else ""),
                       "html": path.with_suffix(".html").name if path.with_suffix(".html").exists() else None,
                       "check": check})
    # an isometric sibling is never a board in its own right
    boards = [b for b in boards if not b["file"].endswith("-3d.svg")]
    demo = [b for b in boards if b["file"].lower().startswith("jeden")]
    boards = demo + [b for b in boards if b not in demo]
    previews = {"schematic": "", "datasheets": []}
    preview_dir = directory / "preview"
    if preview_dir.is_dir():
        schematic = preview_dir / "schematic.svg"
        if schematic.is_file():
            previews["schematic"] = schematic.read_text(encoding="utf-8")
        for image in sorted(preview_dir.glob("datasheet-*.png")):
            previews["datasheets"].append({"file": f"preview/{image.name}",
                                           "label": image.stem.replace("datasheet-", "")
                                                    .replace("-", " ").upper()})
    return {"reports": reports, "passport": passport, "redteam": redteam, "redteams": redteams,
            "previews": previews,
            "diffs": diffs, "designs": designs, "pcb_checks": pcb_checks, "boards": boards,
            "html": sorted(p.name for p in directory.glob("*.html"))}


def _pretty(stem: str) -> str:
    """tmp102-5v -> TMP102 · 5V, broken -> Broken."""
    import re as _re

    words = []
    for token in _re.split(r"[-_.]+", stem):
        if not token:
            continue
        words.append(token.upper() if _re.search(r"[0-9]", token) and _re.search(r"[A-Za-z]", token)
                     else token.capitalize())
    return " · ".join(words) or stem


def _status_pill(item: dict) -> str:
    status = str(item.get("status") or "")
    cls = "bad" if status in {"failed", "blocked"} else "ok" if status in {"passed", "cleared"} else ""
    counts = item.get("counts") or {}
    if "critical" in counts:
        tail = f"{counts['critical']} critical"
    else:
        tail = f"{counts.get('error', '?')} error(s)"
    return f'<span class="pill {cls}">{html.escape(status or "report")} · {tail}</span>'


STUDIO_JS = """
function chipsFor(action) {
  const map = {
    prove: ['check', 'design', 'pcb-check', 'red-team', 'layout-red-team', 'passport'],
    check: ['check'], design: ['design'], pcb: ['pcb-check'],
    redteam: ['red-team'], passport: ['passport'], refresh: ['refresh']
  };
  return map[action] || [action];
}

const sel = document.getElementById('cfg');
if (sel) sel.addEventListener('change', function () {
  const index = sel.selectedIndex;
  document.querySelectorAll('[data-meta]').forEach(function (el) {
    el.style.display = el.getAttribute('data-meta') === String(index) ? '' : 'none';
  });
});
const logEl = document.getElementById('log');
const btns = [...document.querySelectorAll('button.act')];
function write(line, cls) {
  const span = document.createElement('div');
  if (cls) span.className = cls;
  span.textContent = line;
  logEl.appendChild(span);
  logEl.scrollTop = logEl.scrollHeight;
}
async function run(action) {
  const cfg = sel ? sel.value : '';
  if (!cfg && action !== 'refresh') { alert('Pick a configuration first'); return; }
  logEl.classList.add('on');
  logEl.textContent = '';
  logEl.setAttribute('aria-busy', 'true');
  const chips = document.getElementById('steps');
  if (chips) {
    chips.innerHTML = '';
    chipsFor(action).forEach(name => {
      const el = document.createElement('span');
      el.className = 'step';
      el.textContent = name;
      chips.appendChild(el);
    });
  }
  const box = document.createElement('div');
  box.className = 'line';
  box.innerHTML = '<span class="spin"></span><span class="mut">running ' + action + ' …</span>';
  logEl.appendChild(box);
  btns.forEach(b => b.disabled = true);
  try {
    const res = await fetch('/api/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json',
                'X-BoardProof-Token': (window.BP_TOKEN || '')},
      body: JSON.stringify({action, config: cfg})
    });
    const data = await res.json();
    logEl.textContent = '';
    const marks = [].slice.call(document.querySelectorAll('#steps .step'));
    (data.log || []).forEach((line, i) => {
      write(line, data.ok ? 'ok' : 'bad');
      if (marks[i]) {
        const failed = /FAIL|BLOCK|REFUS|ERROR|GAP/i.test(line);
        marks[i].className = 'step ' + (failed ? 'bad' : 'done');
      }
    });
    marks.forEach(m => { if (m.className === 'step') m.className = 'step done'; });
    write('— ' + (data.seconds ?? '?') + 's · exit ' + data.code, data.ok ? 'ok' : 'bad');
    logEl.setAttribute('aria-busy', 'false');
    logEl.focus();
    if (window.bpToast) bpToast(data.ok ? action + ' finished in ' + data.seconds + 's'
                                        : action + ' blocked (exit ' + data.code + ')', !data.ok);
    if (data.ok) setTimeout(() => location.reload(), 1100);
  } catch (err) {
    logEl.textContent = '';
    write('Cannot reach the studio: ' + err, 'bad');
    write('Start it with:  boardproof studio --dir artifacts', 'bad');
    logEl.setAttribute('aria-busy', 'false');
    if (window.bpToast) bpToast('studio not reachable', true);
  } finally {
    btns.forEach(b => b.disabled = false);
  }
}
document.querySelectorAll('button.act').forEach(b =>
  b.addEventListener('click', () => { if (b.dataset.action) run(b.dataset.action); }));

const drop = document.getElementById('drop');
const fileInput = document.getElementById('file');
const out = document.getElementById('upload-out');
async function upload(file) {
  const briefEl = document.getElementById('brief');
  const brief = (briefEl && briefEl.value) || '';
  if (!file && !brief.trim()) return;
  out.classList.add('on');
  const label = file ? file.name : 'brief';
  out.innerHTML = '<h4><span class="spin"></span>reading ' + label + '…</h4>';
  try {
    const isBin = file && /\\.(png|jpe?g|webp|gif)$/i.test(file.name);
    let content = '';
    let content_b64 = '';
    if (file && isBin) {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let bin = '';
      for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
      content_b64 = btoa(bin);
    } else if (file) {
      content = await file.text();
    }
    const kind = isBin ? 'photo' : (file ? '' : 'brief');
    const res = await fetch('/api/upload', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-BoardProof-Token': (window.BP_TOKEN || '')},
      body: JSON.stringify({filename: file ? file.name : 'brief.txt', content, content_b64, brief, kind})
    });
    const data = await res.json();
    if (!data.ok) {
      out.innerHTML = '<h4>Upload rejected</h4><div class="miss">' +
        (data.log || []).map(l => '<div>' + l + '</div>').join('') + '</div>';
      return;
    }
    const rows = (data.parts || []).map(p =>
      '<tr><td>' + p.part + '</td><td>' + (p.refs || []).join(', ') + '</td><td>' +
      (p.document ? '<span class="ok">datasheet ' + p.status + '</span> · ' + (p.sha256 || '')
                  : '<span class="miss">no datasheet: ' + (p.error || 'unknown') + '</span>') +
      '</td></tr>').join('');
    const title = (data.board || data.netlist || label) +
      (data.components ? ' — ' + data.components + ' components, ' +
        data.nets + ' nets, ' + data.pins + ' pins' : '');
    const dl = (data.downloads || []).map(d =>
      '<a href="' + d.file + '" download>' + d.label + '</a>').join('');
    out.innerHTML = '<h4>' + title + '</h4>' +
      (rows ? '<table>' + rows + '</table>' : '') +
      (data.config ? '<div class="hint" style="margin-top:10px">draft config: <b>' + data.config +
        '</b> · ' + data.draft_rules + ' rule(s) at severity=warning · ' + data.blocking +
        ' blocking, ' + data.warnings + ' warning(s)</div>' : '') +
      (dl ? '<div class="dl">' + dl + '</div>' : '') +
      '<div class="hint">' + (data.log || []).concat(data.next || []).join('<br>') + '</div>';
    if (window.bpToast) bpToast('uploaded ' + label, false);
  } catch (err) {
    out.innerHTML = '<h4>Upload failed</h4><div class="miss">' + err + '</div>';
  }
}
if (drop && fileInput) {
  drop.addEventListener('click', () => fileInput.click());
  drop.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });
  fileInput.addEventListener('change', () => {
    [...fileInput.files].forEach(f => upload(f));
  });
  ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => {
    e.preventDefault(); drop.classList.add('over');
  }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => {
    e.preventDefault(); drop.classList.remove('over');
  }));
  drop.addEventListener('drop', e => {
    [...e.dataTransfer.files].forEach(f => upload(f));
  });
}
const briefGo = document.getElementById('brief-go');
if (briefGo) briefGo.addEventListener('click', () => upload(null));
"""


def _studio_panel(configs: list[dict], read_only: bool = False) -> str:
    if not configs:
        return ("<div class=\"studio\"><div class=\"hint\">No boardproof.json found in this "
                "workspace. Add one, or run <code>boardproof init --netlist board.enet</code>."
                "</div></div>")
    if read_only:
        return ('<div class="studio"><div class="studio-idle">'
                "This studio is read-only: the board, reports and passport are live, "
                "but actions are refused by the server.</div></div>")

    options = []
    meta = []
    for index, config in enumerate(configs):
        path = html.escape(config["path"])
        options.append("<option value=\"" + path + "\">" + path + "</option>")
        chips = [config.get("netlist") or "netlist",
                 str(config["rules"]) + " rule" + ("" if config["rules"] == 1 else "s"),
                 str(config["packs"]) + " pack" + ("" if config["packs"] == 1 else "s")]
        if config.get("packages"):
            n = config["packages"]
            chips.append(str(n) + " package spec" + ("" if n == 1 else "s"))
        meta.append('<div class="targetmeta" data-meta="' + str(index) + '"' +
                    ("" if index == 0 else ' style="display:none"') + ">" +
                    html.escape(" · ".join(str(chip) for chip in chips)) + "</div>")

    def button(action: str, label: str, title: str, primary: bool = False) -> str:
        cls = "act primary" if primary else "act"
        glyph = {"check": "check", "design": "design", "pcb": "pcb", "redteam": "redteam",
                 "passport": "passport", "refresh": "refresh", "prove": "prove"}.get(action, "")
        return ('<button class="' + cls + '" data-action="' + action + '" title="' +
                html.escape(title) + '">' + icon(glyph) + "<span>" + label + "</span></button>")

    groups = [
        ("Circuit", [("check", "Check", "deterministic checks on this configuration")]),
        ("Layout", [("design", "Generate board", "editable .kicad_pcb plus preview"),
                    ("pcb", "Verify board", "re-read the board file and prove it")]),
        ("Evidence", [("redteam", "Red team", "inject faults, score the rule set"),
                      ("passport", "Passport", "rebuild the preflight passport")]),
    ]
    secondary = "".join(
        '<div class="grp"><span class="grplabel">' + name + "</span>" + "".join(
            button(action, label, title) for action, label, title in items) + "</div>"
        for name, items in groups
    )
    secondary += ('<div class="grp">'
                  '<button class="act icononly" data-action="refresh" '
                  'title="rescan the artifacts directory" aria-label="Refresh artifacts">'
                  + icon("refresh") + "</button></div>")

    return (
        '<div class="studio">'
        '<div class="target"><label for="cfg">Target</label><select id="cfg">'
        + "".join(options) + "</select></div>"
        + "".join(meta) +
        '<div class="actions"><div class="primarywrap">'
        + button("prove", "Prove it", "check, design, pcb-check, red team, passport",
                 primary=True)
        + "<small>Cmd + Enter</small></div>"
        '<div class="secondary">' + secondary + "</div></div>"
        '<div class="steps" id="steps"></div>'
        '<div id="log" tabindex="-1" aria-live="polite" aria-label="Run output"></div>'
        '<div class="or">Or a board you already have</div>'
        '<div class="drop" id="drop" tabindex="0" role="button">'
        "<span>"
        "<b>Drop a layout, schematic, netlist or design photo</b>"
        "<small>Gemini reads a brief or photo into a netlist. "
        "BoardProof places a new board and writes KiCad + Gerbers. "
        "The Jeden Uno on this page is the demo preview only.</small>"
        "</span><input type=\"file\" id=\"file\" accept=\".enet,.json,.kicad_pcb,.kicad_sch,.txt,.md,image/*\" multiple hidden></div>"
        '<label class="briefwrap"><span>Or write what you are making</span>'
        '<textarea id="brief" class="brief" rows="3" '
        'placeholder="Arduino Uno clone with ATmega328P, USB-B, 16 MHz crystal…"></textarea></label>'
        '<button type="button" class="act" id="brief-go" style="margin-top:8px">Build layout and Gerbers</button>'
        '<div class="upload-out" id="upload-out"></div>'
        '<details class="how"><summary>How this runs</summary><ul>'
        "<li>Every button calls a <b>function in this process</b> — no shell, no arguments "
        "from the browser.</li>"
        "<li>Configurations are discovered under <b>--root</b>; a request naming a path outside "
        "it is refused.</li>"
        "<li>Actions are serialised behind a lock, and can be gated with <b>--token</b> or "
        "switched off with <b>--read-only</b>.</li>"
        "<li>Opened as a plain file this panel is inert: run "
        "<b>boardproof studio --dir artifacts</b> to use it.</li>"
        "</ul></details></div>"
    )


PAGE_JS = """
(function () {
  var root = document.documentElement;
  var saved = null;
  try { saved = localStorage.getItem('bp-theme'); } catch (e) {}
  root.setAttribute('data-theme', saved === 'dark' ? 'dark' : 'light');
  var themeBtn = document.getElementById('theme');
  if (themeBtn) themeBtn.addEventListener('click', function () {
    var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('bp-theme', next); } catch (e) {}
  });

  var cards = [].slice.call(document.querySelectorAll('.arow[data-kind]'));
  cards.forEach(function (card) {
    if (card.getAttribute('data-verdict')) return;
    var verdict = card.querySelector('.averdict');
    var text = verdict ? verdict.textContent.toLowerCase() : '';
    card.setAttribute('data-verdict',
      text.indexOf('fail') >= 0 || text.indexOf('block') >= 0 || text.indexOf('regress') >= 0
        ? 'bad' : (text.indexOf('pass') >= 0 || text.indexOf('clear') >= 0 ? 'ok' : 'warn'));
  });

  var chips = [].slice.call(document.querySelectorAll('.chip[data-kind]'));
  var query = document.getElementById('q');
  var count = document.getElementById('count');
  var active = 'all';
  function apply() {
    var term = (query && query.value || '').toLowerCase();
    var shown = 0;
    cards.forEach(function (card) {
      var okKind = active === 'all' || card.getAttribute('data-kind') === active;
      var okText = !term || card.textContent.toLowerCase().indexOf(term) >= 0;
      var visible = okKind && okText;
      card.style.display = visible ? '' : 'none';
      if (visible) shown++;
    });
    document.querySelectorAll('.agroup').forEach(function (g) {
      var next = g.nextElementSibling, any = false;
      while (next && !next.classList.contains('agroup')) {
        if (next.classList.contains('arow') && next.style.display !== 'none') any = true;
        next = next.nextElementSibling;
      }
      g.style.display = any ? '' : 'none';
    });
    if (count) count.textContent = shown + (shown === 1 ? ' file' : ' files');
  }
  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      chips.forEach(function (c) { c.classList.remove('on'); });
      chip.classList.add('on');
      active = chip.getAttribute('data-kind');
      apply();
    });
  });
  if (query) query.addEventListener('input', apply);

  var toast = document.getElementById('toast');
  window.bpToast = function (message, bad) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.toggle('on', true);
    toast.style.background = bad ? '#a42226' : '';
    setTimeout(function () { toast.classList.remove('on'); }, 2600);
  };

  document.addEventListener('keydown', function (event) {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      var prove = document.querySelector('button.act.primary');
      if (prove) { event.preventDefault(); prove.click(); }
    }
  });
})();
"""


def _dedupe_checks(checks: list[str]) -> list[str]:
    """Drop parentheticals and near-duplicates ("pad-to-net assignment" twice)."""
    out: list[str] = []
    for item in checks:
        text = str(item).strip()
        short = text.split("(")[0].strip().rstrip(".")
        if not short:
            continue
        low = short.lower()
        duplicate = False
        for existing in out:
            other = existing.lower()
            if low == other or low.startswith(other) or other.startswith(low):
                duplicate = True
                break
        if not duplicate:
            out.append(short)
    return out


def _categorise(checks: list[str]) -> list[tuple[str, list[str]]]:
    circuit, layout = [], []
    for item in _dedupe_checks(checks):
        low = item.lower()
        if any(word in low for word in ("land pattern", "clearance", "outline", "drc",
                                        "current", "ipc", "copper", "board")):
            layout.append(item)
        else:
            circuit.append(item)
    groups = []
    if circuit:
        groups.append(("circuit", circuit))
    if layout:
        groups.append(("layout", layout))
    return groups


def _bom(design: dict | None, parts: list | None = None, limit: int = 6) -> str:
    """Component legend. An imported board brings its own parts; a generated one uses the
    placement report - never the other board's BOM."""
    groups: dict[str, list[str]] = {}
    if parts:
        for item in parts:
            groups.setdefault(str(item.get("pattern") or "?"), []).append(str(item.get("ref") or "?"))
    elif design:
        for item in design.get("placement") or []:
            groups.setdefault(str(item.get("pattern") or "?"), []).append(str(item.get("ref") or "?"))
    else:
        return ""
    rows = []
    for pattern, refs in list(groups.items())[:limit]:
        rows.append("<span><b>" + html.escape(" ".join(sorted(refs))) + "</b> <em>" +
                    html.escape(pattern) + "</em></span>")
    return '<div class="legend">' + "".join(rows) + "</div>" if rows else ""


def _rev_key(stem: str) -> tuple[int, str]:
    """rev-c-fixed -> (3, 'fixed'); everything else sorts last."""
    import re as _re

    match = _re.search(r"rev[-_]?([a-z])\b", stem, _re.I)
    if not match:
        return (99, stem)
    return (ord(match.group(1).lower()) - 96, stem)


def _rev_title(stem: str) -> str:
    import re as _re

    match = _re.search(r"rev[-_]?([a-z])[-_]?(.*)$", stem, _re.I)
    if not match:
        return stem.replace("-", " ").replace("_", " ").strip().capitalize()
    letter, rest = match.group(1).upper(), match.group(2).replace("-", " ").strip()
    return "Rev " + letter + (" <em>· " + html.escape(rest) + "</em>" if rest else "")


def _arow(kind: str, href: str, title: str, verdict: str, cls: str,
          meta: str, delta: str = "") -> str:
    extra = " down" if delta.startswith("+") else (
        " up" if delta.startswith("−") or delta.startswith("-") else "")
    return (
        '<a class="arow" data-kind="' + kind + '" data-verdict="' + cls +
        '" href="' + html.escape(href) + '">'
        '<span class="atitle">' + title + "</span>"
        '<span class="averdict ' + cls + '">' + html.escape(verdict) + "</span>"
        '<span class="ameta">' + meta + "</span>"
        '<span class="adelta' + extra + '">' + html.escape(delta) + "</span></a>"
    )


def _artifact_rows(found: dict) -> str:
    from .diff import compare

    reports = sorted(found.get("reports") or [], key=lambda item: _rev_key(item[0].stem))
    revisions = [item for item in reports if _rev_key(item[0].stem)[0] < 99]
    others = [item for item in found.get("reports") or [] if _rev_key(item[0].stem)[0] >= 99]
    rows: list[str] = []
    previous = None
    if revisions:
        rows.append('<div class="agroup"><b>Revisions</b><span>against the previous run</span></div>')
    for path, data in revisions:
        counts = data.get("counts") or {}
        passed = data.get("status") == "passed"
        errors = counts.get("error", 0)
        delta = ""
        if previous is not None:
            result = compare(previous, data)
            introduced = result["summary"]["introduced"]
            fixed = result["summary"]["fixed"]
            if introduced:
                delta = "+" + str(introduced)
            elif fixed:
                delta = "−" + str(fixed)
        previous = data
        href = path.with_suffix(".html").name if path.with_suffix(".html").exists() else path.name
        verdict = "Passed" if passed else ("Failed · " + str(errors) if errors else "Failed")
        rows.append(_arow(
            "revisions", href, _rev_title(path.stem), verdict,
            "ok" if passed else "bad",
            str(data.get("components", "?")) + " components · " +
            str(data.get("nets", "?")) + " nets", delta))

    evidence: list[str] = []
    for path, data in others:
        counts = data.get("counts") or {}
        passed = data.get("status") == "passed"
        errors = counts.get("error", 0)
        href = path.with_suffix(".html").name if path.with_suffix(".html").exists() else path.name
        verdict = "Passed" if passed else ("Failed · " + str(errors) if errors else "Failed")
        evidence.append(_arow(
            "evidence", href,
            html.escape(path.stem.replace("-", " ").capitalize()),
            verdict, "ok" if passed else "bad",
            str(data.get("components", "?")) + " components · " +
            str(data.get("nets", "?")) + " nets"))

    if found.get("passport"):
        path, data = found["passport"]
        counts = data.get("counts") or {}
        cleared = data.get("status") == "cleared"
        crit = counts.get("critical", 0)
        evidence.append(_arow(
            "evidence", path.with_suffix(".html").name,
            "Passport · " + html.escape(str(data.get("revision") or "—")),
            "Cleared" if cleared else ("Blocked · " + str(crit) if crit else "Blocked"),
            "ok" if cleared else "bad",
            str(counts.get("unverified", 0)) + " unverified · " +
            html.escape(str(data.get("passport_hash", ""))[:10])))

    for path, data in found.get("designs") or []:
        census = data.get("census") or {}
        evidence.append(_arow(
            "evidence", path.with_suffix(".svg").name,
            "Layout · " + str(census.get("footprints", 0)) + " footprints",
            "Generated", "ok",
            str(census.get("pads", 0)) + " pads · " +
            f"{census.get('width_mm', 0):g} × {census.get('height_mm', 0):g} mm"))

    pcb_checks = found.get("pcb_checks") or []
    for path, data in pcb_checks:
        counts = data.get("counts") or {}
        drc = data.get("drc") or {}
        passed = data.get("status") == "passed"
        title = "PCB check"
        if len(pcb_checks) > 1:
            extra = path.stem.replace("-pcb", "").replace("pcb-check", "").replace("pcb_check", "")
            extra = extra.replace("-", " ").replace("_", " ").strip()
            if extra and extra.lower() not in {"pcb", "check"}:
                title = "PCB check · " + html.escape(extra)
        meta = str(counts.get("error", 0)) + " errors · " + str(counts.get("notice", 0)) + " notices"
        if drc.get("available"):
            meta += " · DRC " + str(drc.get("violations", 0))
        evidence.append(_arow(
            "evidence", path.name, title,
            "Passed" if passed else "Failed",
            "ok" if passed else "bad", meta))

    for path, data in found.get("redteams") or []:
        score = data.get("score") or {}
        layout = data.get("kind") == "pcb-redteam"
        total = score.get("faults", score.get("targeted", 0))
        caught = score.get("caught", 0)
        body = ("swapped nets, dropped parts, nudged copper" if layout
                else "supply, ground, pull-up and firmware faults")
        gaps, unv = score.get("gaps", 0), score.get("unverifiable", 0)
        extra = []
        if gaps:
            extra.append(str(gaps) + (" gap" if gaps == 1 else " gaps"))
        if unv:
            extra.append(str(unv) + " unverifiable")
        if extra:
            body += " · " + " · ".join(extra)
        evidence.append(_arow(
            "evidence", path.name,
            "Red team · " + ("layout" if layout else "rules"),
            str(caught) + "/" + str(total) + " caught",
            "ok" if caught == total else "warn", body))

    for path, data in found.get("diffs") or []:
        summary = data.get("summary") or {}
        regressed = data.get("regressed")
        introduced = summary.get("introduced", 0)
        evidence.append(_arow(
            "evidence", path.name, "Revision gate",
            "Blocked" if regressed else "Clean",
            "bad" if regressed else "ok",
            str(summary.get("fixed", 0)) + " fixed · " +
            str(summary.get("persisting", 0)) + " pre-existing",
            ("+" + str(introduced)) if introduced else ""))

    if evidence:
        rows.append('<div class="agroup"><b>Evidence</b><span>what those runs produced</span></div>')
        rows.extend(evidence)
    if not rows:
        rows.append('<div class="arow empty-row">No artifacts yet. Run '
                    '<code>boardproof prove</code> in this directory.</div>')
    return '<div class="arows" id="grid">' + "".join(rows) + "</div>"


def _spinner_markup(primary: dict) -> str:
    """The 3D stage: static render as the no-JS fallback, plus a live canvas."""
    fallback = primary.get("svg3d") or ""
    return ('<svg class="bp3d" role="img" aria-label="360 degree board view"></svg>'
            '<div class="bp3d-fallback" aria-hidden="true">' + fallback + "</div>")


def _preview_dialog(primary: dict, views: list, title_block: str, checks_html: str,
                    downloads: list, previews: dict | None) -> str:
    previews = previews or {}
    board_panels = "".join(
        '<div class="boardstage" data-view="' + name + '" data-pvcomeback="' + name + '"' +
        ("" if index == 0 else ' style="display:none"') + ">" + markup + "</div>"
        for index, (name, markup, _label) in enumerate(views))
    tabs = [("board", "Board"), ("layout", "Layout")]
    if previews.get("schematic"):
        tabs.append(("schematic", "Schematic"))
    if previews.get("datasheets"):
        tabs.append(("datasheet", "Datasheets"))
    tab_html = "".join(
        '<button type="button" data-pvtab="' + key + '"' + ("" if index else ' class="on"') +
        ">" + label + "</button>" for index, (key, label) in enumerate(tabs))
    datasheets = "".join(
        '<figure style="margin:0 0 14px"><figcaption style="font:12px var(--sans);'
        'color:var(--ink4);margin-bottom:6px">' +
        html.escape(item["label"]) + " · cited page</figcaption>"
        '<img src="' + html.escape(item["file"]) + '" alt="datasheet page"></figure>'
        for item in previews.get("datasheets") or []) or (
        '<p class="scope">No datasheet page rendered for this board.</p>')
    schematic = previews.get("schematic") or (
        '<p class="scope">No schematic derived for this board.</p>')
    return (
        '<dialog id="bp-preview" aria-label="Board preview">'
        '<div class="pvhead"><b>' + html.escape(primary["file"]) + " · preview</b>"
        '<button type="button" data-pvclose aria-label="Close preview">×</button></div>'
        '<div class="pvtabs" role="tablist">' + tab_html + "</div>"
        '<div class="pvbody">'
        '<div data-pvpanel="board">' + board_panels + "</div>"
        '<div data-pvpanel="layout" style="display:none">' + title_block
        + '<div style="margin-top:14px">' + checks_html + "</div></div>"
        '<div data-pvpanel="schematic" style="display:none">' + schematic + "</div>"
        '<div data-pvpanel="datasheet" style="display:none">' + datasheets + "</div>"
        "</div>"
        '<div class="pvfoot">' + "".join(
            '<a class="dl" href="' + html.escape(href) + '"' +
            (' download' if href.endswith((".zip", ".kicad_pcb")) else
             ' target="_blank" rel="noopener"') + ">" + html.escape(label) + "</a>"
            for label, href, _ in downloads)
        + '<span class="scope" style="border:0;padding:0;margin-left:auto">generated from the '
          "verified geometry · Gerbers via kicad-cli</span></div></dialog>")


def _board_panel(boards: list[dict], found_passport: bool = False,
                 design: dict | None = None, revision: str = "",
                 previews: dict | None = None) -> str:
    if not boards:
        return ('<div class="empty">No generated board yet. Press <b>Generate board</b> above, '
                'or run <code>boardproof design --config boardproof.json</code> — the preview '
                'appears here.</div>')
    primary = boards[0]
    check = primary.get("check") or {}
    census = check.get("census") or {}
    verified = check.get("verified") or []
    scope = check.get("unverified") or []
    passed = str(check.get("status")) == "passed"
    errors = check.get("counts", {}).get("error", 0)
    routed = census.get("segments") or 0

    tags = []
    if any("datasheet" in str(v) for v in verified):
        tags.append('<span class="tagx ok">land pattern vs datasheet</span>')
    if any("IPC-2221" in str(v) for v in verified):
        tags.append('<span class="tagx ok">current capacity</span>')
    if any("DRC" in str(v) for v in verified):
        tags.append('<span class="tagx ok">KiCad DRC</span>')
    design_fp = (design or {}).get("footprints") or {}
    if design_fp.get("guessed"):
        tags.append('<span class="tagx warn">footprint guessed · ' +
                    html.escape(", ".join(design_fp["guessed"])) + "</span>")
    policy = check.get("policy") or {}
    if policy.get("advisory"):
        tags.append('<span class="tagx">geometry advisory · ' +
                    html.escape(str(policy.get("authoritative", "DRC authoritative"))) + "</span>")
    if not routed:
        tags.append('<span class="tagx warn">routing not attempted</span>')
    elif not (check.get("policy") or {}).get("advisory"):
        tags.append('<span class="tagx">' + str(check.get("nets", {}).get("fully_connected", 0)) +
                    "/" + str(check.get("nets", {}).get("total", 0)) + " nets connected</span>")
    else:
        tags.append('<span class="tagx">' + str(census.get("segments", 0)) + " tracks · " +
                    str(census.get("vias", 0)) + " vias</span>")

    specs = "".join(
        "<div><span>" + label + "</span><strong>" + value + "</strong></div>"
        for label, value in (
            ("Footprints", str(census.get("footprints", "—"))),
            ("Pads", str(census.get("pads", "—"))),
            ("Board", (f"{census.get('width_mm', 0):g} × {census.get('height_mm', 0):g} mm"
                       if census.get("width_mm") else "—")),
            ("Copper", (f"{census.get('segments', 0)} tracks · {census.get('vias', 0)} vias"
                        if routed else "placement only")),
        )
    )
    groups = _categorise(verified)
    check_html = ""
    if groups:
        blocks = []
        for name, items in groups:
            shown = items[:4]
            body = "".join('<div class="chk">' + html.escape(item) + "</div>" for item in shown)
            if len(items) > len(shown):
                body += '<div class="more">+' + str(len(items) - len(shown)) + " more</div>"
            blocks.append('<div class="checkgrp two"><div class="gl">' + name + "</div>" +
                          body + "</div>")
        check_html = '<div class="checks">' + "".join(blocks) + "</div>"

    scope_html = ""
    if scope:
        scope_html = ('<div class="scope"><b>Not verified by this run</b>' +
                      html.escape(", ".join(str(s_).split(" (")[0] for s_ in scope[:4])) +
                      "</div>")

    check_html = "".join(
        '<div class="chk">' + html.escape(item) + "</div>"
        for item in _dedupe_checks(verified)[:8])
    links = ['<a href="' + html.escape(primary["file"]) + '" target="_blank" rel="noopener">'
             "Open the SVG</a>"]
    if found_passport:
        links.append('<a href="passport.html">Passport</a>')

    views = [("2d", primary["svg"], "Top view")]
    if primary.get("svg3d"):
        views.append(("3d", _spinner_markup(primary), "Drag to spin · 360°"))
    stages = "".join(
        '<div class="boardstage" data-view="' + name + '"' +
        ("" if index == 0 else ' style="display:none"') + ">"
        '<span class="viewtag">' + label + "</span>"
        + ('<span class="spinhint">drag to spin</span>' if name == "3d" else "")
        + ('<a class="zoomer" href="' + html.escape(primary["file"]) + '" target="_blank" '
           'rel="noopener" aria-label="Open the board drawing at full size">'
           if name == "2d" else '<div class="zoomer">')
        + markup + ("</a></div>" if name == "2d" else "</div></div>")
        for index, (name, markup, label) in enumerate(views)
    )
    toggle = ""
    if len(views) > 1:
        toggle = ('<div class="viewtoggle" role="group" aria-label="Board view">'
                  '<button type="button" class="vt on" data-view-btn="2d">2D</button>'
                  '<button type="button" class="vt" data-view-btn="3d">3D</button></div>')
    downloads = [("Open SVG", primary["file"], "_blank")]
    stem = Path(primary["file"]).stem
    for label, candidate in (
            ("3D SVG", stem + "-3d.svg"),
            ("KiCad board", stem + ".kicad_pcb"),
            ("Gerbers zip", stem + "-gerbers.zip")):
        if (Path(primary.get("dir") or "artifacts") / candidate).is_file():
            downloads.append((label, candidate, ""))


    netlist = Path(str((check.get("board") or ""))).name or primary["file"]
    drawing = "BP-" + "".join(ch for ch in Path(netlist).stem.upper() if ch.isalnum() or ch == "-")
    size = (f"{census.get('width_mm', 0):g} × {census.get('height_mm', 0):g} mm"
            if census.get("width_mm") else "—")
    title_block = (
        '<div class="tblock">'
        "<div><span>drawing</span><strong>" + html.escape(drawing[:26]) + "</strong></div>"
        "<div><span>revision</span><strong>" + html.escape(revision or "—") + "</strong></div>"
        "<div><span>sheet</span><strong>1 / 1</strong></div>"
        "<div><span>outline</span><strong>" + html.escape(size) + "</strong></div>"
        "<div><span>scale</span><strong>1 : 1</strong></div>"
        "<div><span>copper</span><strong>" + ("routed" if routed else "placement") + "</strong></div>"
        '<div class="wide"><span style="margin:0">Pad-to-net verified against the schematic</span>'
        "<span>" + html.escape(Path(primary["file"]).name) + "</span></div></div>"
    )
    download_row = ('<div class="dlrow">'
                    '<button type="button" class="pvbtn" data-preview-open>'
                    "Preview &amp; download</button>"
                    '<span class="scope" style="border:0;padding:0;margin:0">board · layout · '
                    "schematic · datasheet</span></div>"
                    + _preview_dialog(primary, views, title_block, check_html, downloads, previews))

    return (
        '<div class="board"><div class="boardleft">'
        '<div class="viewbar"><span class="viewlabel">Board view</span>' + toggle +
        '<span class="stamp-flag' + ("" if passed else " bad") + '">' +
        ("Verified" if passed else "Blocked") + "</span></div>"
        + stages
        + title_block + download_row + "</div>"
        '<div class="boardmeta">'
        '<div class="eyebrow2">Generated layout</div>'
        '<div class="statusline"><div><h3 class="' + ("ok" if passed else "bad") + '">' +
        ("Verified candidate" if passed else "Blocked candidate") + "</h3>"
        "<p>" + ((str(errors) + " layout error" + ("" if errors == 1 else "s") + " to fix")
                 if not passed
                 else "Footprints and pad-to-net mapping match the schematic") + "</p></div></div>"
        '<div class="specs">' + specs + "</div>"
        '<div class="tags">' + "".join(tags) + "</div>"
        + _bom(design, (check or {}).get("parts")) + check_html + scope_html
        + '<div class="boardlinks">' + "".join(links) + "</div>"
        "</div></div>"
    )



SPIN_JS = """
(function () {
  const payload = document.getElementById('bp-board-model');
  if (!payload) return;
  let model;
  try { model = JSON.parse(payload.textContent || '{}'); } catch (error) { return; }
  if (!model.parts || !model.w) return;

  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const TILT = 0.62;
  const arduino = model.look === 'arduino';
  const MASK = arduino ? '#0b4f8a' : '#0c4f2e';
  const MASK_DARK = arduino ? '#083560' : '#083a22';
  const MASK_LIGHT = arduino ? '#1563a8' : '#11613a';
  const COPPER = arduino ? '#c9d0d6' : '#c99245';
  const COPPER_LIGHT = arduino ? '#e6eaee' : '#e2b467';
  const TRACE = arduino ? '#2a7ab8' : '#2e7a52';
  const TRACE_B = arduino ? '#0a3d6e' : '#0a3a24';
  const SILK = '#f3f6f8';
  const KIND = {
    usb: ['#c5ccd3', '#6f777f'], header: ['#1a1a1a', '#0a0a0a'], dip: ['#1c1c1c', '#0d0d0d'],
    ic: ['#222', '#0e0e0e'], electrolytic: ['#cfd5db', '#1c2228'], crystal: ['#e8ebef', '#8a9198'],
    led: ['#c0282c', '#5c1214'], resistor: ['#d7b48a', '#6a5030'], cap: ['#c4a06a', '#5a4830'],
    diode: ['#2a2e33', '#101214'], jack: ['#1a1a1a', '#0a0a0a'], smd: ['#3a4048', '#1a1d22']
  };

  function project(x, y, z, yaw) {
    const dx = x - model.w / 2, dy = y - model.h / 2;
    const rx = dx * Math.cos(yaw) - dy * Math.sin(yaw);
    const ry = dx * Math.sin(yaw) + dy * Math.cos(yaw);
    return { X: rx, Y: ry * TILT - z, D: ry };
  }

  function box(parts, x0, y0, x1, y1, zLow, zHigh, yaw, fillTop, fillA, fillB, stroke) {
    const c = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
    const top = c.map(([x, y]) => project(x, y, zHigh, yaw));
    const low = c.map(([x, y]) => project(x, y, zLow, yaw));
    // two faces that look toward the viewer: greatest projected D
    const edges = [[0, 1], [1, 2], [2, 3], [3, 0]];
    const ranked = edges
      .map(([a, b]) => ({ a, b, d: (top[a].D + top[b].D) / 2 }))
      .sort((m, n) => m.d - n.d);
    ranked.slice(-2).forEach(({ a, b }) => {
      parts.push('<polygon points="' +
        [top[a], top[b], low[b], low[a]].map(p => p.X.toFixed(2) + ',' + p.Y.toFixed(2)).join(' ') +
        '" fill="' + fillB + '"/>');
    });
    parts.push('<polygon points="' + top.map(p => p.X.toFixed(2) + ',' + p.Y.toFixed(2)).join(' ') +
      '" fill="' + fillTop + '"' + (stroke ? ' stroke="' + stroke + '" stroke-width="0.12"' : '') + '/>');
    return top;
  }

  function frame(svg, yaw) {
    const parts = [];
    const z0 = 0, zt = model.t;
    const bounds = [];
    const track = (p) => bounds.push(p);

    const corners = [[0, 0], [model.w, 0], [model.w, model.h], [0, model.h]];
    corners.forEach(([x, y]) => { track(project(x, y, zt, yaw)); track(project(x, y, 0, yaw)); });
    model.parts.forEach((part) => {
      track(project(part.x - part.w / 2, part.y - part.d / 2, zt + part.z, yaw));
      track(project(part.x + part.w / 2, part.y + part.d / 2, zt + part.z, yaw));
    });

    parts.push('<polygon points="' + corners.map(([x, y]) => {
      const p = project(x, y, 0, yaw);
      return p.X.toFixed(2) + ',' + p.Y.toFixed(2);
    }).join(' ') + '" fill="' + MASK_DARK + '"/>');

    box(parts, 0, 0, model.w, model.h, z0, zt, yaw, MASK, MASK_LIGHT, MASK_DARK, MASK_DARK);
    (model.holes || []).forEach((h) => {
      const p = project(h[0], h[1], zt, yaw);
      parts.push('<circle cx="' + p.X.toFixed(2) + '" cy="' + p.Y.toFixed(2) +
        '" r="1.15" fill="#0a1220"/>');
    });

    (model.tracks || []).forEach((t) => {
      const a = project(t.x1, t.y1, zt, yaw), b = project(t.x2, t.y2, zt, yaw);
      parts.push('<line x1="' + a.X.toFixed(2) + '" y1="' + a.Y.toFixed(2) + '" x2="' +
        b.X.toFixed(2) + '" y2="' + b.Y.toFixed(2) + '" stroke="' +
        (t.b ? TRACE_B : TRACE) + '" stroke-width="' + Math.max(0.25, t.w) + '" opacity="' +
        (t.b ? 0.45 : 0.85) + '"/>');
    });

    const ordered = model.parts.slice().map((part) => ({
      part: part,
      depth: project(part.x, part.y, zt, yaw).D
    })).sort((a, b) => a.depth - b.depth);

    ordered.forEach(({ part }) => {
      const colours = KIND[part.kind] || KIND.smd;
      const quad = part.quad || [
        [part.x - part.w / 2, part.y - part.d / 2],
        [part.x + part.w / 2, part.y - part.d / 2],
        [part.x + part.w / 2, part.y + part.d / 2],
        [part.x - part.w / 2, part.y + part.d / 2]
      ];
      const cap = quad.map(([x, y]) => project(x, y, zt + part.z, yaw));
      const low = quad.map(([x, y]) => project(x, y, zt, yaw));
      const walls = [[1, 2], [2, 3], [3, 0], [0, 1]]
        .map(([a, b]) => ({ a: a, b: b, d: (cap[a].D + cap[b].D) / 2 }))
        .sort((m, n) => m.d - n.d)
        .slice(-2);
      walls.forEach(({ a, b }) => {
        parts.push('<polygon points="' + [cap[a], cap[b], low[b], low[a]]
          .map(p => p.X.toFixed(2) + ',' + p.Y.toFixed(2)).join(' ') +
          '" fill="' + colours[1] + '"/>');
      });
      parts.push('<polygon points="' + cap
        .map(p => p.X.toFixed(2) + ',' + p.Y.toFixed(2)).join(' ') +
        '" fill="' + colours[0] + '" stroke="#0f1216" stroke-width="0.12"/>');
      (part.pads || []).forEach((pad) => {
        const c = [[pad.x - pad.w / 2, pad.y - pad.d / 2], [pad.x + pad.w / 2, pad.y - pad.d / 2],
                   [pad.x + pad.w / 2, pad.y + pad.d / 2], [pad.x - pad.w / 2, pad.y + pad.d / 2]];
        parts.push('<polygon points="' + c.map(([x, y]) => {
          const p = project(x, y, zt + part.z, yaw);
          return p.X.toFixed(2) + ',' + p.Y.toFixed(2);
        }).join(' ') + '" fill="' + COPPER_LIGHT + '" stroke="' + COPPER + '" stroke-width="0.08"/>');
      });
      const label = project((quad[0][0] + quad[2][0]) / 2, (quad[0][1] + quad[2][1]) / 2,
                            zt + part.z + 1.1, yaw);
      parts.push('<text x="' + label.X.toFixed(2) + '" y="' + label.Y.toFixed(2) +
        '" font-family="ui-sans-serif,system-ui,sans-serif" font-size="1.7" fill="' + SILK +
        '" text-anchor="middle" opacity="0.9">' + part.ref + '</text>');
    });

    (model.vias || []).forEach((via) => {
      const p = project(via.x, via.y, zt, yaw);
      parts.push('<circle cx="' + p.X.toFixed(2) + '" cy="' + p.Y.toFixed(2) + '" r="' +
        (via.s / 2).toFixed(2) + '" fill="' + COPPER + '"/>');
    });

    const xs = bounds.map((b) => b.X), ys = bounds.map((b) => b.Y);
    const spanX = Math.max.apply(null, xs) - Math.min.apply(null, xs) || 1;
    const spanY = Math.max.apply(null, ys) - Math.min.apply(null, ys) || 1;
    const scale = Math.min(82 / spanX, 60 / spanY);
    const cx = (Math.max.apply(null, xs) + Math.min.apply(null, xs)) / 2;
    const cy = (Math.max.apply(null, ys) + Math.min.apply(null, ys)) / 2;
    svg.setAttribute('viewBox', (cx - 50 / scale).toFixed(2) + ' ' + (cy - 38 / scale).toFixed(2) +
      ' ' + (100 / scale).toFixed(2) + ' ' + (76 / scale).toFixed(2));
    svg.innerHTML = parts.join('');
    svg.dataset.drawn = '1';
  }

  document.querySelectorAll('.bp3d').forEach(function (svg) {
    let yaw = Math.PI / 4;
    let dragging = null;
    let spinning = !reduce;
    const fallback = svg.parentElement && svg.parentElement.querySelector('.bp3d-fallback');
    if (fallback) fallback.style.display = 'none';
    svg.style.display = '';

    function render() { frame(svg, yaw); }
    render();

    function tick() {
      if (spinning) { yaw += 0.004; render(); }
      requestAnimationFrame(tick);
    }
    if (spinning) requestAnimationFrame(tick);

    svg.addEventListener('pointerdown', function (event) {
      dragging = { x: event.clientX, yaw: yaw };
      spinning = false;
      svg.setPointerCapture(event.pointerId);
    });
    svg.addEventListener('pointermove', function (event) {
      if (!dragging) return;
      yaw = dragging.yaw + (event.clientX - dragging.x) * 0.012;
      render();
    });
    svg.addEventListener('pointerup', function () { dragging = null; });
    svg.addEventListener('pointercancel', function () { dragging = null; });
    svg.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowLeft') { yaw -= 0.15; render(); event.preventDefault(); }
      if (event.key === 'ArrowRight') { yaw += 0.15; render(); event.preventDefault(); }
    });
    svg.setAttribute('tabindex', '0');
    svg.dataset.spinYaw = String(Math.PI / 4);
  });
  window.bpSpinRender = function () {
    document.querySelectorAll('.bp3d').forEach(function (svg) {
      if (svg.getBoundingClientRect().width > 0 && !svg.childElementCount) {
        frame(svg, Math.PI / 4);
      }
    });
  };
})();
"""


BOARD_JS = """
const pv = document.getElementById('bp-preview');
if (pv) {
  document.querySelectorAll('[data-preview-open]').forEach(function (btn) {
    btn.addEventListener('click', function () { if (pv.showModal) pv.showModal(); });
  });
  var closeBtn = pv.querySelector('[data-pvclose]');
  if (closeBtn) closeBtn.addEventListener('click', function () { pv.close(); });
  pv.addEventListener('click', function (event) { if (event.target === pv) pv.close(); });
  pv.querySelectorAll('[data-pvtab]').forEach(function (tab) {
    tab.addEventListener('click', function () {
      var want = tab.getAttribute('data-pvtab');
      pv.querySelectorAll('[data-pvtab]').forEach(function (t) {
        t.classList.toggle('on', t === tab);
      });
      pv.querySelectorAll('[data-pvpanel]').forEach(function (panel) {
        panel.style.display = panel.getAttribute('data-pvpanel') === want ? '' : 'none';
      });
    });
  });
  if (location.hash.indexOf('#preview') === 0 && pv.showModal) {
    pv.showModal();
    if (location.hash === '#preview-3d') {
      setTimeout(function () {
        var three = document.querySelector('[data-view-btn="3d"]');
        if (three) three.click();
      }, 0);
    }
  }
}
document.querySelectorAll('[data-view-btn]').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var want = btn.getAttribute('data-view-btn');
    document.querySelectorAll('.boardstage[data-view]').forEach(function (stage) {
      stage.style.display = stage.getAttribute('data-view') === want ? '' : 'none';
    });
    document.querySelectorAll('[data-view-btn]').forEach(function (b) {
      b.classList.toggle('on', b === btn);
    });
    if (window.bpSpinRender) requestAnimationFrame(window.bpSpinRender);
    try { localStorage.setItem('bp-board-view', want); } catch (e) {}
  });
});
document.querySelectorAll('[data-thumb]').forEach(function (thumb) {
  thumb.addEventListener('click', function () {
    var index = thumb.getAttribute('data-thumb');
    document.querySelectorAll('.boardstage').forEach(function (stage) {
      stage.style.display = stage.getAttribute('data-board') === index ? '' : 'none';
    });
    document.querySelectorAll('.thumb').forEach(function (t) { t.classList.remove('on'); });
    thumb.classList.add('on');
  });
});
"""


def render(found: dict, title: str = "BoardProof", studio: list[dict] | None = None,
           read_only: bool = False) -> str:
    reports, redteam, passport, diffs = (found["reports"], found["redteam"],
                                         found["passport"], found["diffs"])
    reports = sorted(found["reports"], key=lambda item: item[0].stat().st_mtime, reverse=True)
    latest = reports[0][1] if reports else {}
    redteam = redteam or ((found.get("redteams") or [None])[0])
    score = (redteam[1].get("score") or {}) if redteam else {}
    packs = latest.get("packs") or []
    unverified = len(latest.get("unverified_scope") or [])

    cards = []
    for path, data in reports:
        name = _pretty(path.stem)
        page = path.with_suffix(".html")
        link = page.name if page.exists() else path.name
        packs_n = len(data.get("packs") or [])
        cards.append(
            f'<a class="card" href="{html.escape(link)}"><div class="kind">check report</div>'
            f"<h3>{html.escape(name)}</h3>"
            f'<p>{data.get("components", "?")} components · {data.get("nets", "?")} nets · '
            f"{packs_n} rule pack(s) · {html.escape(str(data.get('config') or 'boardproof.json'))}</p>"
            f'<div class="row">{_status_pill(data)}'
            f'<span class="pill">{len(data.get("findings") or [])} finding(s)</span>'
            f'<span class="pill">exit {data.get("exit_code", "?")}</span></div></a>'
        )
    if passport:
        path, data = passport
        cards.append(
            f'<a class="card" href="{html.escape(path.with_suffix(".html").name)}">'
            '<div class="kind">manufacturing artifact</div>'
            f'<h3>Preflight Passport · {html.escape(str(data.get("revision")))}</h3>'
            '<p>What was verified, what failed, and what remains unverified before fabrication.</p>'
            f'<div class="row">{_status_pill(data)}'
            f'<span class="pill">{data.get("counts", {}).get("unverified", "?")} unverified</span>'
            f'<span class="pill">hash {html.escape(str(data.get("passport_hash", ""))[:10])}</span></div></a>'
        )
    for path, data in (found.get("redteams") or ([redteam] if redteam else [])):
        ratio = int(round((data.get("score", {}).get("ratio") or 0) * 100))
        cards.append(
            f'<a class="card" href="{html.escape(path.name)}"><div class="kind">mutation test</div>'
            f"<h3>Red Team · {data['score'].get('caught')}/"
            f"{data['score'].get('faults', data['score'].get('targeted'))} caught</h3>"
            f'<p class="kind" style="margin-top:2px">{html.escape(str(data.get("config") or ""))}</p>' 
            f"<p>{ratio}% of faults aimed at an existing rule were detected. "
            f"{data['score'].get('gaps')} blind spot(s) named with the rule that closes them.</p>"
            f'<div class="row"><span class="pill ok">{ratio}% coverage</span>'
            f'<span class="pill warn">{data["score"].get("gaps")} gap(s)</span>'
            f'<span class="pill">{data["score"].get("unverifiable")} unverifiable</span></div></a>'
        )
    for path, data in (found.get("designs") or []):
        census = data.get("census") or {}
        cards.append(
            f'<a class="card" href="{html.escape(path.with_suffix(".svg").name)}">'
            '<div class="kind">generated layout</div>'
            f"<h3>Design Studio · {census.get('footprints', 0)} footprints</h3>"
            f"<p>{census.get('pads', 0)} pads · {census.get('width_mm', 0):g}×"
            f"{census.get('height_mm', 0):g} mm editable KiCad board · "
            f"{len(data.get('placement') or [])} placement rules applied.</p>"
            f'<div class="row"><span class="pill ok">generated</span>'
            f'<span class="pill">{"routed" if (data.get("routing") or {}).get("attempted") else "placement only"}</span>'
            f'<span class="pill">preview .svg</span></div></a>'
        )
    for path, data in (found.get("pcb_checks") or []):
        census = data.get("census") or {}
        cards.append(
            f'<a class="card" href="{html.escape(path.name)}"><div class="kind">physical check</div>'
            f"<h3>PCB Check · {html.escape(str(data.get('status', '')).upper())}</h3>"
            f"<p>{census.get('pads', 0)} pads · {census.get('footprints', 0)} footprints · "
            f"KiCad DRC {((data.get('drc') or {}).get('violations', 0))} violation(s) · "
            f"{(data.get('drc') or {}).get('unconnected', 0)} unconnected.</p>"
            f'<div class="row">{_status_pill(data)}'
            f'<span class="pill">{data["counts"]["error"]} error(s)</span>'
            f'<span class="pill">{data["counts"].get("notice", 0)} notice(s)</span></div></a>'
        )
    for path, data in diffs:
        summary = data.get("summary") or {}
        cls = "warn" if data.get("regressed") else "ok"
        cards.append(
            f'<a class="card" href="{html.escape(path.name)}"><div class="kind">revision gate</div>'
            f"<h3>{'Blocked' if data.get('regressed') else 'No new violations'} on this revision</h3>"
            f'<p>{html.escape(Path(str((data.get("head") or {}).get("netlist") or "")).name)} against '
            f'{html.escape(Path(str((data.get("base") or {}).get("netlist") or "")).name)}</p>'
            f"<p>{summary.get('introduced', 0)} introduced · {summary.get('fixed', 0)} fixed · "
            f"{summary.get('persisting', 0)} pre-existing.</p>"
            f'<div class="row"><span class="pill {cls}">'
            f'{"regression" if data.get("regressed") else "clean delta"}</span></div></a>'
        )
    cards_html = "".join(cards) or (
        '<div class="empty">No artifacts yet. Run <code>boardproof check</code>, '
        "<code>boardproof redteam</code> and <code>boardproof passport</code> in this directory.</div>")

    reviewer_names = ", ".join(sorted(
        {str(p.get("reviewed_by") or "") for p in packs} - {""})) or "no reviewer"
    findings_n = len(latest.get("findings") or [])
    gaps_n = score.get("gaps", 0)
    tiles = (
        f'<div><span>Verdict</span><strong class="'
        f'{"bad" if latest.get("status") == "failed" else "ok"}">'
        f'{html.escape(str(latest.get("status", "none")).capitalize())}</strong>'
        f'<em>{findings_n} finding{"s" if findings_n != 1 else ""}</em></div>'
        f'<div><span>Faults</span><strong class="ok">'
        f'{score.get("caught", 0)}/{score.get("faults", score.get("targeted", 0))}</strong>'
        f'<em>{gaps_n} gap{"s" if gaps_n != 1 else ""} declared</em></div>'
        f'<div><span>Packs</span><strong>{len(packs)}</strong>'
        f'<em>{html.escape(reviewer_names)}</em></div>'
        f'<div><span>Unverified</span><strong class="warn">{unverified}</strong>'
        "<em>outside this pass</em></div>"
    )
    flow = "".join(
        f'<div class="wstep"><span class="wn">{num}</span><b>{name}</b>'
        f'<span>{what}</span><em>{cmd}</em></div>'
        for num, name, what, cmd in FLOW
    )

    studio_html = _studio_panel(studio, read_only) if studio is not None else ""
    first_board = (found.get("boards") or [{}])[0]
    revision_label = str((first_board.get("check") or {}).get("title")
                         or Path(str(first_board.get("file") or "board.svg")).stem)
    try:
        build_stamp = datetime.fromtimestamp(
            Path(__file__).stat().st_mtime).strftime("%d %b %H:%M")
    except OSError:  # pragma: no cover
        build_stamp = "unknown"
    found_artifacts = (len(found.get("reports") or []) + len(found.get("designs") or [])
                       + len(found.get("pcb_checks") or []) + len(found.get("redteams") or [])
                       + len(found.get("diffs") or []) + (1 if found.get("passport") else 0))
    verdict = "bad" if latest.get("status") == "failed" else "ok"
    return (
        '<!doctype html><html lang="en" data-theme="light"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        '<meta http-equiv="cache-control" content="no-store">'
        '<link rel="icon" href="' + FAVICON + '">'
        "<title>" + html.escape(title) + "</title>"
        "<style>" + CSS + "</style></head><body>"
        '<a class="skip" href="#run">Skip to the run panel</a>' 
        '<div class="bar"><div class="barin">'
        '<div class="brand">' + mark(24) + 'BoardProof</div>'
        '<nav class="anchors"><a href="#run">Run</a><a href="#board">Board</a><a href="#artifacts">Artifacts</a>'
        '<a href="#flow">Flow</a></nav>'
        '<div class="barright"><span class="pill ' + verdict + '">'
        + html.escape(str(latest.get("status", "no runs")).capitalize()) + "</span>"
        '<button class="iconbtn" id="theme" title="Light / dark" '
        'aria-label="Toggle light or dark theme">&#9680;</button></div></div></div>'
        "<main><section class=\"hero\">"
        '<p class="kicker">The first line of defense between a design and a mistake</p>'
        "<h1>Your PCB compiles.<br>But will it work?</h1>"
        '<p class="lede">Connect the netlist, the datasheets and the firmware. '
        "BoardProof finds cross-layer inconsistencies, blocks risky revisions, "
        "and declares what it did not check.</p>"
        '<p class="lede2">Software developers don\'t merge broken code. '
        "Why should hardware developers manufacture unverified designs?</p></section>"
        '<section class="status">' + tiles + "</section>"
        '<section id="run"><div class="head"><h2>Run</h2>'
        '<span class="hint">Named actions in this process</span></div>'
        + (studio_html if studio is not None else
           '<div class="empty">Static view. Start the studio with '
           '<code>boardproof studio --dir artifacts</code> to run the pipeline from here.</div>')
        + "</section>"
        '<section id="board"><div class="head"><h2>Board preview</h2>'
        '<span class="hint">Rendered from the generated .kicad_pcb</span></div>'
        + _board_panel(found.get("boards") or [], bool(found.get("passport")),
                             (found.get("designs") or [(None, None)])[0][1],
                             revision_label,
                             found.get("previews"))
        + "</section>"
        '<section id="artifacts"><div class="head"><h2>Artifacts</h2>'
        '<span class="hint" id="count">' + str(found_artifacts) + " files</span></div>"
        '<div class="tools">'
        '<button class="chip on" data-kind="all">All</button>'
        '<button class="chip" data-kind="revisions">Revisions</button>'
        '<button class="chip" data-kind="evidence">Evidence</button>'
        '<input id="q" type="search" placeholder="Search" aria-label="Search artifacts"></div>'
        + _artifact_rows(found) + "</section>"
        '<section id="flow"><div class="head"><h2>How a revision flows</h2></div>'
        '<div class="flow">' + flow + "</div></section>"
        "<footer><b>Deterministic verdicts, AI-assisted reading.</b> "
        "A human vets every number. The engine computes pass/fail."
        '<br><span class="buildstamp">Made by Team SuperX'
        " · dashboard build " + html.escape(build_stamp) +
        " · " + str(found_artifacts) + " artifacts</span></footer>"
        "</main><div id=\"toast\" role=\"status\" aria-live=\"polite\"></div>"
        + ("<script type=\"application/json\" id=\"bp-board-model\">" +
           (found.get("boards") or [{}])[0].get("model", "{}") + "</script>")
        + (f"<script>{STUDIO_JS}</script>" if studio is not None else "")
        + "<script>" + PAGE_JS + BOARD_JS + SPIN_JS + "</script></body></html>"
    )
