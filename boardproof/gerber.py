"""Fab outputs: Gerbers and an Excellon drill file, zipped, via kicad-cli.

If kicad-cli is missing we say so instead of shipping a broken zip - the same
rule the rest of the tool follows.
"""
from __future__ import annotations

import shutil
import subprocess
from tempfile import TemporaryDirectory
import zipfile
from pathlib import Path

from .pcbcheck import find_kicad_cli


def export(board_path: Path, out_dir: Path) -> dict:
    cli = find_kicad_cli()
    board_path, out_dir = Path(board_path), Path(out_dir)
    if not cli:
        return {"available": False,
                "note": "kicad-cli not installed; Gerbers were not produced"}
    if not board_path.is_file():
        return {"available": False, "note": f"board not found: {board_path}"}

    out_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".gerber-", dir=out_dir) as scratch:
        try:
            return _export(cli, board_path, out_dir, Path(scratch))
        except OSError as exc:
            return {"available": True, "error": f"could not save Gerbers: {exc}"}


def _export(cli: str, board_path: Path, out_dir: Path, scratch: Path) -> dict:
    gerbers = scratch / "layers"
    gerbers.mkdir()
    commands = [
        [cli, "pcb", "export", "gerbers", "--output", str(gerbers) + "/", str(board_path)],
        [cli, "pcb", "export", "drill", "--format", "excellon",
         "--output", str(gerbers) + "/", str(board_path)],
    ]
    for command in commands:
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.SubprocessError) as exc:
            return {"available": True, "error": f"{command[2]} failed: {exc}"}
        if proc.returncode != 0:
            return {"available": True,
                    "error": (proc.stderr or proc.stdout or "kicad-cli error").strip()[:300]}

    files = sorted(p for p in gerbers.iterdir() if p.is_file())
    if not files:
        return {"available": True, "error": "kicad-cli produced no files"}
    archive = out_dir / (board_path.stem + "-gerbers.zip")
    pending = scratch / archive.name
    with zipfile.ZipFile(pending, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            bundle.write(path, path.name)
    layers = out_dir / "gerbers"
    layers.mkdir(exist_ok=True)
    for path in files:
        shutil.copy2(path, layers / path.name)
    pending.replace(archive)
    return {
        "available": True,
        "archive": archive.name,
        "files": [p.name for p in files],
        "bytes": archive.stat().st_size,
        "layers": len(files),
    }
