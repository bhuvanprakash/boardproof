"""Parse simple numeric #define statements, fail closed for unknown expressions.

The first release intentionally does NOT claim to compile or understand arbitrary
C/C++ firmware. Unresolved macros become unknown findings, never an inferred pass.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import re

_DEFINE = re.compile(r'^\s*#\s*define\s+([A-Za-z_]\w*)\s+([^\r\n]+)', re.MULTILINE)
_NUMBER = re.compile(r'^\(?\s*(0[xX][0-9a-fA-F]+|[0-9]+)(?:[uUlL]*)\s*\)?$')


def parse_defines(path: Path) -> dict[str, int]:
    """Cached on (path, mtime, size) so repeated checks do not re-read or re-parse."""
    try:
        stat = path.stat()
    except OSError as exc:
        raise ValueError(f"cannot read firmware file {path}: {exc}") from exc
    return dict(_parse_cached(str(path), stat.st_mtime_ns, stat.st_size))


@lru_cache(maxsize=64)
def _parse_cached(path_str: str, _mtime: int, _size: int) -> dict[str, int]:
    text = Path(path_str).read_text(encoding="utf-8")
    values: dict[str, int] = {}
    for m in _DEFINE.finditer(text):
        value = m.group(2).split("//", 1)[0].strip()
        num = _NUMBER.fullmatch(value)
        if num:
            values[m.group(1)] = int(num.group(1), 0)
    return values
