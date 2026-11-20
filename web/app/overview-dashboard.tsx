import type { Board } from "./board-view";

export type RunSummary = {
  file: string;
  status: string;
  config: string;
  updated_at: string;
  counts: { error: number; warning: number; info: number };
  findings: { severity: string; code: string; message: string; component: string; pin: string; net: string }[];
};

export type RuleSummary = {
  id: string;
  type: string;
  severity: string;
  component: string;
  pin: string;
  net: string;
  status: string;
  citation: { page?: number; quote?: string; source?: string } | null;
};

export type RulePackSummary = {
  path: string;
  netlist: string;
  status: string;
  rules: RuleSummary[];
};

type Props = {
  board?: Board;
  boardPreviewUrl?: string;
  config: string;
  configs: { path: string; rules: number }[];
  rulePacks: RulePackSummary[];
  runs: RunSummary[];
  busy: boolean;
  onNavigate: (view: string) => void;
  onRunChecks: () => void;
  onSelectConfig: (path: string) => void;
  onOpenArduino: () => void;
  onRunRevB: () => void;
  demoAvailable: boolean;
};

const moneyDate = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium", timeStyle: "short",
  }).format(date);
};

function CircuitIllustration() {
  return (
    <svg className="circuit-illustration" viewBox="0 0 700 360" role="img" aria-labelledby="circuit-title circuit-desc">
      <title id="circuit-title">TMP102 circuit check illustration</title>
      <desc id="circuit-desc">The sensor supply is connected to five volts and fails the three point three volt rule. The SDA pull-up passes and the firmware pin mapping remains unknown.</desc>
      <defs>
        <linearGradient id="circuit-wash" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#f5fbf7" />
          <stop offset="1" stopColor="#e0edf5" />
        </linearGradient>
        <pattern id="circuit-dots" width="20" height="20" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1" fill="#bdcec6" opacity=".55" />
        </pattern>
      </defs>
      <rect width="700" height="360" rx="22" fill="url(#circuit-wash)" />
      <rect width="700" height="360" rx="22" fill="url(#circuit-dots)" />
      <g fill="none" stroke="#a47a3d" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M0 80h115l32 32h111" />
        <path d="M0 156h158l36 36h64" />
        <path d="M0 257h113l29-29h116" />
        <path d="M436 88h60l34-34h170" />
        <path d="M436 168h264" />
        <path d="M436 249h74l32 32h188" />
      </g>
      <g fill="none" stroke="#b64345" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M0 80h115l32 32h111" />
      </g>
      <g fill="none" stroke="#13846b" strokeWidth="4" strokeDasharray="3 9" strokeLinecap="round">
        <path d="M436 168h264" />
      </g>
      <g fill="#fff" stroke="#a47a3d" strokeWidth="4">
        <circle cx="147" cy="112" r="8" /><circle cx="113" cy="257" r="8" />
        <circle cx="530" cy="54" r="8" /><circle cx="542" cy="281" r="8" />
      </g>
      <rect x="267" y="70" width="170" height="205" rx="18" fill="#f5faf7" stroke="#936c34" strokeWidth="4" />
      <rect x="282" y="86" width="140" height="173" rx="12" fill="none" stroke="#d4e0d9" strokeWidth="2" />
      <circle cx="300" cy="105" r="5" fill="#a47a3d" />
      <text x="352" y="161" textAnchor="middle" className="circuit-chip-ref">U1</text>
      <text x="352" y="187" textAnchor="middle" className="circuit-chip-name">TMP102</text>
      <g className="circuit-callout circuit-callout-fail">
        <rect x="25" y="36" width="174" height="34" rx="17" />
        <text x="112" y="58" textAnchor="middle">V+ → 5V · FAIL</text>
      </g>
      <g className="circuit-callout circuit-callout-pass">
        <rect x="26" y="273" width="186" height="34" rx="17" />
        <text x="119" y="295" textAnchor="middle">SDA pull-up · PASS</text>
      </g>
      <g className="circuit-callout circuit-callout-unknown">
        <rect x="492" y="185" width="189" height="34" rx="17" />
        <text x="586" y="207" textAnchor="middle">GPIO mapping · UNKNOWN</text>
      </g>
    </svg>
  );
}

