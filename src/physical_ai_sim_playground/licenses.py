"""Refuse a dist/ that still carries a non-commercial or copyleft asset.

The scan looks at LICENSE* and NOTICE* files, at every recorded ``spdx``
value, and at file names. A dual license such as ``MIT OR GPL-3.0-or-later``
is accepted when one side is usable on its own: the site takes that side.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Phrases, not the letters NC: the Apache text and the filename LICENCE both
# contain those letters without being a non-commercial grant.
_FILE_MARKERS = (
    re.compile(r"by-nc", re.I),
    re.compile(r"by-nd", re.I),
    re.compile(r"non-?commercial", re.I),
    re.compile(r"no derivatives", re.I),
    re.compile(r"\bgpl\b", re.I),
    re.compile(r"gpl-\d", re.I),
    re.compile(r"cern-ohl", re.I),
    re.compile(r"no license", re.I),
    re.compile(r"unlicensed", re.I),
)

_NAME_MARKERS = re.compile(
    r"lafan|dance1_subject2|dance_1_subject_2|microduck|by-nc|by-nd|gpl|cern-ohl",
    re.I,
)

_SPDX_BAD = ("NC", "ND", "GPL", "CERN-OHL")


def problems(dist: Path) -> list[str]:
    """Human-readable reasons ``dist`` must not ship, or an empty list."""
    found: list[str] = []
    if not dist.is_dir():
        return [f"{dist} is not a directory"]
    for path in sorted(dist.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(dist).as_posix()
        if _NAME_MARKERS.search(relative):
            found.append(f"banned name {relative}")
        if path.name.startswith(("LICENSE", "NOTICE")):
            text = path.read_text(errors="replace")
            for marker in _FILE_MARKERS:
                if marker.search(text):
                    found.append(f"{relative} matches {marker.pattern}")
                    break
    manifest = dist / "manifest.json"
    if manifest.is_file():
        found.extend(_spdx_problems(json.loads(manifest.read_text())))
    return found


def _spdx_problems(node: object, where: str = "manifest") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{where}.{key}"
            if key == "spdx" and isinstance(value, str):
                reason = _spdx_bad(value)
                if reason:
                    found.append(f"{child} = {value!r} ({reason})")
            else:
                found.extend(_spdx_problems(value, child))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_spdx_problems(value, f"{where}[{index}]"))
    return found


def _spdx_bad(expr: str) -> str | None:
    """Why ``expr`` cannot be satisfied by a license this site may ship."""
    parts = re.split(r"\s+OR\s+", expr.strip())
    if not parts or any(not part.strip() for part in parts):
        return "empty SPDX id"
    bad = [part for part in parts if _one_bad(part)]
    if len(bad) == len(parts):
        return "no alternative this site can ship"
    return None


def _one_bad(part: str) -> bool:
    text = part.upper()
    if any(token in text for token in _SPDX_BAD):
        return True
    if "NO LICENSE" in text or text.strip() in {"NONE", "UNLICENSED"}:
        return True
    return False
