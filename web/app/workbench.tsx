"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { arduinoBoard, artifactUrl, boardFileUrl, BoardView, type Board } from "./board-view";
import { Evidence } from "./evidence";

const groups = [
  { label: "Workspace", items: [["overview", "Overview", "⌂"], ["import", "Import design", "↑"], ["checks", "Circuit checks", "✓"]] },
  { label: "Board", items: [["2d", "2D layout", "▤"], ["3d", "3D viewer", "◇"], ["schematic", "Schematic", "⌘"], ["datasheets", "Datasheets", "▧"]] },
  { label: "Evidence", items: [["pcb", "PCB verification", "◎"], ["redteam", "Red team", "⚑"], ["passport", "Preflight passport", "▣"], ["diffs", "Revision history", "↔"], ["files", "Artifacts", "↓"]] },
] as const;
type View = (typeof groups)[number]["items"][number][0];
const views = groups.flatMap(({ items }) => [...items]);
const arduinoDemo = "demo:arduino";
const demo = {
  broken: "examples/tmp102/boardproof.rev-b-failure.json",
  fixed: "examples/tmp102/boardproof.rev-c-fixed.json",
};
type Workspace = {
  configs: { path: string; rules: number }[];
  board: string | null;
  boards: Board[];
  previews: string[];
  files: string[];
  artifacts: Record<string, string[] | string | null>;
};
type Action = "check" | "design" | "pcb" | "prove" | "redteam" | "passport" | "gerbers";
const actionLabels: Record<Action, string> = {
  check: "Run hardware check", design: "Generate board", pcb: "Verify board",
  prove: "Run preflight", redteam: "Run red team", passport: "Build passport",
  gerbers: "Export Gerbers",
};
type RunResult = { ok: boolean; code: number; log: string[]; seconds?: number; board?: string };
type Upload = {
  config?: string; board?: string; netlist?: string; components?: number; nets?: number; pins?: number;
  draft_rules?: number; downloads?: { label: string; file: string }[];
  parts?: { part: string; refs: string[]; status: string; error?: string }[];
  log?: string[]; next?: string[];
};
type Activity = { action: Action; title: string; result: RunResult; config: string };

async function json<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok || (body.ok === false && body.code === undefined)) {
    const detail = body.detail ?? body.log?.join("\n") ?? `Request failed (${response.status})`;
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg ?? item).join("; ") : detail);
  }
  return body as T;
}

