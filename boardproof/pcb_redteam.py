"""Red team for the physical design.

Same idea as the schematic red team, one layer down: mutate the *board* and ask
whether the verifier notices. A verifier that cannot catch a swapped pad net is
not a verifier, it is a screenshot.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .model import Design
from .pcb import Board, FootprintInst, PadInst, Segment
from .pcbcheck import CLEARANCE, check_board


def _faults(board: Board) -> list[dict]:
    faults: list[dict] = []
    pads = board.pads()
    nets = sorted({p.net for p in pads if p.net})

    def add(fault_id: str, kind: str, summary: str, expect: set[str], mutate) -> None:
        faults.append({"id": fault_id, "kind": kind, "summary": summary,
                       "expect": expect, "mutate": mutate})

    # 1. a pad silently wired to the wrong net (the classic symbol/pad trap)
    for pad in pads:
        if pad.net and len(nets) > 1:
            wrong = next(n for n in nets if n != pad.net)
            add(f"pad-net:{pad.ref}.{pad.number}", "pad_net_swap",
                f"{pad.ref}.{pad.number} ({pad.net}) rewired to {wrong}", {"PAD_NET_MISMATCH"},
                lambda pad=pad, wrong=wrong: [p.__setattr__("net", wrong)
                                              for f in board.footprints for p in f.pads
                                              if p is pad])
            break

    # 2. a component that never made it onto the board
    if len(board.footprints) > 1:
        victim = board.footprints[-1]
        add(f"missing:{victim.ref}", "drop_footprint",
            f"{victim.ref} ({victim.pattern}) missing from the board", {"MISSING_FOOTPRINT"},
            lambda victim=victim: board.footprints.remove(victim))

    # 3. a track deleted so a net is no longer continuous
    if board.segments:
        victim = board.segments[0]
        add(f"unrouted:{victim.net}", "drop_track",
            f"track carrying {victim.net} deleted", {"UNROUTED_NET"},
            lambda victim=victim: board.segments.remove(victim))

    # 4. copper placed too close to an unrelated net
    if board.segments:
        host = board.segments[0]
        other = next((p for p in pads if p.net != host.net), None)
        if other is not None:
            add("clearance-nudge", "clearance",
                f"a {host.net} track pushed to {CLEARANCE / 2:.2f} mm from an unrelated pad",
                {"CLEARANCE"},
                lambda host=host, other=other: board.segments.append(
                    Segment(host.net, "F.Cu", other.x + other.w / 2 + 0.15, other.y,
                            other.x + other.w / 2 + 2.0, other.y, 0.25)))

    # 5. a footprint (and its pads) shifted off the outline
    if board.footprints:
        victim = board.footprints[0]

        def shift(victim=victim, board=board) -> None:
            dx = board.width + 3.0 - victim.x
            victim.x += dx
            for pad in victim.pads:
                pad.x += dx

        add(f"offboard:{victim.ref}", "off_board",
            f"{victim.ref} moved outside the board outline",
            {"OUT_OF_BOUNDS", "CLEARANCE"}, shift)
    return faults


def check_board_board(board_path: Path) -> Board:
    """Read the board file into the model the checks operate on."""
    from .pcb import read_kicad

    return read_kicad(board_path.read_text(encoding="utf-8"))


def run_pcb_redteam(board_path: Path, design: Design) -> dict:
    baseline = check_board(board_path, design, run_drc=False)
    if baseline["status"] != "passed":
        return {"kind": "pcb-redteam", "available": False, "faults": [],
                "score": {"caught": 0, "faults": 0, "gaps": 0, "ratio": 0.0},
                "suggestions": [],
                "reason": "the board already fails its own checks, so an injected fault cannot "
                          "be told apart from an existing violation",
                "baseline": baseline["counts"]}

    text_before = board_path.read_text(encoding="utf-8")
    plan = _faults(check_board_board(board_path))
    results: list[dict] = []
    suggestions: list[str] = []
    for fault in plan:
        trial = check_board_board(board_path)
        mutation = _rebind(trial, fault["id"])
        if mutation is None:
            continue
        mutation()
        findings = check_board(board_path, design, board=trial, run_drc=False)
        fired = {f["code"] for f in findings["findings"] if f["severity"] in {"error", "notice"}}
        caught_by = sorted(fired & fault["expect"])
        results.append({"id": fault["id"], "kind": fault["kind"], "summary": fault["summary"],
                        "status": "caught" if caught_by else "gap",
                        "caught_by": caught_by, "expected": sorted(fault["expect"]),
                        "observed": sorted(fired)})
        if not caught_by:
            suggestions.append(
                f"{fault['summary']}: the physical check did not fire. Add or tighten the "
                "corresponding layout check before trusting this board.")
    if board_path.read_text(encoding="utf-8") != text_before:          # pragma: no cover
        raise RuntimeError("red team mutated the board file on disk; refusing to continue")
    caught = [r for r in results if r["status"] == "caught"]
    ratio = (len(caught) / len(results)) if results else 1.0
    return {
        "kind": "pcb-redteam",
        "board": str(board_path),
        "faults": results,
        "score": {"caught": len(caught), "faults": len(results),
                  "gaps": len(results) - len(caught), "ratio": round(ratio, 3)},
        "suggestions": suggestions,
        "note": "Mutation testing of the layout verifier. Not proof of manufacturability.",
    }


def _rebind(board: Board, fault_id: str):
    """Rebuild the mutation closures against a specific Board instance."""
    for fault in _faults(board):
        if fault["id"] == fault_id:
            return fault["mutate"]
    return None
