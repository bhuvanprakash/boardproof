"use client";

import { useEffect, useRef, useState } from "react";
import { createBoardRenderer } from "./board-renderer";

export type Board = { name: string; top?: string; iso?: string; model?: string; gerbers?: string; demo?: boolean };
export const artifactUrl = (file: string) => `/api/artifacts/${encodeURIComponent(file)}`;
export const boardFileUrl = (board: Board, file: string) =>
  board.demo ? `/demo/arduino/${encodeURIComponent(file)}` : artifactUrl(file);
const previewUrl = (file: string) => `/api/previews/${encodeURIComponent(file)}`;

export const arduinoBoard: Board = {
  name: "jeden-uno.kicad_pcb", top: "jeden-uno.svg", iso: "jeden-uno-3d.svg",
  model: "jeden-uno-model.json", demo: true,
};

function ImagePreview({ url, label }: { url: string; label: string }) {
  const [failed, setFailed] = useState(false);

  return failed ? <p className="empty-copy">Could not load {label}. Refresh the workspace and try again.</p> : (
    // eslint-disable-next-line @next/next/no-img-element -- local API previews, including SVGs
    <img src={url} alt={label} onError={() => setFailed(true)} />
  );
}

function SpinView({ board, version }: { board: Board; version: number }) {
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number; angle: number; elevation: number } | null>(null);
  const [angle, setAngle] = useState(45);
  const [elevation, setElevation] = useState(36);
  const [zoom, setZoom] = useState(100);
  const [draw, setDraw] = useState<ReturnType<typeof createBoardRenderer> | null>(null);
  const [failed, setFailed] = useState(false);
  const modelUrl = board.model ? boardFileUrl(board, board.model) : "";

  useEffect(() => {
    if (!modelUrl) return;
    const controller = new AbortController();
    fetch(modelUrl, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Model unavailable");
        return response.json();
      })
      .then((model) => {
        if (!Number.isFinite(model.w) || !Number.isFinite(model.h) || !Array.isArray(model.parts)) {
          throw new Error("Invalid board model");
        }
        setDraw(() => createBoardRenderer(model));
      })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [modelUrl, version]);

  useEffect(() => {
    if (!draw || !svg.current) return;
    try {
      draw(svg.current, angle * Math.PI / 180, elevation, zoom / 100);
    } catch {
      setFailed(true);
    }
  }, [angle, draw, elevation, zoom]);

  if (!draw || failed) {
    return board.iso ? <ImagePreview url={`${boardFileUrl(board, board.iso)}?v=${version}`} label="Isometric board preview" />
      : <p className="empty-copy">{failed || !board.model ? "No 3D preview available." : "Loading 3D model…"}</p>;
  }

  function rotate(value: number) {
    setAngle((Math.round(value) % 360 + 360) % 360);
  }

  return (
    <div className="spin-view">
      <svg className="spin-canvas" ref={svg} role="img" aria-label="Rotatable 3D board preview"
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = { x: event.clientX, y: event.clientY, angle, elevation };
        }}
        onPointerMove={(event) => {
          if (!drag.current) return;
          rotate(drag.current.angle + (event.clientX - drag.current.x) * .7);
          setElevation(Math.max(15, Math.min(85, Math.round(drag.current.elevation + (event.clientY - drag.current.y) * .3))));
        }}
        onLostPointerCapture={() => { drag.current = null; }}
      />
      <div className="rotation">
        <RangeControl id="board-angle" label="Rotation" value={angle} min={0} max={359} unit="°" change={setAngle} />
        <RangeControl id="board-tilt" label="Tilt" value={elevation} min={15} max={85} unit="°" change={setElevation} />
        <RangeControl id="board-zoom" label="Zoom" value={zoom} min={60} max={200} unit="%" change={setZoom} />
        <button className="button button-secondary" onClick={() => { setAngle(45); setElevation(36); setZoom(100); }}>Reset view</button>
      </div>
    </div>
  );
}