function NetDiagram() {
  return (
    <svg className="net-diagram" viewBox="0 0 720 320" role="img" aria-labelledby="net-title net-desc">
      <title id="net-title">Example sensor connections</title>
      <desc id="net-desc">A power input connects to a TMP102 sensor and a microcontroller. The 5 volt supply is highlighted as a failed rule. SDA and SCL pin mapping is unknown.</desc>
      <defs>
        <pattern id="net-dots" width="18" height="18" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1" fill="#b8cbc1" opacity=".65" />
        </pattern>
      </defs>
      <rect width="720" height="320" rx="12" fill="#f2f8f4" />
      <rect width="720" height="320" rx="12" fill="url(#net-dots)" />
      <g fill="none" stroke="#567969" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
        <path d="M108 144h130" /><path d="M362 120h145" /><path d="M362 191h145" />
        <path d="M240 237h-83v42" /><path d="M533 71v-32h111" />
      </g>
      <path d="M108 144h130" fill="none" stroke="#bd4146" strokeWidth="6" strokeLinecap="round" />
      <path d="M362 120h145M362 191h145" fill="none" stroke="#7462bc" strokeWidth="4" strokeDasharray="8 7" />
      <rect x="28" y="111" width="80" height="68" rx="11" fill="#fff" stroke="#9b743c" strokeWidth="3" />
      <text x="68" y="139" textAnchor="middle" className="diagram-label">J1</text>
      <text x="68" y="158" textAnchor="middle" className="diagram-small">POWER</text>
      <rect x="238" y="75" width="124" height="158" rx="15" fill="#fff" stroke="#9b743c" strokeWidth="3" />
      <text x="300" y="123" textAnchor="middle" className="diagram-label">U1</text>
      <text x="300" y="144" textAnchor="middle" className="diagram-small">TMP102</text>
      <text x="253" y="171" className="diagram-small">V+</text>
      <text x="253" y="209" className="diagram-small">GND</text>
      <text x="334" y="121" className="diagram-small">SDA</text>
      <text x="334" y="192" className="diagram-small">SCL</text>
      <rect x="507" y="80" width="170" height="149" rx="15" fill="#fff" stroke="#9b743c" strokeWidth="3" />
      <text x="592" y="144" textAnchor="middle" className="diagram-label">MCU</text>
      <text x="592" y="166" textAnchor="middle" className="diagram-small">GPIO ?</text>
      <rect x="132" y="180" width="101" height="36" rx="18" fill="#fdebed" stroke="#df9da0" />
      <text x="182" y="203" textAnchor="middle" className="diagram-pill-fail">5V · FAIL</text>
      <circle cx="439" cy="120" r="12" fill="#f2efff" stroke="#9b8bdb" strokeWidth="2" />
      <circle cx="439" cy="191" r="12" fill="#f2efff" stroke="#9b8bdb" strokeWidth="2" />
      <text x="439" y="125" textAnchor="middle" className="diagram-unknown">?</text>
      <text x="439" y="196" textAnchor="middle" className="diagram-unknown">?</text>
      <path d="M157 279v14m-13 0h26m-21 7h16m-11 7h6" stroke="#567969" strokeWidth="3" strokeLinecap="round" />
      <text x="142" y="270" className="diagram-small">GND</text>
    </svg>
  );
}

