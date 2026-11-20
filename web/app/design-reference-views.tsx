"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { RangeControl, previewUrl } from "./board-view";

export type Preview = {
  name: string; kind: string; bytes: number; modified: string;
  parts?: number | null; nets?: number | null;
};

const TTL = 5_000;
type Store<T> = { data?: T; at: number; inflight?: Promise<T> };
const previewStore: Store<Preview[]> = { at: 0 };
const registryStore: Store<Registry> = { at: 0 };

/** Cached with a short TTL: switching back to a view paints from memory. */
async function load<T>(store: Store<T>, path: string, label: string, pick: (body: unknown) => T,
                       force?: boolean): Promise<T> {
  if (store.inflight) return store.inflight;
  if (!force && store.data !== undefined && Date.now() - store.at < TTL) return store.data;
  const request = fetch(path, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`Could not load ${label}.`);
      return response.json();
    })
    .then((body) => {
      const value = pick(body);
      store.data = value;
      store.at = Date.now();
      store.inflight = undefined;
      return value;
    })
    .catch((reason: unknown) => {
      store.inflight = undefined;
      throw reason;
    });
  store.inflight = request;
  return request;
}

export const loadPreviews = (force?: boolean) =>
  load(previewStore, "/api/previews", "previews",
    (body) => (body as { previews?: Preview[] }).previews ?? [], force);

export const loadRegistry = (force?: boolean) =>
  load(registryStore, "/api/datasheets", "the datasheet registry",
    (body) => body as Registry, force);

export function warmPreviews() { void loadPreviews().catch(() => undefined); }
export function warmDatasheets() { void loadRegistry().catch(() => undefined); }

export const prettyName = (name: string) => name.replace(/\.[^.]+$/, "").replaceAll("-", " ");
export const fileSize = (bytes: number) =>
  bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
export const timeStamp = (iso: string) => {
  const date = new Date(iso);
  return Number.isNaN(date.valueOf()) ? "" : date.toLocaleString();
};