function RangeControl({ id, label, value, min, max, unit, change }: {
  id: string; label: string; value: number; min: number; max: number; unit: string; change: (value: number) => void;
}) {
  return <div className="range-control">
    <label htmlFor={id}>{label}</label>
    <output htmlFor={id}>{value}{unit}</output>
    <input id={id} type="range" min={min} max={max} value={value} aria-valuetext={`${value}${unit}`}
      onChange={(event) => change(Number(event.target.value))} />
  </div>;
}

function LayoutView({ url, label }: { url: string; label: string }) {
  const [zoom, setZoom] = useState(100);
  return <div className="layout-view">
    <div className="layout-scroll" role="region" aria-label="Scrollable board layout" tabIndex={zoom > 100 ? 0 : undefined}>
      <div style={{ width: `${zoom}%`, height: `${zoom}%` }}><ImagePreview url={url} label={label} /></div>
    </div>
    <div className="rotation">
      <RangeControl id="layout-zoom" label="Zoom" min={100} max={300} unit="%" value={zoom} change={setZoom} />
      <button className="button button-secondary" onClick={() => setZoom(100)}>Fit board</button>
    </div>
  </div>;
}

export function BoardView({ mode, board, previews, version, onExport, busy }: {
  mode: "2d" | "3d" | "schematic" | "datasheets";
  board?: Board;
  previews: string[];
  version: number;
  onExport?: () => void;
  busy?: boolean;
}) {
  const files = mode === "datasheets"
    ? previews.filter((name) => name.endsWith(".png"))
    : previews.filter((name) => name.endsWith(".svg"));

  if (mode === "schematic" || mode === "datasheets") {
    return (
      <section className="panel">
        <p className="muted">These files may be from another board revision.</p>
        {files.length ? files.map((file) => (
          <figure className="reference" key={file}>
            <figcaption>{file.replace(/^datasheet-/, "").replace(/\.[^.]+$/, "").replaceAll("-", " ")}</figcaption>
            <ImagePreview key={version} url={`${previewUrl(file)}?v=${version}`} label={file} />
          </figure>
        )) : <p className="empty-copy">{mode === "schematic" ? "Run preflight to generate a schematic." : "No cited datasheet pages in this workspace."}</p>}
      </section>
    );
  }

  return (
    <section className="panel board-panel">
      {board ? <>
        <div className="generated-links board-downloads">
          <a download href={boardFileUrl(board, board.name)}>KiCad board ↓</a>
          {board.top && <a download href={boardFileUrl(board, board.top)}>2D SVG ↓</a>}
          {board.iso && <a download href={boardFileUrl(board, board.iso)}>3D SVG ↓</a>}
          {board.gerbers && <a download href={artifactUrl(board.gerbers)}>Gerbers ↓</a>}
          {onExport && <button type="button" className="text-button" disabled={busy} onClick={onExport}>Export Gerbers</button>}
        </div>
        <div className="board-stage">
          {mode === "3d" ? <SpinView key={`${board.demo}:${board.name}:${version}`} board={board} version={version} />
            : board.top ? <LayoutView key={`${board.demo}:${board.top}:${version}`} url={`${boardFileUrl(board, board.top)}?v=${version}`} label={`Top view of ${board.name}`} />
            : <p className="empty-copy">No 2D preview available for this board.</p>}
        </div>
        <p className="muted">{board.demo ? "Jeden Uno sample. " : ""}{mode === "3d" ? "Drag to rotate and tilt. Component shapes are approximate." : "Zoom in and scroll to inspect pads and traces."}</p>
      </> : <>
        <div className="board-stage">
          <ImagePreview key={mode} url={mode === "2d" ? "/demo/tmp102-rev-c-2d.svg" : "/demo/tmp102-rev-c.svg"}
            label={`Sample TMP102 Rev C ${mode === "2d" ? "top view" : "isometric view"}`} />
        </div>
        <p className="muted">Sample TMP102 Rev C placement. Import or generate a board to inspect your own design.</p>
      </>}
    </section>
  );
}
