"use client";

import { useEffect, useState } from "react";
import { artifactUrl } from "./board-view";

type Document = Record<string, unknown>;
const label = (key: string) => key.replaceAll("_", " ");
const record = (value: unknown): Document =>
  value && typeof value === "object" && !Array.isArray(value) ? value as Document : {};

function EvidenceValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    return value.length ? <ul>{value.map((item, index) => (
      <li key={index}><EvidenceValue value={item} /></li>
    ))}</ul> : <span>None</span>;
  }
  if (value && typeof value === "object") {
    return <dl>{Object.entries(record(value)).map(([key, item]) => (
      <div key={key}><dt>{label(key)}</dt><dd><EvidenceValue value={item} /></dd></div>
    ))}</dl>;
  }
  return <>{value === null ? "—" : String(value)}</>;
}

function EvidenceDocument({ file }: { file: string }) {
  const [document, setDocument] = useState<Document>();
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch(artifactUrl(file), { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Could not load evidence.");
        return response.json();
      })
      .then(setDocument)
      .catch(() => { if (!controller.signal.aborted) setError("Could not load evidence."); });
    return () => controller.abort();
  }, [file]);

  if (!document) return <p role={error ? "alert" : "status"} className="empty-copy">{error || "Loading evidence…"}</p>;

  const status = typeof document.status === "string" ? document.status
    : typeof document.regressed === "boolean" ? (document.regressed ? "Regression found" : "No new violations") : "";
  const metrics = Object.entries({
    ...record(document.counts), ...record(document.score), ...record(document.summary), ...record(document.census),
  }).filter(([, value]) => typeof value === "number");
  const sections = ["findings", "faults", "introduced", "fixed", "suggestions", "verified", "unverified_scope", "unverified", "drc", "packs", "footprints", "routing", "scope", "placement", "delta", "layout_redteam", "pcb"];
  return (
    <>
      <div className="evidence-meta">
        {status && <strong className="status-chip">{status}</strong>}
        {typeof document.revision === "string" && <span>{document.revision}</span>}
        {typeof document.passport_hash === "string" && <code title={document.passport_hash}>{document.passport_hash.slice(0, 16)}</code>}
      </div>
      {metrics.length > 0 && <div className="metrics">
        {metrics.map(([key, value]) => <div key={key}>
          <span>{label(key)}</span><strong>{key === "ratio" ? `${Math.round(Number(value) * 100)}%` : String(value)}</strong>
        </div>)}
      </div>}
      {typeof document.note === "string" && <p className="muted">{document.note}</p>}
      <div className="evidence-details">
        {sections.filter((key) => document[key] != null).map((key) => (
          <details key={key} open={["findings", "faults", "unverified_scope"].includes(key)}>
            <summary>{label(key)}{Array.isArray(document[key]) ? ` (${document[key].length})` : ""}</summary>
            <EvidenceValue value={document[key]} />
          </details>
        ))}
      </div>
    </>
  );
}

export function Evidence({ files, preferred, version }: { files: string[]; preferred?: string; version: number }) {
  const [selected, setSelected] = useState("");
  const file = [selected, preferred, files[0]].find((name) => name && files.includes(name));
  if (!file) return <section className="panel"><p className="empty-copy">No evidence yet for this view.</p></section>;
  return (
    <section className="panel">
      <div className="evidence-picker">
        <label className="field-label">Evidence file
          <select value={file} onChange={(event) => setSelected(event.target.value)}>
            {files.map((name) => <option key={name}>{name}</option>)}
          </select>
        </label>
        <a className="button button-secondary" download href={artifactUrl(file)}>Download JSON ↓</a>
      </div>
      <EvidenceDocument key={`${file}:${version}`} file={file} />
    </section>
  );
}