export function SchematicView({ version, busy, onGenerate }: {
  version: number;
  busy?: boolean;
  onGenerate: () => void;
}) {
  const [items, setItems] = useState<Preview[]>([]);
  const [error, setError] = useState("");
  const [zoom, setZoom] = useState(100);
  const seen = useRef<number | null>(null);

  useEffect(() => {
    // Force a refresh only when the workspace changed since this view last looked.
    const force = seen.current !== version;
    loadPreviews(force)
      .then((next) => { seen.current = version; setItems(next); setError(""); })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "Could not load previews.");
      });
  }, [version]);

  const sheets = items.filter((item) => item.kind === "schematic");

  return (
    <section className="panel">
      <div className="section-heading">
        <h2>Schematic sheets</h2>
        <span>{sheets.length ? `${sheets.length} sheet${sheets.length > 1 ? "s" : ""}` : "none yet"}</span>
      </div>
      <p className="muted">This generated view shows parts and connections. Edit the source schematic in KiCad.</p>
      {error && <p className="notice notice-error" role="alert">{error}</p>}

      {sheets.length > 0 && (
        <div className="view-toolbar">
          <RangeControl id="schematic-zoom" label="Zoom" min={50} max={300} unit="%" value={zoom} change={setZoom} />
          <button type="button" className="button button-secondary" onClick={() => setZoom(100)}>Fit width</button>
          <button type="button" className="button button-secondary" disabled={busy} onClick={onGenerate}>
            {busy ? "Working…" : "Redraw from netlist"}
          </button>
        </div>
      )}

      {sheets.length ? (
        <div className="sheet-list">
          {sheets.map((sheet) => (
            <figure className="sheet" key={sheet.name}>
              <figcaption className="sheet-head">
                <span>
                  <strong>{prettyName(sheet.name)}</strong>
                  <small className="sheet-meta">{fileSize(sheet.bytes)} · {timeStamp(sheet.modified)}
                    {sheet.parts != null && sheet.nets != null ? ` · ${sheet.parts} parts · ${sheet.nets} nets` : ""}</small>
                </span>
                <span className="sheet-links">
                  <a href={previewUrl(sheet.name)} download>Download ↓</a>
                  <a href={previewUrl(sheet.name)} target="_blank" rel="noreferrer">Open ↗</a>
                </span>
              </figcaption>
              <div className="sheet-scroll">
                <div className="sheet-frame" style={{ width: `${zoom}%` }}>
                  {/* eslint-disable-next-line @next/next/no-img-element -- local API SVG preview */}
                  <img src={`${previewUrl(sheet.name)}?v=${version}`} alt={`Schematic sheet: ${prettyName(sheet.name)}`} />
                </div>
              </div>
            </figure>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <p className="empty-copy">
            No generated schematic yet. Run preflight to create one from the selected configuration.
          </p>
          <button type="button" className="button button-primary" disabled={busy} onClick={onGenerate}>
            {busy ? "Working…" : "Run preflight"}
          </button>
        </div>
      )}
    </section>
  );
}

type Document = {
  slug: string;
  part: string;
  url?: string;
  sha256?: string;
  fetched_at?: string;
  exists: boolean;
  bytes?: number | null;
  hash_ok?: boolean;
  page?: string | null;
  pdf?: string;
};
type Registry = { documents: Document[]; prefixes: string[]; max_pdf_mb: number };
type Check = { ok: boolean; note: string };

async function post<T>(path: string, payload: object): Promise<T> {
  const response = await fetch(`/api/${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = (body as { detail?: unknown }).detail;
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg ?? item).join("; ") : String(detail ?? `Request failed (${response.status}).`));
  }
  return body as T;
}

const sourceLabel = (url: string) => {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === "file:") return `${parsed.pathname.split("/").pop() ?? "file"} · local`;
    return parsed.hostname || url.slice(0, 48);
  } catch { return url.slice(0, 48); }
};
const shortHash = (hash?: string) => (hash ? `${hash.slice(0, 12)}…${hash.slice(-6)}` : "—");

async function copy(text: string) {
  try { await navigator.clipboard.writeText(text); } catch { /* clipboard unavailable */ }
}

export function DatasheetsView({ version, busy }: { version: number; busy?: boolean }) {
  const [registry, setRegistry] = useState<Registry>();
  const [pages, setPages] = useState<Preview[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [working, setWorking] = useState("");
  const [checks, setChecks] = useState<Record<string, Check>>({});
  const [part, setPart] = useState("");
  const [url, setUrl] = useState("");
  const [refresh, setRefresh] = useState(false);
  const [zoom, setZoom] = useState(100);
  const [query, setQuery] = useState("");
  const seen = useRef<number | null>(null);

  const load = useCallback(async (force?: boolean) => {
    const [list, previews] = await Promise.all([loadRegistry(force), loadPreviews(force)]);
    setRegistry(list);
    setPages(previews.filter((item) => item.kind === "datasheet"));
  }, []);

  useEffect(() => {
    const force = seen.current !== version;
    load(force)
      .then(() => { seen.current = version; setError(""); })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "Could not load datasheets.");
      });
  }, [load, version]);

  function verify(doc: Document) {
    setWorking(`verify:${doc.slug}`);
    setError("");
    post<{ ok: boolean }>("datasheets/verify", { part: doc.part })
      .then((result) => setChecks((previous) => ({
        ...previous,
        [doc.slug]: result.ok
          ? { ok: true, note: "SHA-256 matches the registry." }
          : { ok: false, note: "Hash changed. Fetch the datasheet again to replace the saved copy." },
      })))
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Verify failed."))
      .finally(() => setWorking(""));
  }

  function verifyAll() {
    setWorking("verify-all");
    setError("");
    setNotice("");
    post<{ results: { slug: string; part: string; ok: boolean }[] }>("datasheets/verify-all", {})
      .then(({ results }) => {
        setChecks(Object.fromEntries(results.map((item) => [item.slug, item.ok
          ? { ok: true, note: "SHA-256 matches the registry." }
          : { ok: false, note: "Hash changed. Fetch the datasheet again to replace the saved copy." }])));
        const changed = results.filter((item) => !item.ok).length;
        setNotice(changed
          ? `${changed} of ${results.length} saved file(s) changed since they were pinned.`
          : `All ${results.length} saved file(s) match their recorded hash.`);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Verify failed."))
      .finally(() => setWorking(""));
  }

  function lookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!part.trim()) return;
    setWorking("fetch");
    setError("");
    setNotice("");
    post<Document>("datasheets/fetch", { part: part.trim(), url: url.trim() || null, refresh })
      .then((entry) => {
        setNotice(`Saved ${entry.part}${entry.sha256 ? ` · SHA-256 ${entry.sha256.slice(0, 12)}…` : ""}`);
        setPart("");
        setUrl("");
        setRefresh(false);
        return load(true);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Fetch failed."))
      .finally(() => setWorking(""));
  }

  const documents = registry?.documents ?? [];
  const needle = query.trim().toLowerCase();
  const shown = needle
    ? documents.filter((doc) => doc.part.toLowerCase().includes(needle) || doc.slug.includes(needle))
    : documents;

  return (
    <>
      <section className="panel">
        <div className="section-heading">
          <h2>Saved datasheets</h2>
          <span>{documents.length ? `${documents.length} part${documents.length > 1 ? "s" : ""}` : "none saved"}</span>
        </div>
        <p className="muted">Each PDF is saved with its source and SHA-256. Verify the hash to check whether the file changed. Rule citations link to the saved PDF page.</p>
        {error && <p className="notice notice-error" role="alert">{error}</p>}
        {notice && <p className="notice busy-notice" role="status">{notice}</p>}

        {documents.length > 0 && (
          <div className="view-toolbar">
            <div className="filter-field">
              <label className="field-label" htmlFor="datasheet-filter">Filter parts</label>
              <input id="datasheet-filter" type="search" value={query} placeholder="e.g. TMP102"
                disabled={!!busy} onChange={(event) => setQuery(event.target.value)} />
            </div>
            <button type="button" className="button button-secondary" disabled={!!busy || !!working}
              onClick={verifyAll}>
              {working === "verify-all" ? "Hashing…" : "Verify all hashes"}
            </button>
          </div>
        )}

        {shown.length ? (
          <div className="doc-grid">
            {shown.map((doc) => {
              const check = checks[doc.slug];
              return (
                <article className="doc-card" key={doc.slug}>
                  <header className="doc-head">
                    <strong className="doc-part">{doc.part}</strong>
                    <span className={`badge ${!doc.exists ? "badge-warn" : doc.hash_ok ? "badge-ok" : "badge-warn"}`}>
                      {!doc.exists ? "missing" : doc.hash_ok ? "verified" : "drift"}
                    </span>
                  </header>
                  <dl className="doc-rows">
                    <dt>Source</dt>
                    <dd>{doc.url
                      ? <a href={doc.url} target="_blank" rel="noreferrer" title={doc.url}>{sourceLabel(doc.url)}</a>
                      : "—"}</dd>
                    <dt>Saved</dt><dd>{doc.fetched_at ? timeStamp(doc.fetched_at) : "—"}</dd>
                    <dt>Size</dt><dd>{doc.bytes ? fileSize(doc.bytes) : "—"}</dd>
                    <dt>SHA-256</dt>
                    <dd>
                      <code title={doc.sha256 ?? ""}>{shortHash(doc.sha256)}</code>
                      {doc.sha256 && <button type="button" className="text-button" onClick={() => void copy(doc.sha256!)}>copy</button>}
                    </dd>
                  </dl>
                  {check && <p className={`doc-verify ${check.ok ? "ok" : "bad"}`}>{check.note}</p>}
                  <div className="generated-links">
                    {doc.exists && <a download href={`/api/datasheets/pdf/${encodeURIComponent(doc.slug)}`}>PDF ↓</a>}
                    {doc.page && <a href={previewUrl(doc.page)} target="_blank" rel="noreferrer">Cited page ↗</a>}
                    <button type="button" className="text-button" disabled={!!busy || !!working}
                      onClick={() => verify(doc)}>
                      {working === `verify:${doc.slug}` ? "Checking…" : "Verify hash"}
                    </button>
                  </div>
                  {doc.page && (
                    <a className="doc-thumb" href={previewUrl(doc.page)} target="_blank" rel="noreferrer"
                      aria-label={`Open the cited page for ${doc.part}`}>
                      {/* eslint-disable-next-line @next/next/no-img-element -- rendered datasheet page */}
                      <img src={`${previewUrl(doc.page)}?v=${version}`} alt={`Cited datasheet page for ${doc.part}`} />
                    </a>
                  )}
                </article>
              );
            })}
          </div>
        ) : (
          <p className="empty-copy">
            {documents.length ? `No saved part matches “${query}”.` : <>
              No datasheets saved yet. Import a design with “Look up datasheets” or enter a part number below
              {registry?.prefixes?.length ? `. Known prefixes: ${registry.prefixes.join(", ")}.` : "."}
            </>}
          </p>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <h2>Look up a part</h2>
          <span>{registry ? `≤ ${registry.max_pdf_mb} MB per file` : "saved with SHA-256"}</span>
        </div>
        <form className="lookup-form" onSubmit={lookup}>
          <div className="target-fields">
            <div>
              <label className="field-label" htmlFor="datasheet-part">Part number</label>
              <input id="datasheet-part" value={part} maxLength={80} placeholder="e.g. TMP102AIDRLR"
                disabled={!!working || !!busy} onChange={(event) => setPart(event.target.value)} />
            </div>
            <div>
              <label className="field-label" htmlFor="datasheet-url">Direct PDF URL (optional)</label>
              <input id="datasheet-url" value={url} maxLength={600} placeholder="leave empty for a known source"
                disabled={!!working || !!busy} onChange={(event) => setUrl(event.target.value)} />
            </div>
          </div>
          <label className="lookup-toggle">
            <input type="checkbox" checked={refresh} disabled={!!working || !!busy}
              onChange={(event) => setRefresh(event.target.checked)} />
            <span><strong>Replace the saved file</strong>
              <small>The new PDF and hash replace the current copy.</small></span>
          </label>
          <p className="lookup-hint">Without a URL, only known vendor part numbers are accepted. For other parts, enter a public HTTP(S) PDF URL.</p>
          <button className="button button-primary" disabled={!!working || !!busy || !part.trim()}>
            {working === "fetch" ? "Fetching…" : "Fetch datasheet"}
          </button>
        </form>
      </section>

      {pages.length > 0 && (
        <section className="panel">
          <div className="section-heading">
            <h2>Rendered pages</h2>
            <span>{pages.length} page{pages.length > 1 ? "s" : ""} cited by checks</span>
          </div>
          <div className="view-toolbar">
            <RangeControl id="datasheet-zoom" label="Zoom" min={50} max={300} unit="%" value={zoom} change={setZoom} />
            <button type="button" className="button button-secondary" onClick={() => setZoom(100)}>Fit width</button>
          </div>
          <div className="page-grid">
            {pages.map((page) => (
              <figure key={page.name}>
                <figcaption>
                  {prettyName(page.name.replace(/^datasheet-/, ""))}
                  <small className="sheet-meta">{fileSize(page.bytes)} · {timeStamp(page.modified)}</small>
                </figcaption>
                <div className="sheet-scroll">
                  <div className="sheet-frame" style={{ width: `${zoom}%` }}>
                    {/* eslint-disable-next-line @next/next/no-img-element -- rendered PDF page */}
                    <img src={`${previewUrl(page.name)}?v=${version}`} alt={`Datasheet page: ${prettyName(page.name)}`} />
                  </div>
                </div>
              </figure>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