function post<T>(path: string, payload: object) {
  return fetch(`/api/${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }).then(json<T>);
}

async function readFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
    reader.onerror = () => reject(new Error("Could not read selected file."));
    reader.readAsDataURL(file);
  });
}

export default function Workbench() {
  const [view, setView] = useState<View>("overview");
  const [workspace, setWorkspace] = useState<Workspace>();
  const [config, setConfig] = useState("");
  const [boardName, setBoardName] = useState("");
  const [version, setVersion] = useState(0);
  const [files, setFiles] = useState<File[]>([]);
  const [brief, setBrief] = useState("");
  const [fetchDatasheets, setFetchDatasheets] = useState(false);
  const [uploads, setUploads] = useState<{ name: string; data: Upload }[]>([]);
  const [activity, setActivity] = useState<Activity>();
  const [preferred, setPreferred] = useState("");
  const [revision, setRevision] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [fileSearch, setFileSearch] = useState("");

  const refresh = useCallback(async () => {
    const state = await json<Workspace>(await fetch("/api/state", { cache: "no-store" }));
    setWorkspace(state);
    setConfig((current) => state.configs.some((item) => item.path === current) ? current : state.configs[0]?.path ?? "");
    setBoardName((current) => current === arduinoDemo || state.boards.some((item) => item.name === current) ? current : state.board ?? "");
    setVersion((value) => value + 1);
    return state;
  }, []);

  useEffect(() => {
    refresh().catch((reason: Error) => setError(reason.message));
    function syncView() {
      if (window.location.hash === "#main-content") return;
      const match = views.find(([id]) => `#${id}` === window.location.hash);
      setView(match?.[0] ?? "overview");
    }
    syncView();
    window.addEventListener("hashchange", syncView);
    return () => window.removeEventListener("hashchange", syncView);
  }, [refresh]);

  function show(next: View) {
    setView(next);
    window.location.hash = next;
    window.scrollTo({ top: 0, behavior: "instant" });
  }

  async function task(label: string, callback: () => Promise<void>) {
    setError("");
    setBusy(label);
    try {
      await callback();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Request failed.");
    } finally {
      setBusy("");
    }
  }

  function uploadDesign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!files.length && !brief.trim()) return;
    void task("Preparing design…", async () => {
      setUploads([]);
      const failures: string[] = [];
      let importedConfig = "";
      let importedBoard = "";
      for (const file of files.length ? files : [undefined]) {
        const name = file?.name ?? "brief.txt";
        try {
          if (file && file.size > 8 * 1024 * 1024) throw new Error("File exceeds 8 MB.");
          const data = await post<Upload>("upload", {
            filename: name, content_b64: file ? await readFile(file) : undefined,
            brief, fetch_datasheets: fetchDatasheets,
          });
          setUploads((previous) => [...previous, { name, data }]);
          importedConfig = data.config ?? importedConfig;
          importedBoard = data.board ?? importedBoard;
        } catch (reason) {
          failures.push(`${name} — ${reason instanceof Error ? reason.message : "Import failed."}`);
        }
      }
      await refresh();
      if (importedConfig) setConfig(importedConfig);
      if (importedBoard) setBoardName(importedBoard);
      if (failures.length) setError(failures.join("\n"));
    });
  }

  function run(action: Action, target = config) {
    const title = actionLabels[action];
    void task(`${title}…`, async () => {
      setActivity(undefined);
      const result = await post<RunResult>("run", {
        action, config: target, revision, board: action === "pcb" || action === "gerbers" ? boardName : undefined,
      });
      setActivity({ action, title, result, config: target });
      await refresh();
      setConfig(target);
      if (action === "check") {
        setPreferred(target.split("/").pop() ?? "");
        show("checks");
      }
      if (action === "prove") setPreferred("report.json");
      if (result.board) setBoardName(result.board);
      if (action === "design" && result.ok) show("2d");
      if (action === "prove") show("passport");
    });
  }

  function importArduino() {
    void task("Importing the Arduino demo…", async () => {
      const response = await fetch(boardFileUrl(arduinoBoard, arduinoBoard.name));
      if (!response.ok) throw new Error("Could not read the Arduino demo board.");
      const filename = "Jeden-Uno-example.kicad_pcb";
      const file = new File([await response.blob()], filename);
      const imported = await post<Upload>("upload", {
        filename, content_b64: await readFile(file), kind: "pcb",
      });
      if (!imported.board) throw new Error("The backend did not return an imported board.");
      await refresh();
      setBoardName(imported.board);
    });
  }

  const board = boardName === arduinoDemo ? arduinoBoard : workspace?.boards.find((item) => item.name === boardName);
  const demoAvailable = Object.values(demo).every((path) =>
    workspace?.configs.some((item) => item.path === path),
  );
  const previews = workspace?.previews ?? [];
  const evidence = workspace?.artifacts;
  const list = (key: string) => {
    const files = evidence?.[key];
    return typeof files === "string" ? [files] : files ?? [];
  };
  const boardPicker = (id: string, includeDemo = true) => (
    <div>
      <label className="field-label" htmlFor={id}>Board</label>
      <select id={id} value={!includeDemo && board?.demo ? "" : boardName}
        disabled={(!includeDemo && !workspace?.boards.length) || !!busy} onChange={(event) => setBoardName(event.target.value)}>
        {(!workspace?.boards.length || (!includeDemo && board?.demo)) && <option value="">{workspace?.boards.length ? "Select a workspace board" : "No workspace board selected"}</option>}
        {includeDemo && <option value={arduinoDemo}>Jeden Uno (Arduino demo)</option>}
        {workspace?.boards.map((item) => <option key={item.name}>{item.name}</option>)}
      </select>
    </div>
  );
  const actions = (...items: Action[]) => <div className="action-row">{items.map((action) => (
    <button key={action} type="button" className={`button ${action === items[0] ? "button-primary" : "button-secondary"}`}
      onClick={() => run(action)} disabled={!config || !!busy || (action === "pcb" && (!board || board.demo))}>
      {actionLabels[action]}
    </button>
  ))}</div>;
  const boardView = view === "2d" || view === "3d" || view === "schematic" || view === "datasheets";
  const evidenceKey = { checks: "reports", pcb: "pcb_checks", redteam: "red_teams", passport: "passport", diffs: "diffs" } as const;
  const actionView = view === "checks" || view === "pcb" || view === "redteam" || view === "passport";
  const activityView = activity && { check: "checks", design: "2d", pcb: "pcb", prove: "passport", redteam: "redteam", passport: "passport", gerbers: view === "3d" ? "3d" : "2d" }[activity.action];

  return (
    <div className="workspace">
      <a className="skip-link" href="#main-content">Skip to workspace</a>
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="BoardProof home">
          <span className="brand-mark" aria-hidden="true"><span /></span>BoardProof
        </a>
        <nav aria-label="Workspace views">
          {groups.map((group) => (
            <div className="nav-group" key={group.label}>
              <p>{group.label}</p>
              {group.items.map(([id, name, icon]) => (
                <button key={id} aria-current={view === id ? "page" : undefined} onClick={() => show(id)}>
                  <span aria-hidden="true">{icon}</span>{name}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="mobile-nav">
          <label htmlFor="workspace-view">Workspace view</label>
          <select id="workspace-view" value={view} onChange={(event) => show(event.target.value as View)}>
            {groups.map((group) => <optgroup key={group.label} label={group.label}>
              {group.items.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </optgroup>)}
          </select>
        </div>
        <div className="connection"><span className={`local-dot ${workspace ? "" : "offline"}`} />{workspace ? "Workspace connected" : "API disconnected"}</div>
      </aside>

      <main className="shell" id="main-content" tabIndex={-1}>
        <header className="topbar">
          <span>Local workspace</span>
          <button className="button button-secondary" disabled={!!busy} onClick={() => task("Refreshing…", async () => { await refresh(); })}>Refresh workspace</button>
        </header>
        <section className="intro">
          <h1>{view === "overview" ? "PCB workspace" : views.find(([id]) => id === view)?.[1]}</h1>
        </section>

        {error && <p className="notice notice-error" role="alert">{error}</p>}
        {busy && <p className="notice busy-notice" role="status">{busy}</p>}

        {view === "overview" && <>
          <section className="demo-panel arduino-demo" aria-labelledby="arduino-title">
            <div className="demo-copy">
              <p className="demo-kicker">Demo 1</p>
              <h2 id="arduino-title">Jeden Uno</h2>
              <p>Arduino Uno-compatible KiCad board.</p>
              <div className="action-row">
                <button className="button button-primary" onClick={() => { setBoardName(arduinoDemo); show("3d"); }}>Open 3D view</button>
                <button className="button button-secondary" onClick={() => { setBoardName(arduinoDemo); show("2d"); }}>Open 2D view</button>
              </div>
            </div>
            <figure className="demo-board">
              {/* eslint-disable-next-line @next/next/no-img-element -- generated local board illustration */}
              <img src={boardFileUrl(arduinoBoard, arduinoBoard.iso!)} alt="Isometric preview of the Arduino-compatible Jeden Uno board" />
            </figure>
          </section>
          <section className="demo-panel" aria-labelledby="demo-title">
            <div className="demo-copy">
              <p className="demo-kicker">Demo 2</p>
              <h2 id="demo-title">TMP102 temperature sensor</h2>
              <p>Compare a board with wiring errors (Rev B) against the corrected Rev C.</p>
              <div className="action-row">
                <button className="button button-primary" disabled={!demoAvailable || !!busy}
                  onClick={() => run("check", demo.broken)}>Check Rev B</button>
                <button className="button button-secondary" onClick={() => show("import")}>Import a design</button>
              </div>
              {workspace && !demoAvailable && <p className="demo-hint">Start the API from the repository root to load the example configurations.</p>}
            </div>
            <figure className="demo-board">
              {/* eslint-disable-next-line @next/next/no-img-element -- generated local board illustration */}
              <img src="/demo/tmp102-rev-c.svg" alt="Isometric preview of the TMP102 Rev C board" />
              <figcaption>Rev C · Component placement</figcaption>
            </figure>
          </section>
        </>}

        {(view === "overview" || actionView || view === "2d") && (
          <section className="panel target-panel" aria-label="Run controls">
            <div className="target-fields">
              <div>
                <label className="field-label" htmlFor="config">BoardProof configuration</label>
                <select id="config" value={config} onChange={(event) => setConfig(event.target.value)}
                  disabled={!workspace?.configs.length || !!busy}>
                  {!workspace?.configs.length && <option value="">No configurations found</option>}
                  {workspace?.configs.map((item) => <option key={item.path} value={item.path}>{item.path} · {item.rules} rules</option>)}
                </select>
              </div>
              {(view === "pcb" || view === "2d") && boardPicker("active-board", view !== "pcb")}
              {(view === "passport" || view === "overview") && <div>
                <label className="field-label" htmlFor="revision">Revision label (optional)</label>
                <input id="revision" value={revision} maxLength={160} onChange={(event) => setRevision(event.target.value)} />
              </div>}
            </div>
            {view === "overview" && actions("prove", "check", "design")}
            {view === "checks" && actions("check")}
            {view === "2d" && actions("design")}
            {view === "pcb" && actions("pcb")}
            {view === "redteam" && actions("redteam")}
            {view === "passport" && actions("passport")}
          </section>
        )}

        {activity && !busy && (view === activityView || (view === "overview" && !activity.result.ok)) && (
          <details className="panel activity" open>
            <summary><strong>{activity.title}</strong> · {activity.result.ok ? "Completed" : "Review needed"}
              {activity.result.seconds !== undefined && ` · ${activity.result.seconds}s`}</summary>
            <ul className="log-list">{activity.result.log.map((line, i) => <li key={i}>{line}</li>)}</ul>
          </details>
        )}
        {view === "checks" && activity?.config === demo.broken && activity.result.code === 1 && demoAvailable && (
          <section className="panel demo-next">
            <div><h2>Compare with Rev C</h2><p>Generate the Rev C layout and verification report.</p></div>
            <button className="button button-primary" disabled={!!busy}
              onClick={() => run("prove", demo.fixed)}>Run Rev C preflight</button>
          </section>
        )}

        {view === "overview" && (
          <div className="overview-grid">
            <section className="panel overview-preview">
              <div className="section-heading"><h2>Board preview</h2><span>{board?.name ?? "No board selected"}</span></div>
              {board?.top ? <button className="preview-link" onClick={() => show("2d")} aria-label="Open 2D layout">
                {/* eslint-disable-next-line @next/next/no-img-element -- local SVG preview */}
                <img src={`${boardFileUrl(board, board.top)}?v=${version}`} alt={`Top view of ${board.name}`} />
              </button> : <p className="empty-copy">Import or generate a board to see its layout.</p>}
              <div className="action-row">
                <button className="button button-secondary" onClick={() => show("2d")}>Open 2D layout</button>
                <button className="button button-secondary" onClick={() => show("3d")}>Open 3D viewer</button>
              </div>
            </section>
            <section className="panel">
              <div className="section-heading"><h2>Board checks</h2></div>
              <ol className="flow-list">
                <li><button onClick={() => show("import")}>Import a design</button></li>
                <li><button onClick={() => show("checks")}>Check the circuit</button></li>
                <li><button onClick={() => show("pcb")}>Verify the board</button></li>
                <li><button onClick={() => show("passport")}>Review the passport</button></li>
              </ol>
            </section>
          </div>
        )}

        {view === "import" && (
          <section className="panel">
            <form onSubmit={uploadDesign}>
              <label className={`dropzone ${files.length ? "has-file" : ""}`}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  if (!busy) setFiles(Array.from(event.dataTransfer.files));
                }}>
                <span className="file-icon" aria-hidden="true">↑</span>
                <strong>{files.length > 1 ? `${files.length} files selected` : files[0]?.name ?? "Choose or drop design files"}</strong>
                <span>Netlist, KiCad PCB or schematic, photo, or text · up to 8 MB per file</span>
                <input type="file" multiple accept=".enet,.json,.kicad_pcb,.kicad_sch,.txt,.md,.png,.jpg,.jpeg,.webp,.gif"
                  disabled={!!busy} onChange={(event) => {
                    setFiles(Array.from(event.target.files ?? []));
                    event.target.value = "";
                  }} />
              </label>
              {!!files.length && <button className="text-button" type="button" disabled={!!busy} onClick={() => setFiles([])}>Clear selection</button>}
              <label className="field-label brief-label" htmlFor="brief">Design brief (optional with a file)</label>
              <textarea id="brief" rows={3} maxLength={20_000} value={brief} disabled={!!busy}
                onChange={(event) => setBrief(event.target.value)} placeholder="Describe your circuit and components…" />
              <p className="muted">Briefs, photos, and schematics require Gemini. Review generated layouts before fabrication.</p>
              <label className="lookup-toggle">
                <input type="checkbox" checked={fetchDatasheets} disabled={!!busy} onChange={(event) => setFetchDatasheets(event.target.checked)} />
                <span><strong>Look up datasheets</strong><small>Sends part numbers from the netlist to public datasheet sites.</small></span>
              </label>
              <button className="button button-primary" disabled={!!busy || (!files.length && !brief.trim())}>
                {files.length > 1 ? "Import designs" : files.length ? "Import design" : "Generate from brief"}
              </button>
            </form>
            {uploads.map(({ name, data: upload }, index) => (
              <div className="inline-result" role="status" key={`${name}:${index}`}>
                <strong>{upload.board ?? upload.netlist ?? name}</strong>
                <span>{upload.components ?? "—"} components · {upload.nets ?? "—"} nets · {upload.pins ?? "—"} pins</span>
                {upload.config && <small>{upload.draft_rules ?? 0} draft rules. Review them before using them to block a revision.</small>}
                {upload.parts?.length ? <details><summary>Parts and datasheet status</summary>
                  <ul className="log-list">{upload.parts.map((part, i) => <li key={i}>{part.part} · {part.refs.join(", ")} · {part.error ?? part.status}</li>)}</ul>
                </details> : null}
                {!!upload.log?.length && <ul className="log-list">{upload.log.map((line, i) => <li key={i}>{line}</li>)}</ul>}
                <div className="generated-links">{upload.downloads?.map((item) => <a download key={item.file} href={artifactUrl(item.file)}>{item.label} ↓</a>)}</div>
                {upload.board && <div className="action-row">
                  <button className="button button-secondary" disabled={!!busy} onClick={() => { setBoardName(upload.board ?? ""); show("2d"); }}>Open 2D layout</button>
                  <button className="button button-secondary" disabled={!!busy} onClick={() => { setBoardName(upload.board ?? ""); show("3d"); }}>Open 3D viewer</button>
                </div>}
              </div>
            ))}
          </section>
        )}

        {view === "3d" && <section className="panel">{boardPicker("viewer-board")}</section>}
        {(view === "2d" || view === "3d") && board?.demo && workspace && (
          <section className="panel demo-next">
            <div><h2>Jeden Uno sample</h2><p>Import the KiCad file to export Gerbers.</p></div>
            <button className="button button-secondary" disabled={!!busy} onClick={importArduino}>Import demo board</button>
          </section>
        )}
        {boardView && <BoardView mode={view} board={board} previews={previews} version={version} busy={!!busy}
          onExport={board && !board.demo ? () => run("gerbers") : undefined} />}
        {view === "2d" && list("designs").length > 0 && <Evidence files={list("designs")} version={version} />}
        {(actionView || view === "diffs") && (
          <Evidence key={`${view}:${preferred}`} files={list(evidenceKey[view])} preferred={view === "checks" ? preferred : undefined} version={version} />
        )}
        {view === "files" && (
          <section className="panel">
            <label className="field-label" htmlFor="file-search">Filter artifacts</label>
            <input id="file-search" type="search" value={fileSearch} onChange={(event) => setFileSearch(event.target.value)} placeholder="Search by filename" />
            <div className="artifact-list">
              {workspace?.files.filter((name) => name.toLowerCase().includes(fileSearch.toLowerCase())).map((name) => (
                <a className="artifact-row" key={name} href={artifactUrl(name)} download>
                  <span className="artifact-type">{name.split(".").pop()?.toUpperCase()}</span>
                  <span className="artifact-name">{name}</span><span className="artifact-action">Download ↓</span>
                </a>
              ))}
              {!workspace?.files.some((name) => name.toLowerCase().includes(fileSearch.toLowerCase())) && <p className="empty-copy">No matching artifacts.</p>}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
