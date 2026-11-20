"use client";

import { useEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogBackdrop,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@ui-sdk/react/dialog";
import { createBoardRenderer } from "./board-renderer";

export type Board = { name: string; top?: string; iso?: string; model?: string; gerbers?: string; demo?: boolean };
export const artifactUrl = (file: string) => `/api/artifacts/${encodeURIComponent(file)}`;
export const boardFileUrl = (board: Board, file: string) =>
  board.demo ? `/demo/arduino/${encodeURIComponent(file)}` : artifactUrl(file);
export const previewUrl = (file: string) => `/api/previews/${encodeURIComponent(file)}`;

export const arduinoBoard: Board = {
  name: "jeden-uno.kicad_pcb", top: "jeden-uno.svg", iso: "jeden-uno-3d.svg",
  model: "jeden-uno-model.json", demo: true,
};

function ImagePreview({ url, label }: { url: string; label: string }) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);

  if (failed) return <p className="empty-copy">Could not load {label}. Refresh the workspace and try again.</p>;
  return <div className="image-preview">
    {!loaded && <p className="image-loading" role="status">Loading preview…</p>}
    {/* eslint-disable-next-line @next/next/no-img-element -- local API previews, including SVGs */}
    <img src={url} alt={label} onLoad={() => setLoaded(true)} onError={() => setFailed(true)} />
  </div>;
}

function SpinView({ board, version, idPrefix }: { board: Board; version: number; idPrefix: string }) {
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number; angle: number; elevation: number } | null>(null);
  const [angle, setAngle] = useState(45);
  const [elevation, setElevation] = useState(36);
  const [zoom, setZoom] = useState(120);
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
        <RangeControl id={`${idPrefix}-angle`} label="Rotation" value={angle} min={0} max={359} unit="°" change={setAngle} />
        <RangeControl id={`${idPrefix}-tilt`} label="Tilt" value={elevation} min={15} max={85} unit="°" change={setElevation} />
        <RangeControl id={`${idPrefix}-zoom`} label="Zoom" value={zoom} min={60} max={200} unit="%" change={setZoom} />
        <button className="button button-secondary" onClick={() => { setAngle(45); setElevation(36); setZoom(120); }}>Reset view</button>
      </div>
    </div>
  );
}

export function RangeControl({ id, label, value, min, max, unit, change }: {
  id: string; label: string; value: number; min: number; max: number; unit: string; change: (value: number) => void;
}) {
  return <div className="range-control">
    <label htmlFor={id}>{label}</label>
    <output htmlFor={id}>{value}{unit}</output>
    <input id={id} type="range" min={min} max={max} value={value} aria-valuetext={`${value}${unit}`}
      onChange={(event) => change(Number(event.target.value))} />
  </div>;
}

function LayoutView({ url, label, idPrefix }: { url: string; label: string; idPrefix: string }) {
  const [zoom, setZoom] = useState(100);
  return <div className="layout-view">
    <div className="layout-scroll" role="region" aria-label="Scrollable board layout" tabIndex={zoom > 100 ? 0 : undefined}>
      <div style={{ width: `${zoom}%`, height: `${zoom}%` }}><ImagePreview url={url} label={label} /></div>
    </div>
    <div className="rotation">
      <RangeControl id={`${idPrefix}-zoom`} label="Zoom" min={100} max={300} unit="%" value={zoom} change={setZoom} />
      <button className="button button-secondary" onClick={() => setZoom(100)}>Fit board</button>
    </div>
  </div>;
}

export function BoardView({ mode, board, version, onExport, busy }: {
  mode: "2d" | "3d";
  board?: Board;
  version: number;
  onExport?: () => void;
  busy?: boolean;
}) {
  const renderPreview = (idPrefix: string) => board
    ? mode === "3d"
      ? <SpinView key={`${board.demo}:${board.name}:${version}:${idPrefix}`} board={board} version={version} idPrefix={`${idPrefix}-board`} />
      : board.top
        ? <LayoutView key={`${board.demo}:${board.top}:${version}:${idPrefix}`} url={`${boardFileUrl(board, board.top)}?v=${version}`}
            label={`Top view of ${board.name}`} idPrefix={`${idPrefix}-layout`} />
        : <p className="empty-copy">No 2D preview available for this board.</p>
    : <ImagePreview key={`${mode}:${idPrefix}`} url={mode === "2d" ? "/demo/tmp102-rev-c-2d.svg" : "/demo/tmp102-rev-c.svg"}
        label={`Sample TMP102 Rev C ${mode === "2d" ? "top view" : "isometric view"}`} />;

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
        <div className="board-stage">{renderPreview("inline")}</div>
        <div className="board-key" aria-label="Board view key">
          <span><i className="key-mask" /> Solder mask</span>
          <span><i className="key-pad" /> Pads</span>
          <span><i className="key-body" /> Component body</span>
        </div>
        <p className="muted">{board.demo ? "Jeden Uno sample. " : ""}{mode === "3d" ? "Drag to rotate and tilt. Component shapes are approximate." : "Zoom in and scroll to inspect pads and traces."}</p>
      </> : <>
        <div className="board-stage">{renderPreview("sample")}</div>
        <div className="board-key" aria-label="Board view key">
          <span><i className="key-mask" /> Solder mask</span>
          <span><i className="key-pad" /> Pads</span>
          <span><i className="key-body" /> Component body</span>
        </div>
        <p className="muted">Sample TMP102 Rev C placement. Import or generate a board to inspect your own design.</p>
      </>}
      <Dialog>
        <DialogTrigger className="button button-secondary board-expand">View full size</DialogTrigger>
        <DialogBackdrop className="board-modal-backdrop" />
        <DialogContent className="board-modal">
          <div className="board-modal-heading">
            <div>
              <DialogTitle>{board?.name.replace(/\.kicad_pcb$/i, "") ?? "TMP102 Rev C"} · {mode} view</DialogTitle>
              <DialogDescription>
                {mode === "3d" ? "Drag the board or use the controls to rotate it." : "Zoom and scroll to inspect pads and traces."}
              </DialogDescription>
            </div>
            <DialogClose className="button button-secondary board-modal-close">Close</DialogClose>
          </div>
          <div className="board-stage board-modal-stage">{renderPreview("dialog")}</div>
        </DialogContent>
      </Dialog>
    </section>
  );
}