export function OverviewDashboard({ board, boardPreviewUrl, config, configs, rulePacks, runs, busy, onNavigate, onRunChecks, onSelectConfig, onOpenArduino, onRunRevB, demoAvailable }: Props) {
  const latest = runs[0];
  const selectedPack = rulePacks.find((pack) => pack.path === config);
  const findings = latest?.findings.slice(0, 3) ?? [];
  const ruleCount = selectedPack?.rules.length ?? configs.find((item) => item.path === config)?.rules ?? 0;
  const status = latest?.status.toLowerCase() ?? "no runs yet";

  return (
    <div className="product-overview">
      <section className="overview-hero">
        <div className="overview-hero-copy">
          <p className="eyebrow">Circuit board verification</p>
          <h2>Check your board before you build it.</h2>
          <p>Check connections, component rules, and firmware pins before a revision. Each finding shows which rule triggered it.</p>
          <div className="overview-hero-actions">
            <button className="button button-primary" onClick={() => onNavigate("import")}>Import design <span aria-hidden="true">↑</span></button>
            <button className="button button-secondary" disabled={busy || !config} onClick={onRunChecks}><span aria-hidden="true">▷</span> Run checks</button>
          </div>
          <div className="trust-pills" aria-label="How checks run">
            <span>Deterministic checks</span><span>Runs locally</span><span>Approval status stays explicit</span>
          </div>
        </div>
        <div className="overview-hero-visual"><CircuitIllustration /></div>
      </section>

      <section className="overview-steps" aria-labelledby="steps-heading">
        <div className="overview-section-title"><h2 id="steps-heading">How a board gets checked</h2><span>4 steps</span></div>
        <div className="steps-grid">
          {[
            ["01", "Import", "Load a netlist, KiCad board, or firmware file."],
            ["02", "Review rules", "Check each rule, severity, citation, and saved approval."],
            ["03", "Run checks", "The offline engine compares the design with its rules."],
            ["04", "Keep the record", "Compare reports and review the passport scope."],
          ].map(([number, title, body]) => <article className="step-card" key={number}>
            <span className="step-number">{number}</span><h3>{title}</h3><p>{body}</p>
          </article>)}
        </div>
      </section>

      <section className="overview-section" aria-labelledby="latest-run-heading">
        <div className="overview-section-title"><h2 id="latest-run-heading">Latest run</h2>
          {latest && <span className={`run-tag status-${status.replaceAll(" ", "-")}`}>{latest.file}</span>}
        </div>
        <div className="latest-run-grid">
          <article className="overview-card connection-card">
            <div className="card-heading"><h3>TMP102 connection example</h3><span>Illustrative wiring</span></div>
            <NetDiagram />
            <div className="diagram-legend"><span className="legend-pass">pass · checked</span><span className="legend-fail">fail · rule broken</span><span className="legend-unknown">unknown · cannot verify</span></div>
          </article>
          <article className="overview-card run-result-card">
            <div className="card-heading"><h3>Result</h3>{latest && <span>{moneyDate(latest.updated_at)}</span>}</div>
            {latest ? <>
              <div className="result-metrics" aria-label="Latest run summary">
                <div className="metric metric-errors"><strong>{latest.counts.error}</strong><span>Errors</span></div>
                <div className="metric metric-warnings"><strong>{latest.counts.warning}</strong><span>Warnings</span></div>
                <div className="metric metric-info"><strong>{latest.counts.info}</strong><span>Info</span></div>
              </div>
              <p className="result-note">A missing finding is not proof that an unconfigured rule passed.</p>
              <div className={`run-state ${latest.status === "passed" ? "run-state-pass" : "run-state-fail"}`}>
                <span aria-hidden="true">{latest.status === "passed" ? "✓" : "!"}</span>
                <div><strong>{latest.status === "passed" ? "Checks passed" : `${latest.counts.error} error(s) need review`}</strong><small>{latest.config || "Configuration not recorded"}</small></div>
              </div>
              <button className="text-button overview-link" onClick={() => onNavigate("runs")}>Open run history →</button>
            </> : <div className="empty-run"><p>No saved check runs yet.</p><button className="button button-secondary" onClick={onRunChecks} disabled={busy || !config}>Run the first check</button></div>}
            <div className="scope-note"><strong>Outside this run’s scope</strong><span>RF · thermal · mechanical fit · fabrication validation</span></div>
          </article>
        </div>
      </section>

      <section className="overview-lower-grid">
        <article className="overview-card attention-card">
          <div className="card-heading"><h3>Needs attention</h3><span>{latest ? `${latest.findings.length} findings` : "No run"}</span></div>
          {findings.length ? <ul className="attention-list">{findings.map((finding, index) => <li key={`${finding.code}:${index}`}>
            <span className={`finding-mark finding-${finding.severity || "unknown"}`} aria-hidden="true">{finding.severity === "error" ? "×" : finding.severity === "warning" ? "!" : "?"}</span>
            <div><strong>{finding.message || finding.code || "Finding details unavailable"}</strong><small>{[finding.code, finding.component, finding.pin && `pin ${finding.pin}`, finding.net && `net ${finding.net}`].filter(Boolean).join(" · ")}</small></div>
          </li>)}</ul> : <p className="empty-copy">Run a check to see source-linked findings here.</p>}
          <button className="text-button overview-link" onClick={() => onNavigate("runs")}>Review all findings →</button>
        </article>
        <article className="overview-card rules-card">
          <div className="card-heading"><h3>Rule pack</h3><span>{selectedPack?.status ?? "configuration"}</span></div>
          <label className="field-label" htmlFor="overview-rule-pack">Current configuration</label>
          <select id="overview-rule-pack" value={config} onChange={(event) => onSelectConfig(event.target.value)}>
            {configs.map((item) => <option key={item.path} value={item.path}>{item.path}</option>)}
            {!configs.length && <option value="">No configurations found</option>}
          </select>
          <div className="rule-total"><strong>{ruleCount}</strong><span>rules in this configuration</span></div>
          <p className="result-note">Approval is shown only when the configuration records it. Review rule sources before using them as a release gate.</p>
          <button className="text-button overview-link" onClick={() => onNavigate("rules")}>Review configurations →</button>
        </article>
      </section>

      <section className="overview-card board-card">
        <div className="card-heading"><div><h3>Selected board</h3><p>{board?.name ?? "No board selected"}</p></div><button className="text-button" onClick={() => onNavigate("2d")}>Open 2D view →</button></div>
        {boardPreviewUrl ? <img src={boardPreviewUrl} alt={`Board layout: ${board?.name ?? "selected board"}`} /> : <div className="board-empty">Import a KiCad board to view its layout.</div>}
      </section>

      <section className="demo-cases" aria-label="Included demos">
        <article><div><span className="eyebrow">Demo 1</span><h3>Jeden Uno · Arduino board</h3><p>Open the included KiCad board in the interactive 3D viewer.</p></div>
          <button className="button button-secondary" onClick={onOpenArduino}>Open Arduino demo</button></article>
        <article><div><span className="eyebrow">Demo 2</span><h3>TMP102 · Rev B and Rev C</h3><p>Run the known wiring failure, then compare it with the corrected revision.</p></div>
          <button className="button button-secondary" disabled={!demoAvailable || busy} onClick={onRunRevB}>Check Rev B</button></article>
      </section>
    </div>
  );
}
