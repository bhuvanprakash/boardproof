"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { arduinoBoard, artifactUrl, boardFileUrl, BoardView, type Board } from "./board-view";
import { DatasheetsView, SchematicView, warmDatasheets, warmPreviews } from "./design-reference-views";
import { Evidence } from "./evidence";
import { OverviewDashboard, type RulePackSummary, type RunSummary } from "./overview-dashboard";

const groups = [
  { label: "Workspace", items: [["overview", "Overview", "⌂"], ["runs", "Runs", "◷"], ["rules", "Rule packs", "▤"], ["compatibility", "Compatibility", "⌁"], ["import", "Import design", "↑"], ["checks", "Circuit checks", "✓"]] },
  { label: "Board", items: [["2d", "2D layout", "▤"], ["3d", "3D viewer", "◇"], ["schematic", "Schematic", "⌘"], ["datasheets", "Datasheets", "▧"]] },
  { label: "Evidence", items: [["pcb", "PCB verification", "◎"], ["redteam", "Red team", "⚑"], ["passport", "Preflight passport", "▣"], ["diffs", "Revision history", "↔"], ["files", "Artifacts", "↓"], ["search", "Search", "⌕"]] },
] as const;
type View = (typeof groups)[number]["items"][number][0];
const views = groups.flatMap(({ items }) => [...items]);
const primaryViews = ["overview", "runs", "rules", "compatibility", "redteam", "passport"] as const;
const arduinoDemo = "demo:arduino";
const demo = {
  broken: "examples/tmp102/boardproof.rev-b-failure.json",
  fixed: "examples/tmp102/boardproof.rev-c-fixed.json",
};
type Workspace = {
  configs: { path: string; rules: number }[];
  rule_packs: RulePackSummary[];
  runs: RunSummary[];
  board: string | null;
  boards: Board[];
  previews: string[];
  preview_stats?: { schematic: number; datasheets: number };
  files: string[];
  artifacts: Record<string, string[] | string | null>;
};
type Action = "check" | "design" | "pcb" | "prove" | "redteam" | "passport" | "gerbers" | "diff";
const actionLabels: Record<Action, string> = {
  check: "Run hardware check", design: "Generate board", pcb: "Verify board",
  prove: "Run preflight", redteam: "Run red team", passport: "Build passport",
  gerbers: "Export Gerbers", diff: "Compare reports",
};
type RunResult = { ok: boolean; code: number; log: string[]; seconds?: number; board?: string; file?: string };
type Upload = {
  kind?: string; config?: string; firmware?: string; board?: string; netlist?: string; components?: number; nets?: number; pins?: number;
  draft_rules?: number; downloads?: { label: string; file: string }[];
  parts?: { part: string; refs: string[]; status: string; error?: string }[];
  log?: string[]; next?: string[];
};
type Activity = { action: Action; title: string; result: RunResult; config: string; view?: View };

const viewDescriptions: Record<View, string> = {
  overview: "Review the latest evidence and choose what to check next.",
  runs: "Review saved checks and open the findings attached to each run.",
  rules: "Inspect the configurations and rule sources used by BoardProof.",
  compatibility: "Review the firmware and circuit findings the current rules can verify.",
  import: "Import a KiCad board, netlist, or firmware source, or start with a design brief.",
  checks: "Run circuit checks and compare reports.",
  "2d": "Inspect the board outline, component placement, pads, and traces.",
  "3d": "Rotate the board. Component shapes are approximate.",
  schematic: "Inspect sheets generated from the checked netlist.",
  datasheets: "Check datasheet sources, hashes, and cited pages.",
  pcb: "Check footprints, net connections, and board rules.",
  redteam: "Run test faults to see whether PCB rules detect them.",
  passport: "Review the checks, source files, and status for this preflight.",
  diffs: "Compare two reports to see which findings changed.",
  files: "View and download boards, reports, previews, and exports.",
  search: "Search saved findings, rule configurations, and workspace files.",
};

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

