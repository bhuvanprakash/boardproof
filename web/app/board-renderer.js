// Port of the Python dashboard's board projection. Labels are untrusted netlist text.
function escapeText(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

export function createBoardRenderer(model) {
  let tilt = Math.PI / 5;
  const arduino = model.look === 'arduino';
  const MASK = arduino ? '#0b4f8a' : '#0c4f2e';
  const MASK_DARK = arduino ? '#083560' : '#083a22';
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
    return { X: rx, Y: ry * Math.sin(tilt) - z * Math.cos(tilt), D: ry * Math.cos(tilt) + z * Math.sin(tilt) };
  }

  function box(parts, x0, y0, x1, y1, zLow, zHigh, yaw, fillTop, fillB, stroke) {
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

  function frame(svg, yaw, elevation = 36, zoom = 1) {
    tilt = elevation * Math.PI / 180;
    const parts = [];
    const z0 = 0, zt = model.t;
    const bounds = [];
    const track = (p) => bounds.push(p);

    const corners = [[0, 0], [model.w, 0], [model.w, model.h], [0, model.h]];
    corners.forEach(([x, y]) => { track(project(x, y, zt, yaw)); track(project(x, y, 0, yaw)); });
    model.parts.forEach((part) => {
      for (const dx of [-part.w / 2, part.w / 2]) {
        for (const dy of [-part.d / 2, part.d / 2]) {
          track(project(part.x + dx, part.y + dy, zt + part.z, yaw));
        }
      }
    });

    parts.push('<polygon points="' + corners.map(([x, y]) => {
      const p = project(x, y, 0, yaw);
      return p.X.toFixed(2) + ',' + p.Y.toFixed(2);
    }).join(' ') + '" fill="' + MASK_DARK + '"/>');

    box(parts, 0, 0, model.w, model.h, z0, zt, yaw, MASK, MASK_DARK, MASK_DARK);
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
      const fontSize = Math.max(0.45, Math.min(0.82, Math.min(part.w, part.d) * 0.55));
      const label = project((quad[0][0] + quad[2][0]) / 2, (quad[0][1] + quad[2][1]) / 2,
                            zt + part.z + Math.max(0.6, part.z * 0.25), yaw);
      parts.push('<text x="' + label.X.toFixed(2) + '" y="' + label.Y.toFixed(2) +
        '" font-family="ui-sans-serif,system-ui,sans-serif" font-size="' + fontSize.toFixed(2) +
        '" fill="' + SILK + '" stroke="#10202b" stroke-width="0.12" paint-order="stroke"' +
        ' text-anchor="middle" opacity="0.95">' + escapeText(part.ref) + '</text>');
    });

    (model.vias || []).forEach((via) => {
      const p = project(via.x, via.y, zt, yaw);
      parts.push('<circle cx="' + p.X.toFixed(2) + '" cy="' + p.Y.toFixed(2) + '" r="' +
        (via.s / 2).toFixed(2) + '" fill="' + COPPER + '"/>');
    });

    const xs = bounds.map((b) => b.X), ys = bounds.map((b) => b.Y);
    const spanX = Math.max.apply(null, xs) - Math.min.apply(null, xs) || 1;
    const spanY = Math.max.apply(null, ys) - Math.min.apply(null, ys) || 1;
    const scale = Math.min(88 / spanX, 64 / spanY) * zoom;
    const cx = (Math.max.apply(null, xs) + Math.min.apply(null, xs)) / 2;
    const cy = (Math.max.apply(null, ys) + Math.min.apply(null, ys)) / 2;
    svg.setAttribute('viewBox', (cx - 50 / scale).toFixed(2) + ' ' + (cy - 38 / scale).toFixed(2) +
      ' ' + (100 / scale).toFixed(2) + ' ' + (76 / scale).toFixed(2));
    svg.innerHTML = parts.join('');
  }

  return frame;
}
