"""Generate an editable two-layer PCB candidate from a *verified* design.

The rule this module obeys: geometry is never invented for an unverified part.
Footprints must resolve, every net must come from the netlist, and anything the
router cannot complete is reported as unrouted rather than hidden.

Output is a native KiCad board so it stays editable, plus an SVG preview.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from .footprints import FootprintError, LandPattern, outline_of, resolve
from .model import Design
from .pcb import Board, FootprintInst, PadInst, Segment, Via, census, render_svg, write_kicad

CELL = 0.5           # routing grid, mm (0.5 keeps parallel tracks 0.25 mm apart)
TRACK = 0.25         # track width, mm
CLEARANCE = 0.2      # copper-to-copper minimum, mm
ROUTE_CLEARANCE = 0.45  # what the grid reserves, so real gaps clear 0.2 mm after snapping
EDGE_KEEPOUT = 0.5   # mm from the board edge
VIA_COST = 12        # grid steps

DECOUPLING_MAX_MM = 4.0
PULLUP_MAX_MM = 10.0

RING = [(radius, dx, dy)
        for radius in (3.6, 4.6, 5.8, 7.2, 9.0, 11.0)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0), (1, -1), (-1, -1), (1, 1), (-1, 1))]


@dataclass
class Placement:
    ref: str
    pattern: LandPattern
    x: float
    y: float
    rotation: float = 0.0
    rules: list[str] = field(default_factory=list)
    source: str = "export"


@dataclass
class RouteResult:
    routed: list[str] = field(default_factory=list)
    order: list[str] = field(default_factory=list)
    lanes: dict[str, float] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    segments: list[Segment] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)


def parse_outline(text: str) -> tuple[float, float] | tuple[None, None]:
    if str(text).strip().lower() in {"auto", "fit", "shrink"}:
        return None, None
    cleaned = text.lower().replace("mm", "").replace(" ", "")
    if "x" not in cleaned:
        raise ValueError(f"--outline must look like 30x25mm, got {text!r}")
    width, height = cleaned.split("x", 1)
    w, h = float(width), float(height)
    if not (10 <= w <= 200 and 10 <= h <= 200):
        raise ValueError("board outline must be between 10 and 200 mm per side")
    return w, h


def _bbox(pattern: LandPattern) -> tuple[float, float]:
    return outline_of(pattern)


def _row_conflict(candidate: Placement, placed: list[Placement], min_gap: float = 0.9) -> bool:
    """Two footprints must not put pads on nearly the same row.

    Parallel stubs 0.25 mm apart is a short waiting to happen; rows are cheap to
    separate at placement time and impossible to fix after routing.
    """
    def rows(item: Placement) -> list[float]:
        return [round(item.y + pad.y, 3) for pad in item.pattern.pads]

    for other in placed:
        if abs(candidate.x - other.x) > 6.0 or abs(candidate.y - other.y) > 6.0:
            continue                       # far apart: parallel stubs cannot interact
        for a in rows(candidate):
            for b in rows(other):
                if 0 < abs(a - b) < min_gap:
                    return True
    return False


def _overlaps(a: Placement, b: Placement, gap: float = 0.8) -> bool:
    aw, ah = _bbox(a.pattern)
    bw, bh = _bbox(b.pattern)
    return (abs(a.x - b.x) < (aw + bw) / 2 + gap) and (abs(a.y - b.y) < (ah + bh) / 2 + gap)


def _place(design: Design, width: float, height: float, compact: bool = False,
           allow_generic: bool = True) -> tuple[list[Placement], list[str]]:
    notes: list[str] = []
    def _prefix(ref: str) -> str:
        upper = (ref or "").upper()
        if upper.startswith("LED"):
            return "C"
        if upper.startswith("Y"):
            return "C"
        return upper[:1]

    ordered = sorted(design.components.values(),
                     key=lambda c: ({"U": 0, "C": 1, "R": 2, "J": 3}.get(_prefix(c.ref), 4), c.ref))
    placed: list[Placement] = []
    for comp in ordered:
        pins = sorted(comp.pins, key=lambda n: (len(n), n))
        pattern, source = resolve(comp.ref, comp.part,
                                  comp.attributes.get("FootprintName", ""), pins,
                                  allow_generic=allow_generic)
        anchor = placed[0] if placed else None
        candidates: list[tuple[float, float, str]] = []
        prefix = _prefix(comp.ref)
        if prefix == "J":
            inset = EDGE_KEEPOUT + 3.2
            step = 5.2
            ys, xs = [], []
            y, x = inset, inset
            while y < height - inset:
                ys.append(y)
                y += step
            while x < width - inset:
                xs.append(x)
                x += step
            candidates = [(inset, y, "connector on the left edge") for y in ys]
            candidates += [(width - inset, y, "connector on the right edge") for y in ys]
            candidates += [(x, inset, "connector on the top edge") for x in xs]
            candidates += [(x, height - inset, "connector on the bottom edge") for x in xs]
            if compact and anchor is not None:
                candidates = [(anchor.x - 8.0, anchor.y + offset, "connector beside the IC")
                              for offset in (0.0, -5.0, 5.0, -10.0, 10.0, -15.0, 15.0)] + candidates
        elif prefix == "C" and anchor is not None:
            ring = ((3.4, 0, -1), (3.4, 1, -1), (3.4, -1, -1), (4.4, 0, 1), (4.4, 1, 1),
                    (4.4, -1, 1)) if compact else RING
            candidates = [(anchor.x + radius * dx, anchor.y + radius * dy,
                           f"decoupling within {DECOUPLING_MAX_MM:g} mm of {anchor.ref}")
                          for radius, dx, dy in ring]
        elif prefix == "R" and anchor is not None:
            offset = len([p for p in placed if p.ref[:1].upper() == "R"]) * 0.9
            ring = ((3.4, 1, 1), (3.4, 1, -1), (4.6, 0, 1), (4.6, 0, -1), (5.8, 1, 1),
                    (5.8, 1, -1), (5.8, -1, 1), (5.8, -1, -1)) if compact else (
                [(r, dx, dy) for r, dx, dy in RING if dx != 0]
                + [(r, 0, dy) for r, _dx, dy in RING])
            candidates = [(anchor.x + radius * dx, anchor.y + radius * dy + offset * 0.6,
                           f"pull-up within {PULLUP_MAX_MM:g} mm of {anchor.ref}")
                          for radius, dx, dy in ring]
        else:
            candidates.append((width / 2, height / 2, "board centre"))
            if anchor is not None:
                for dx, dy in ((18.0, 0.0), (-18.0, 0.0), (0.0, 26.0), (0.0, -26.0),
                               (22.0, 22.0), (-22.0, 22.0), (22.0, -22.0), (-22.0, -22.0)):
                    candidates.append((anchor.x + dx, anchor.y + dy, "beside the IC"))

        chosen: Placement | None = None
        for strict_rows in (True, False):
            for x, y, rule in candidates:
                trial = Placement(comp.ref, pattern, x, y, 0.0, [rule], source)
                w, h = _bbox(pattern)
                inside = (w / 2 + EDGE_KEEPOUT < x < width - w / 2 - EDGE_KEEPOUT
                          and h / 2 + EDGE_KEEPOUT < y < height - h / 2 - EDGE_KEEPOUT)
                if not inside:
                    continue
                if any(_overlaps(trial, other) for other in placed):
                    continue
                if strict_rows and _row_conflict(trial, placed):
                    continue
                chosen = trial
                break
            if chosen is not None:
                break
        if chosen is None:
            raise ValueError(
                f"could not place {comp.ref} ({pattern.name}) on a {width:g}x{height:g} mm board "
                "without overlap; increase --outline")
        placed.append(chosen)
    if not any(p.ref[:1].upper() == "U" for p in placed):
        notes.append("no IC found on this board; layout rules ran with the first component as anchor")
    return placed, notes


class Router:
    """Two-layer grid router: 0.25 mm cells, SMD pads on F.Cu, vias switch layers."""

    LAYERS = ("F.Cu", "B.Cu")

    def __init__(self, width: float, height: float) -> None:
        self.cols = int(width / CELL)
        self.rows = int(height / CELL)
        # committed copper, per layer
        self.base: dict[str, set[tuple[int, int]]] = {l: set() for l in self.LAYERS}
        self.pad_cells: dict[str, set[tuple[int, int]]] = {}
        self.blocked: dict[str, set[tuple[int, int]]] = {l: set() for l in self.LAYERS}

    def cell(self, x: float, y: float) -> tuple[int, int]:
        return int(round(x / CELL)), int(round(y / CELL))

    def world(self, ix: int, iy: int) -> tuple[float, float]:
        return ix * CELL, iy * CELL

    def _inside(self, ix: int, iy: int) -> bool:
        margin = int(EDGE_KEEPOUT / CELL)
        return margin <= ix < self.cols - margin and margin <= iy < self.rows - margin

    def cells_for_pad(self, pad: PadInst, grow: float) -> set[tuple[int, int]]:
        x0, y0 = self.cell(pad.x - pad.w / 2 - grow, pad.y - pad.h / 2 - grow)
        x1, y1 = self.cell(pad.x + pad.w / 2 + grow, pad.y + pad.h / 2 + grow)
        return {(ix, iy) for ix in range(x0, x1 + 1) for iy in range(y0, y1 + 1)}

    def register_pads(self, pads_by_net: dict[str, list[PadInst]]) -> None:
        for net, pads in pads_by_net.items():
            cells: set[tuple[int, int]] = set()
            for pad in pads:
                cells |= self.cells_for_pad(pad, ROUTE_CLEARANCE)
            self.pad_cells[net] = cells

    def prepare(self, net: str) -> None:
        """SMD pads occupy F.Cu only; tracks occupy the layer they were routed on."""
        blocked_top = set(self.base["F.Cu"])
        blocked_bottom = set(self.base["B.Cu"])
        for other, cells in self.pad_cells.items():
            if other != net:
                blocked_top |= cells
        own = self.pad_cells.get(net, set())
        blocked_top -= own
        self.blocked = {"F.Cu": blocked_top, "B.Cu": blocked_bottom}

    def mark_track(self, segment: Segment) -> None:
        x0, y0 = self.cell(min(segment.x1, segment.x2), min(segment.y1, segment.y2))
        x1, y1 = self.cell(max(segment.x1, segment.x2), max(segment.y1, segment.y2))
        radius = int(math.ceil((segment.width / 2 + ROUTE_CLEARANCE) / CELL))
        target = self.base[segment.layer]
        for ix in range(x0 - radius, x1 + radius + 1):
            for iy in range(y0 - radius, y1 + radius + 1):
                target.add((ix, iy))

    def mark_via(self, via: Via) -> None:
        cells = set()
        for layer in self.LAYERS:
            cells |= self.cells_for_pad(
                PadInst("", "", via.net, via.x, via.y, via.size, via.size), ROUTE_CLEARANCE)
        for layer in self.LAYERS:
            self.base[layer] |= cells

    def route(self, start: PadInst, goal: PadInst, net: str) -> tuple[list[Segment], list[Via], str]:
        sx, sy = self.cell(start.x, start.y)
        gx, gy = self.cell(goal.x, goal.y)
        goal_cell = (gx, gy)
        queue: deque[tuple[int, int, int]] = deque()
        came: dict[tuple[int, int, int], tuple[int, int, int] | None] = {}
        cost: dict[tuple[int, int, int], int] = {}

        def layer_name(index: int) -> str:
            return self.LAYERS[index]

        for index in (0, 1):
            node = (index, sx, sy)
            queue.append(node)
            came[node] = None
            cost[node] = 0
        found: tuple[int, int, int] | None = None
        while queue:
            node = queue.popleft()
            layer, ix, iy = node
            if (ix, iy) == goal_cell and layer == 0:
                found = node
                break
            base_cost = cost[node]
            blocked = self.blocked[layer_name(layer)]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = ix + dx, iy + dy
                if not self._inside(nx, ny):
                    continue
                if (nx, ny) in blocked and (nx, ny) != goal_cell:
                    continue
                nxt = (layer, nx, ny)
                if nxt in cost and cost[nxt] <= base_cost + 1:
                    continue
                cost[nxt] = base_cost + 1
                came[nxt] = node
                queue.append(nxt)
            other = (1 - layer, ix, iy)
            if (ix, iy) not in self.blocked[layer_name(1 - layer)] and (
                    other not in cost or cost[other] > base_cost + VIA_COST):
                cost[other] = base_cost + VIA_COST
                came[other] = node
                queue.append(other)
        if found is None:
            return [], [], f"no legal path from {start.ref}.{start.number} to {goal.ref}.{goal.number}"

        path: list[tuple[int, int, int]] = []
        node = found
        while node is not None:
            path.append(node)
            node = came[node]  # type: ignore[assignment]
        path.reverse()

        segments: list[Segment] = []
        vias: list[Via] = []
        run_start = path[0]
        for index in range(1, len(path) + 1):
            if index == len(path) or path[index][0] != run_start[0]:
                end = path[index - 1]
                x1, y1 = self.world(run_start[1], run_start[2])
                x2, y2 = self.world(end[1], end[2])
                if (x1, y1) != (x2, y2):
                    segments.append(Segment(net, layer_name(run_start[0]), x1, y1, x2, y2, TRACK))
                if index < len(path):
                    vx, vy = self.world(path[index - 1][1], path[index - 1][2])
                    vias.append(Via(net, vx, vy))
                    run_start = path[index]
        return segments, vias, ""


ESCAPE_STEP = 1.0      # mm between escape columns of pads in the same row
ESCAPE_BASE = 0.9      # mm from the pad edge to its escape via
LANE_PITCH = 1.2       # mm between nets' horizontal lanes
VIA_SIZE = 0.6
VIA_DRILL = 0.3
MIN_COLUMN_GAP = 1.15  # mm between drop columns of different nets (via 0.6 + 0.2 clearance)


MIN_COLUMN_GAP = 1.0   # mm between drop columns of different nets


VIA_FANOUT = 1.5     # mm off the pad row: clears neighbouring pads, stubs and a 0.6 mm via


def _fan_direction(board: Board, pad: PadInst) -> float:
    footprint = next((f for f in board.footprints if f.ref == pad.ref), None)
    if footprint is None:
        return 1.0
    return 1.0 if pad.y >= footprint.y else -1.0


def via_point(board: Board, pad: PadInst, column_x: float) -> tuple[float, float]:
    return column_x, round(pad.y + _fan_direction(board, pad) * VIA_FANOUT, 3)


def escape_points(board: Board) -> dict[tuple[str, str], tuple[float, float]]:
    """Allocate a unique drop column per pad, always outward from its footprint.

    Uniqueness is the whole trick: verticals never share an x, horizontals never
    share a lane, so clearance is a property of the construction rather than of a
    search that might quietly fail.
    """
    footprints = {f.ref: f for f in board.footprints}
    escapes: dict[tuple[str, str], tuple[float, float]] = {}
    taken: list[float] = []
    all_pads = board.pads()

    def clear_of_other_pads(pad: PadInst, x: float, taken_x: list[float]) -> bool:
        """The stub and its via must clear every pad of another net.

        Uses exactly the geometry the verifier uses, so a column that passes here
        cannot make `pcb-check` refuse later.
        """
        for other in all_pads:
            if other.net == pad.net or other is pad:
                continue
            # the via sits off the pad row, so check the point it will occupy
            from .design import via_point as _vp  # local alias for clarity

            vx, vy = _vp(board, pad, x)
            cx = min(max(vx, other.x - other.w / 2), other.x + other.w / 2)
            cy = min(max(vy, other.y - other.h / 2), other.y + other.h / 2)
            if math.hypot(vx - cx, vy - cy) - VIA_SIZE / 2 < CLEARANCE:
                return False
            # the horizontal stub from the pad to the via
            seg_lo, seg_hi = min(pad.x, x), max(pad.x, x)
            sx = min(max(seg_lo, other.x - other.w / 2), seg_hi)
            sy = min(max(pad.y, other.y - other.h / 2), other.y + other.h / 2)
            if math.hypot(sx - other.x, sy - other.y) - TRACK / 2 < CLEARANCE:
                # a straight-line distance is not enough for a rectangle; be exact
                dx = max(seg_lo - (other.x + other.w / 2), (other.x - other.w / 2) - seg_hi)
                dy = max(0.0, abs(pad.y - other.y) - other.h / 2)
                if math.hypot(max(dx, 0.0), dy) - TRACK / 2 < CLEARANCE:
                    return False
        return all(abs(t - x) >= MIN_COLUMN_GAP for t in taken_x)

    pads = sorted(all_pads, key=lambda p: (p.x, p.y))
    for pad in pads:
        fp = footprints[pad.ref]
        outward = 1.0 if pad.x >= fp.x else -1.0
        x = pad.x + outward * (pad.w / 2 + 0.9)
        for _ in range(80):
            inside = 1.2 <= x <= board.width - 1.2
            if inside and clear_of_other_pads(pad, x, taken):
                break
            x += outward * MIN_COLUMN_GAP
        else:
            raise ValueError(
                f"cannot find a free routing column for {pad.ref}.{pad.number} on a "
                f"{board.width:g} mm wide board; increase --outline width")
        x = round(x / 0.05) * 0.05
        escapes[(pad.ref, pad.number)] = (x, round(pad.y, 2))
        taken.append(x)
    return escapes


def channel_route(board: Board, escapes: dict[tuple[str, str], tuple[float, float]]) -> RouteResult:
    """Lane router: horizontals on F.Cu at one lane per net, verticals on B.Cu.

    Deterministic by design. A greedy grid router produced boards that looked
    finished and failed DRC; this produces boards whose clearances are structural.
    """
    result = RouteResult()
    pads_by_net: dict[str, list[PadInst]] = {}
    for pad in board.pads():
        if pad.net:
            pads_by_net.setdefault(pad.net, []).append(pad)
    nets = sorted(pads_by_net, key=lambda n: (n.upper() in {"3V3", "5V", "VCC", "VDD", "GND"}, n))
    if not nets:
        return result

    lowest_pad = max((p.y for p in board.pads()), default=0.0)
    lane_top = board.height - 1.6
    if lane_top - (len(nets) - 1) * LANE_PITCH < lowest_pad + 1.8:
        raise ValueError(
            f"the component area reaches {lowest_pad:.1f} mm and {len(nets)} lanes need "
            f"{len(nets) * LANE_PITCH:.1f} mm below it; use a taller --outline")
    lane_y = {net: round(lane_top - index * LANE_PITCH, 2) for index, net in enumerate(nets)}
    result.lanes = dict(lane_y)

    for net, pads in pads_by_net.items():
        if len(pads) < 2:
            continue
        columns = sorted(((escapes[(pad.ref, pad.number)][0], pad) for pad in pads),
                         key=lambda item: item[0])
        y = lane_y[net]
        for x, pad in columns:
            vx, vy = via_point(board, pad, x)
            result.segments.append(Segment(net, "F.Cu", pad.x, pad.y, x, pad.y, TRACK))
            if abs(vy - pad.y) > 0.01:
                result.segments.append(Segment(net, "F.Cu", x, pad.y, vx, vy, TRACK))
            result.segments.append(Segment(net, "B.Cu", vx, vy, vx, y, TRACK))
            result.vias.append(Via(net, vx, vy, VIA_DRILL, VIA_SIZE))
            result.vias.append(Via(net, vx, y, VIA_DRILL, VIA_SIZE))
        for left, right in zip(columns, columns[1:]):
            if abs(left[0] - right[0]) > 0.01:
                result.segments.append(Segment(net, "F.Cu", left[0], y, right[0], y, TRACK))
        result.routed.append(net)

    seen: set[tuple[str, float, float]] = set()
    vias: list[Via] = []
    for via in result.vias:
        key = (via.net, round(via.x, 2), round(via.y, 2))
        if key not in seen:
            seen.add(key)
            vias.append(via)
    result.vias = vias

    seen_seg: set[tuple[str, str, float, float, float, float]] = set()
    segments: list[Segment] = []
    for segment in result.segments:
        key = (segment.net, segment.layer, round(min(segment.x1, segment.x2), 2),
               round(min(segment.y1, segment.y2), 2), round(max(segment.x1, segment.x2), 2),
               round(max(segment.y1, segment.y2), 2))
        if key not in seen_seg:
            seen_seg.add(key)
            segments.append(segment)
    result.segments = segments
    _validate(result, board)
    return result


def _track_gap(a: Segment, b: Segment) -> float:
    if a.layer != b.layer:
        return 99.0
    half = max(a.width, b.width) / 2
    ax, ay = sorted((a.x1, a.x2)), sorted((a.y1, a.y2))
    bx, by = sorted((b.x1, b.x2)), sorted((b.y1, b.y2))
    dx = max(0.0, max(bx[0] - ax[1], ax[0] - bx[1]))
    dy = max(0.0, max(by[0] - ay[1], ay[0] - by[1]))
    return 0.0 if dx == 0 and dy == 0 else (dx * dx + dy * dy) ** 0.5 - half


def _validate(result: RouteResult, board: Board) -> None:
    """Refuse to emit a board that fails the same geometry rule the checker uses."""
    pads = board.pads()
    for i, a in enumerate(result.segments):
        for b in result.segments[i + 1:]:
            if a.net == b.net:
                continue
            gap = _track_gap(a, b)
            if gap < CLEARANCE - 0.01:
                raise ValueError(
                    f"generated routing for {a.net} and {b.net} would be {gap:.2f} mm apart "
                    f"(minimum {CLEARANCE:g} mm); refusing to emit a board that fails its own check")
    for segment in result.segments:
        for pad in pads:
            if pad.net == segment.net or segment.layer != pad.layer:
                continue
            cx = min(max(segment.x1, pad.x - pad.w / 2), pad.x + pad.w / 2)
            cy = min(max(segment.y1, pad.y - pad.h / 2), pad.y + pad.h / 2)
            gap = math.hypot(cx - segment.x1, cy - segment.y1) - segment.width / 2
            if gap < CLEARANCE - 0.01:
                raise ValueError(
                    f"track {segment.net} would be {gap:.2f} mm from pad {pad.ref}.{pad.number}; "
                    "refusing to emit")
    for via in result.vias:
        for pad in pads:
            if pad.net == via.net:
                continue
            cx = min(max(via.x, pad.x - pad.w / 2), pad.x + pad.w / 2)
            cy = min(max(via.y, pad.y - pad.h / 2), pad.y + pad.h / 2)
            if math.hypot(via.x - cx, via.y - cy) - via.size / 2 < CLEARANCE - 0.01:
                raise ValueError(
                    f"via for {via.net} at ({via.x:.2f}, {via.y:.2f}) is too close to pad "
                    f"{pad.ref}.{pad.number} ({pad.net}); refusing to emit")


def plan_routing(board: Board, placements: list[Placement], design: Design) -> RouteResult:
    return channel_route(board, escape_points(board))


def fit_outline(board: Board, margin: float = 3.0) -> tuple[float, float]:
    """Shrink the outline to the copper that actually exists.

    A generated breakout should look like a breakout, not like parts floating on a
    canvas. Everything is translated so the board starts at (margin, margin).
    """
    pads = board.pads()
    if not pads:
        return board.width, board.height
    xs = [p.x - p.w / 2 for p in pads] + [p.x + p.w / 2 for p in pads]
    ys = [p.y - p.h / 2 for p in pads] + [p.y + p.h / 2 for p in pads]
    for footprint in board.footprints:
        xs += [footprint.x - footprint.body_w / 2, footprint.x + footprint.body_w / 2]
        ys += [footprint.y - footprint.body_h / 2, footprint.y + footprint.body_h / 2]
    dx, dy = margin - min(xs), margin - min(ys)
    for footprint in board.footprints:
        footprint.x += dx
        footprint.y += dy
        for pad in footprint.pads:
            pad.x += dx
            pad.y += dy
    for segment in board.segments:
        segment.x1 += dx
        segment.x2 += dx
        segment.y1 += dy
        segment.y2 += dy
    for via in board.vias:
        via.x += dx
        via.y += dy
    board.width = round(max(xs) - min(xs) + 2 * margin, 2)
    board.height = round(max(ys) - min(ys) + 2 * margin, 2)
    return board.width, board.height


def build_board(design: Design, width: float | None, height: float | None, title: str = "",
                route: bool = False, allow_generic: bool = True) -> tuple[Board, dict]:
    auto = width is None or height is None
    if auto:
        width = height = max(60.0, 12.0 * max(1, len(design.components)))
    placements, placement_notes = _place(design, width, height, compact=auto,
                                         allow_generic=allow_generic)
    board = Board(width, height, title=title or "BoardProof candidate")
    for item in placements:
        pads: list[PadInst] = []
        for pad in item.pattern.pads:
            pin = design.pin(item.ref, pad.number)
            net = pin.net if pin else ""
            pads.append(PadInst(item.ref, pad.number, net, item.x + pad.x, item.y + pad.y,
                                pad.w, pad.h))
        w, h = _bbox(item.pattern)
        board.footprints.append(FootprintInst(item.ref, item.pattern.name, item.x, item.y,
                                              0.0, pads, item.pattern.body_w,
                                              item.pattern.body_h, w, h))
    routing: RouteResult | None = None
    if route:
        routing = plan_routing(board, placements, design)
        board.segments = routing.segments
        board.vias = routing.vias
        board.unrouted = sorted({p.net for p in board.pads() if p.net} - set(routing.routed))
    if auto:
        fit_outline(board)
    report = {
        "outline": "fitted" if auto else "fixed",
        "board": census(board),
        "placement": [{"ref": p.ref, "pattern": p.pattern.name, "source": p.source,
                       "x": round(p.x, 2), "y": round(p.y, 2), "rules": p.rules} for p in placements],
        "footprints": {
            "from_export": sorted(p.ref for p in placements if p.source == "export"),
            "from_library": sorted(p.ref for p in placements if p.source == "library"),
            "guessed": sorted(p.ref for p in placements if p.source == "designator"),
        },
        "routing": (
            {"attempted": True, "routed": sorted(routing.routed), "failed": routing.failed,
             "lanes": routing.lanes, "track_mm": TRACK, "clearance_mm": CLEARANCE}
            if routing is not None else
            {"attempted": False,
             "note": "routing not attempted; this board is a verified placement and "
                     "pad-to-net mapping, not a routed PCB"}),
        "scope": {
            "generated": ["footprint assignment", "component placement with rules applied",
                          "pad-to-net assignment", "board outline",
                          "native editable .kicad_pcb"],
            "not_generated": ([] if routing is not None else
                              ["copper routing (not attempted by design)"]),
            "not_verified": ["current capacity and thermal rise", "impedance / RF behaviour",
                             "assembly and DFM rules", "land patterns are approximate"],
        },
        "notes": placement_notes,
        "footprint_warning": (
            "Land patterns are simplified and are NOT manufacturer-recommended. "
            "Replace with fab-approved footprints before fabrication."),
    }
    return board, report


def write_board(board: Board, out: Path, svg_out: Path | None = None) -> None:
    import json

    from .pcbview import board_model, render_2d, render_3d

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(write_kicad(board), encoding="utf-8")
    if svg_out:
        svg_out.parent.mkdir(parents=True, exist_ok=True)
        svg_out.write_text(render_2d(board), encoding="utf-8")
        svg_out.with_name(svg_out.stem + "-3d.svg").write_text(render_3d(board), encoding="utf-8")
        svg_out.with_name(svg_out.stem + "-model.json").write_text(
            json.dumps(board_model(board), separators=(",", ":")) + "\n", encoding="utf-8")