export default function Workbench({ email, onSignOut }: { email: string; onSignOut: () => void }) {
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
  const [baseReport, setBaseReport] = useState("");
  const [headReport, setHeadReport] = useState("");
  const [revision, setRevision] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [fileSearch, setFileSearch] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

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
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  // Hovering or focusing a view warms its data, so the click paints immediately.
  const warm = (id: View) => {
    if (id === "schematic") warmPreviews();
    else if (id === "datasheets") warmDatasheets();
  };
  const navCount = (id: View) => {
    const stats = workspace?.preview_stats;
    if (!stats) return "";
    if (id === "schematic") return stats.schematic ? String(stats.schematic) : "";
    if (id === "datasheets") return stats.datasheets ? String(stats.datasheets) : "";
    return "";
  };

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
      const selectedFiles = files.length
        ? files.slice().sort((left, right) => Number(/\.(?:h|ino|c|cc|cpp)$/i.test(left.name)) - Number(/\.(?:h|ino|c|cc|cpp)$/i.test(right.name)))
        : [undefined];
      for (const file of selectedFiles) {
        const name = file?.name ?? "brief.txt";
        try {
          if (file && file.size > 8 * 1024 * 1024) throw new Error("File exceeds 8 MB.");
          const firmware = !!file && /\.(?:h|ino|c|cc|cpp)$/i.test(file.name);
          const firmwareConfig = importedConfig || config;
          if (firmware && !firmwareConfig) throw new Error("Select a BoardProof configuration before attaching firmware.");
          const data = await post<Upload>("upload", {
            filename: name, content_b64: file ? await readFile(file) : undefined,
            brief, fetch_datasheets: fetchDatasheets,
            ...(firmware ? { kind: "firmware", config_path: firmwareConfig } : {}),
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

  function run(action: Action, target = config, destination?: View) {
    const title = actionLabels[action];
    void task(`${title}…`, async () => {
      setActivity(undefined);
      const result = await post<RunResult>("run", {
        action, config: action === "diff" ? undefined : target, revision,
        board: action === "pcb" || action === "gerbers"
          ? boardName
          : action === "passport" && workspace?.boards.some((item) => item.name === boardName)
            ? boardName
            : undefined,
        base: action === "diff" ? selectedBase : undefined,
        head: action === "diff" ? selectedHead : undefined,
      });
      setActivity({ action, title, result, config: target, view: destination });
      await refresh();
      if (action !== "diff") setConfig(target);
      if (action === "check") {
        setPreferred(result.file ?? target.split("/").pop() ?? "");
        show(destination ?? "checks");
      }
      if (action === "diff") {
        if (result.file) setPreferred(result.file);
        show("diffs");
      }
      if (action === "prove") setPreferred("report.json");
      if (result.board) setBoardName(result.board);
      if (action === "design" && result.ok) show("2d");
      if (action === "prove") show(destination ?? "passport");
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
  const boardPreviewUrl = board?.top ? `${boardFileUrl(board, board.top)}?v=${version}` : undefined;
  const demoAvailable = Object.values(demo).every((path) =>
    workspace?.configs.some((item) => item.path === path),
  );
  const evidence = workspace?.artifacts;
  const list = (key: string) => {
    const files = evidence?.[key];
    return typeof files === "string" ? [files] : files ?? [];
  };
  const reports = list("reports");
  const selectedBase = reports.includes(baseReport) ? baseReport : reports[0] ?? "";
  const selectedHead = reports.includes(headReport) && headReport !== selectedBase
    ? headReport : reports.find((file) => file !== selectedBase) ?? "";
  const searchResults = (() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    if (!query || !workspace) return [];
    const matches: { kind: string; title: string; detail: string; view: View; value?: string; file?: string }[] = [];
    for (const item of workspace.configs) {
      if (item.path.toLocaleLowerCase().includes(query)) matches.push({ kind: "Configuration", title: item.path, detail: `${item.rules} rules`, view: "rules", value: item.path });
    }
    for (const pack of workspace.rule_packs) {
      for (const rule of pack.rules) {
        const detail = [rule.type, rule.component, rule.pin, rule.net, rule.status].filter(Boolean).join(" ");
        if (`${rule.id} ${detail}`.toLocaleLowerCase().includes(query)) {
          matches.push({ kind: "Rule", title: rule.id, detail: `${pack.path} · ${detail}`, view: "rules", value: pack.path });
        }
      }
    }
    for (const run of workspace.runs) {
      for (const finding of run.findings) {
        const detail = `${finding.code} ${finding.message} ${finding.component} ${finding.pin} ${finding.net}`;
        if (detail.toLocaleLowerCase().includes(query)) matches.push({ kind: "Finding", title: finding.message || finding.code, detail: `${run.file} · ${finding.severity}`, view: "runs", file: run.file });
      }
    }
    for (const file of workspace.files) {
      if (file.toLocaleLowerCase().includes(query)) matches.push({ kind: "File", title: file, detail: "Workspace artifact", view: "files", value: file });
    }
    return matches.slice(0, 60);
  })();
  const boardPicker = (id: string, includeDemo = true, emptyLabel?: string) => {
    const selectedWorkspaceBoard = workspace?.boards.some((item) => item.name === boardName) ?? false;
    const pickerValue = includeDemo || selectedWorkspaceBoard ? boardName : "";
    return (
    <div>
      <label className="field-label" htmlFor={id}>Board</label>
      <select id={id} value={pickerValue}
        disabled={(!includeDemo && !workspace?.boards.length) || !!busy} onChange={(event) => setBoardName(event.target.value)}>
        {(!workspace?.boards.length || (!includeDemo && !selectedWorkspaceBoard)) && <option value="">{emptyLabel ?? (workspace?.boards.length ? "Select a workspace board" : "No workspace board selected")}</option>}
        {includeDemo && <option value={arduinoDemo}>Jeden Uno (Arduino demo)</option>}
        {workspace?.boards.map((item) => <option key={item.name}>{item.name}</option>)}
      </select>
    </div>
    );
  };
  const actions = (...items: Action[]) => <div className="action-row">{items.map((action) => (
    <button key={action} type="button" className={`button ${action === items[0] ? "button-primary" : "button-secondary"}`}
      onClick={() => run(action)} disabled={!config || !!busy || (action === "pcb" && (!board || board.demo))}>
      {actionLabels[action]}
    </button>
  ))}</div>;
  const boardView = view === "2d" || view === "3d";
  const evidenceKey = { checks: "reports", compatibility: "reports", pcb: "pcb_checks", redteam: "red_teams", passport: "passport", diffs: "diffs", runs: "reports" } as const;
  const actionView = view === "checks" || view === "compatibility" || view === "pcb" || view === "redteam" || view === "passport";
  const activityView = activity && (activity.view ?? { check: "checks", design: "2d", pcb: "pcb", prove: "passport", redteam: "redteam", passport: "passport", gerbers: view === "3d" ? "3d" : "2d", diff: "diffs" }[activity.action]);

  return (
    <div className="workspace" data-view={view}>
      <a className="skip-link" href="#main-content">Skip to workspace</a>
      <header className="app-header">
        <a className="brand" href="/" aria-label="BoardProof home">
          <span className="brand-mark" aria-hidden="true"><span /></span>BoardProof
        </a>
        <nav className="product-nav" aria-label="Main sections">
          {views.filter(([id]) => (primaryViews as readonly string[]).includes(id)).map(([id, name]) => (
            <a key={id} href={`#${id}`} aria-current={view === id ? "page" : undefined}
              onClick={(event) => { event.preventDefault(); show(id); }}>{name}</a>
          ))}
        </nav>
        <form className="workspace-search" role="search" onSubmit={(event) => { event.preventDefault(); show("search"); }}>
          <label className="sr-only" htmlFor="workspace-search">Search findings, rules, and files</label>
          <span aria-hidden="true">⌕</span>
          <input id="workspace-search" type="search" value={searchQuery} maxLength={200}
            onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search findings, rules, files" />
        </form>
        <details className="tools-menu">
          <summary>Tools <span aria-hidden="true">⌄</span></summary>
          <div className="tools-menu-content">
            {groups.map((group) => {
              const items = group.items.filter(([id]) => !(primaryViews as readonly string[]).includes(id));
              return items.length > 0 && <div className="tools-menu-group" key={group.label}>
                <span>{group.label}</span>
                {items.map(([id, name, icon]) => <a key={id} href={`#${id}`} aria-current={view === id ? "page" : undefined}
                  onMouseEnter={() => warm(id)} onFocus={() => warm(id)}
                  onClick={(event) => { event.preventDefault(); show(id); }}>{icon} {name}</a>)}
              </div>;
            })}
          </div>
        </details>
        <details className="profile-menu">
          <summary aria-label={`Account: ${email}`}><span className="profile-avatar">{email.slice(0, 1).toUpperCase() || "B"}</span><span className="profile-email">{email}</span></summary>
          <div><strong>{email}</strong><button type="button" onClick={onSignOut}>Sign out</button></div>
        </details>
      </header>

      <main className="shell" id="main-content" tabIndex={-1}>
        <header className="topbar">
          <span><i className={`local-dot ${workspace ? "" : "offline"}`} />{workspace ? "Workspace connected" : "API disconnected"}</span>
          <button className="button button-secondary" disabled={!!busy} onClick={() => task("Refreshing…", async () => { await refresh(); })}>Refresh workspace</button>
        </header>
        <section className="intro">
          <h1>{views.find(([id]) => id === view)?.[1]}</h1>
          <p>{viewDescriptions[view]}</p>
        </section>

        {error && <p className="notice notice-error" role="alert">{error}</p>}
        {busy && <p className="notice busy-notice" role="status">{busy}</p>}

        {(actionView || view === "2d" || view === "schematic") && (
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
              {view === "passport" && <div className="target-board-field">
                {boardPicker("passport-board", false, "Use latest workspace board")}
                <p className="lookup-hint">Passport evidence will use this board. Leave the default to use the latest workspace board.</p>
              </div>}
              {(view === "passport" || view === "checks") && <div>
                <label className="field-label" htmlFor="revision">Revision label (optional)</label>
                <input id="revision" value={revision} maxLength={160} placeholder="e.g. Rev A" onChange={(event) => setRevision(event.target.value)} />
              </div>}
            </div>
            {view === "checks" && actions("check")}
            {view === "compatibility" && <button type="button" className="button button-primary" disabled={!config || !!busy}
              onClick={() => run("check", config, "compatibility")}>Check compatibility</button>}
            {view === "2d" && actions("design")}
            {view === "schematic" && actions("prove")}
            {view === "pcb" && actions("pcb")}
            {view === "redteam" && actions("redteam")}
            {view === "passport" && actions("passport")}
          </section>
        )}

        {activity && !busy && view === activityView && (
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

        {view === "overview" && workspace && <OverviewDashboard board={board} boardPreviewUrl={boardPreviewUrl}
          config={config} configs={workspace.configs} rulePacks={workspace.rule_packs} runs={workspace.runs}
          busy={!!busy} onNavigate={(next) => show(next as View)} onRunChecks={() => run("check", config)}
          onSelectConfig={setConfig} onOpenArduino={() => { setBoardName(arduinoDemo); show("3d"); }}
          onRunRevB={() => run("check", demo.broken)} demoAvailable={demoAvailable} />}
        {view === "overview" && !workspace && <section className="panel loading-state" role="status">Connecting to the BoardProof API…</section>}

        {view === "runs" && <section className="panel run-history">
          <div className="section-heading"><div><h2>Saved runs</h2><p>Each result links to the report that was written by the Python checker.</p></div>
            <button className="button button-primary" disabled={!config || !!busy} onClick={() => run("check", config, "runs")}>Run a check</button></div>
          {workspace?.runs.length ? <div className="run-list">{workspace.runs.map((runItem) => <article className="run-row" key={runItem.file}>
            <div className="run-row-main"><span className={`run-status status-${runItem.status}`}>{runItem.status}</span>
              <strong>{runItem.file}</strong><small>{runItem.config || "Configuration not recorded"} · {new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(runItem.updated_at))}</small></div>
            <div className="run-row-counts"><span className="count-error">{runItem.counts.error} errors</span><span>{runItem.counts.warning} warnings</span><span>{runItem.counts.info} info</span></div>
            <button className="text-button" onClick={() => setPreferred(runItem.file)}>View report →</button>
          </article>)}</div> : <div className="empty-state"><strong>No saved runs yet</strong><p>Run a hardware check to save the first report here.</p><button className="button button-secondary" disabled={!config || !!busy} onClick={() => run("check", config, "runs")}>Run a check</button></div>}
        </section>}

        {view === "rules" && <section className="rule-pack-list">
          <div className="rules-toolbar panel"><div><h2>Rule configurations</h2><p>Review the checks that are available in this workspace.</p></div>
            <button className="button button-primary" onClick={() => show("import")}>Import a design</button></div>
          {workspace?.rule_packs.length ? workspace.rule_packs.map((pack) => <article className={`overview-card rule-pack-detail ${config === pack.path ? "rule-pack-selected" : ""}`} key={pack.path}>
            <div className="card-heading"><div><h3>{pack.path.split("/").pop()}</h3><p>{pack.path} · {pack.netlist || "Netlist not recorded"}</p></div>
              <span className="status-not-recorded">Approval: {pack.status}</span></div>
            <div className="rule-pack-summary"><strong>{pack.rules.length}</strong><span>rules</span><span>Rule approval is not inferred when it is missing from the source.</span>
              <button className="button button-secondary" onClick={() => { setConfig(pack.path); show("checks"); }}>Use in checks</button></div>
            <div className="rules-table-wrap"><table className="rules-table"><thead><tr><th>Rule</th><th>Type</th><th>Severity</th><th>Target</th><th>Source</th></tr></thead>
              <tbody>{pack.rules.map((rule) => <tr key={rule.id}><td><strong>{rule.id}</strong><small>{rule.status}</small></td><td>{rule.type}</td><td>{rule.severity}</td>
                <td>{[rule.component, rule.pin && `pin ${rule.pin}`, rule.net && `net ${rule.net}`].filter(Boolean).join(" · ") || "Not specified"}</td>
                <td>{rule.citation ? [rule.citation.source, rule.citation.page && `p. ${rule.citation.page}`].filter(Boolean).join(" · ") : "No citation recorded"}</td></tr>)}</tbody>
            </table></div>
          </article>) : <div className="empty-state"><strong>No rule configurations found</strong><p>Import a supported design or add a BoardProof configuration to the workspace.</p><button className="button button-secondary" onClick={() => show("import")}>Import design</button></div>}
        </section>}

        {view === "compatibility" && <section className="compatibility-grid">
          <article className="overview-card compatibility-summary">
            <div className="card-heading"><h2>Firmware and circuit compatibility</h2><span>{workspace?.runs[0]?.file ?? "No run selected"}</span></div>
            <p>Compatibility findings come from explicit rules in the selected configuration. BoardProof does not infer a GPIO mapping from a net name.</p>
            {(() => {
              const latest = workspace?.runs[0];
              const relevant = latest?.findings.filter((finding) => /firmware|gpio|i2c|sda|scl/i.test(`${finding.code} ${finding.message}`)) ?? [];
              return latest ? relevant.length ? <ul className="attention-list">{relevant.map((finding, index) => <li key={`${finding.code}:${index}`}>
                <span className={`finding-mark finding-${finding.severity || "unknown"}`} aria-hidden="true">{finding.severity === "error" ? "×" : finding.severity === "warning" ? "!" : "?"}</span>
                <div><strong>{finding.message || finding.code}</strong><small>{[finding.code, finding.component, finding.pin && `pin ${finding.pin}`, finding.net && `net ${finding.net}`].filter(Boolean).join(" · ")}</small></div>
              </li>)}</ul> : <div className="compatibility-unknown"><span>?</span><div><strong>No firmware-specific finding in this report</strong><p>The report does not store per-rule passes, so this cannot be counted as a compatibility pass.</p></div></div>
                : <div className="empty-state"><strong>No report to inspect</strong><p>Run a check after selecting a configuration with firmware rules.</p></div>;
            })()}
            <div className="compatibility-actions"><button className="button button-primary" disabled={!config || !!busy} onClick={() => run("check", config, "compatibility")}>Check selected configuration</button>
              <button className="button button-secondary" onClick={() => show("import")}>Import firmware or design files</button></div>
          </article>
          <article className="overview-card compatibility-notes"><h3>What the checker can report</h3>
            <ul><li>Simple numeric firmware <code>#define</code> values referenced by configured GPIO rules.</li><li>Pin and net rules present in the selected configuration.</li><li>Unsupported macros remain unresolved and need review.</li></ul>
            <p className="result-note">A clean report only covers the rules it ran. It does not prove full board and firmware compatibility.</p></article>
        </section>}

        {view === "search" && <section className="panel search-results-panel">
          <div className="section-heading"><div><h2>Search results</h2><p>Findings, rules, configurations, and artifacts in this workspace.</p></div><span>{searchResults.length} shown</span></div>
          {!searchQuery.trim() ? <div className="empty-state"><strong>Search this workspace</strong><p>Enter a finding, rule ID, configuration, or filename in the search box above.</p></div>
            : searchResults.length ? <div className="artifact-list">{searchResults.map((result, index) => <button className="search-result" key={`${result.kind}:${result.title}:${index}`} onClick={() => {
              if (result.value && result.view === "rules") setConfig(result.value);
              if (result.value && result.view === "files") setFileSearch(result.value);
              if (result.file) setPreferred(result.file);
              show(result.view);
            }}><span>{result.kind}</span><strong>{result.title}</strong><small>{result.detail}</small><span aria-hidden="true">→</span></button>)}</div>
              : <div className="empty-state"><strong>No matches for “{searchQuery}”</strong><p>Try a finding code, rule type, or part of a filename.</p></div>}
        </section>}

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
                <span>Netlist, KiCad PCB or schematic, firmware source, photo, or text · up to 8 MB per file</span>
                <input type="file" multiple accept=".enet,.json,.kicad_pcb,.kicad_sch,.h,.ino,.c,.cc,.cpp,.txt,.md,.png,.jpg,.jpeg,.webp,.gif"
                  disabled={!!busy} onChange={(event) => {
                    setFiles(Array.from(event.target.files ?? []));
                    event.target.value = "";
                  }} />
              </label>
              {!!files.length && <button className="text-button" type="button" disabled={!!busy} onClick={() => setFiles([])}>Clear selection</button>}
              {files.some((file) => /\.(?:h|ino|c|cc|cpp)$/i.test(file.name)) && <div className="firmware-config">
                <label className="field-label" htmlFor="firmware-config">Attach firmware to this configuration</label>
                <select id="firmware-config" value={config} disabled={!workspace?.configs.length || !!busy}
                  onChange={(event) => setConfig(event.target.value)}>
                  {workspace?.configs.map((item) => <option key={item.path} value={item.path}>{item.path}</option>)}
                  {!workspace?.configs.length && <option value="">Import a design first</option>}
                </select>
                <p className="lookup-hint">When you import a design with firmware, it attaches to the new configuration. Firmware checks currently read simple numeric #define values in configured GPIO rules.</p>
              </div>}
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
                <strong>{upload.kind === "firmware" ? `Firmware attached: ${name}` : upload.board ?? upload.netlist ?? name}</strong>
                {upload.kind !== "firmware" && <span>{upload.components ?? "—"} components · {upload.nets ?? "—"} nets · {upload.pins ?? "—"} pins</span>}
                {upload.kind === "firmware" && upload.config && <small>Attached to {upload.config}. Run a check to evaluate configured firmware GPIO rules.</small>}
                {upload.kind !== "firmware" && upload.config && <small>{upload.draft_rules ?? 0} draft rules. Review them before using them to block a revision.</small>}
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
        {boardView && <BoardView mode={view} board={board} version={version} busy={!!busy}
          onExport={board && !board.demo ? () => run("gerbers") : undefined} />}
        {view === "schematic" && <SchematicView version={version} busy={!!busy}
          onGenerate={() => run("prove", config, "schematic")} />}
        {view === "datasheets" && <DatasheetsView version={version} busy={!!busy} />}
        {view === "2d" && list("designs").length > 0 && <Evidence files={list("designs")} version={version} />}
        {view === "diffs" && <section className="panel revision-compare">
          <div className="section-heading"><h2>Compare saved checks</h2></div>
          {reports.length >= 2 ? <>
            <div className="target-fields">
              <div>
                <label className="field-label" htmlFor="base-report">Earlier report</label>
                <select id="base-report" value={selectedBase} disabled={!!busy}
                  onChange={(event) => setBaseReport(event.target.value)}>
                  {reports.map((file) => <option key={file} value={file}>{file}</option>)}
                </select>
              </div>
              <div>
                <label className="field-label" htmlFor="head-report">Later report</label>
                <select id="head-report" value={selectedHead} disabled={!!busy}
                  onChange={(event) => setHeadReport(event.target.value)}>
                  {reports.filter((file) => file !== selectedBase).map((file) => <option key={file} value={file}>{file}</option>)}
                </select>
              </div>
            </div>
            <button className="button button-primary" disabled={!!busy || !selectedBase || !selectedHead}
              onClick={() => run("diff")}>{actionLabels.diff}</button>
          </> : <p className="empty-copy">Run checks on two configurations, or label each run on Circuit checks to save two revisions here.</p>}
        </section>}
        {(actionView || view === "diffs" || view === "runs") && (
          <Evidence key={`${view}:${preferred}`} files={list(evidenceKey[view])} preferred={view === "checks" || view === "diffs" || view === "runs" ? preferred : undefined} version={version} />
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
