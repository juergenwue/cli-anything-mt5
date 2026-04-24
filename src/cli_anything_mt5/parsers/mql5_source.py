"""Parse MQL5 source files — `input`/`sinput`/`extern` declarations and `#include` directives.

The grammar is intentionally permissive; we favour extracting as much as we
can over strict correctness. MQL5 allows trailing `// comment strings` after
the default value which we capture as the `label` (MT5 uses them as the UI
label in the parameter list).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_INPUT_RE = re.compile(
    r"""
    ^\s*
    (?P<kind>input|sinput|extern)\s+
    (?P<type>[A-Za-z_][A-Za-z0-9_]*)\s+
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    (?:\s*=\s*(?P<default>
        "(?:\\.|[^"\\])*"    # string literal
        | '(?:\\.|[^'\\])*'
        | [^;/]+
    ))?
    \s*;
    \s*(?://\s*(?P<label>.*))?
    \s*$
    """,
    re.VERBOSE,
)

_INCLUDE_RE = re.compile(
    r'^\s*#include\s+(?P<quote>["<])(?P<path>[^">]+)[">]',
    re.MULTILINE,
)

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


@dataclass
class InputParam:
    name: str
    type: str
    default: str | None
    kind: str  # input | sinput | extern
    label: str | None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class IncludeRef:
    path: str
    system: bool  # True for <...>, False for "..."

    def to_dict(self) -> dict:
        return {"path": self.path, "system": self.system}


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le", errors="replace")
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def _strip_block_comments(text: str) -> str:
    return _BLOCK_COMMENT_RE.sub("", text)


def extract_inputs(text: str) -> list[InputParam]:
    """Return `input`/`sinput`/`extern` declarations in source order."""
    cleaned = _strip_block_comments(text)
    params: list[InputParam] = []
    for raw_line in cleaned.splitlines():
        # Skip lines that are only comments
        line = raw_line.rstrip("\n")
        m = _INPUT_RE.match(line)
        if not m:
            continue
        default = m.group("default")
        if default is not None:
            default = default.strip()
        label = m.group("label")
        if label is not None:
            label = label.strip()
        params.append(
            InputParam(
                name=m.group("name"),
                type=m.group("type"),
                default=default,
                kind=m.group("kind"),
                label=label or None,
            )
        )
    return params


def extract_includes(text: str) -> list[IncludeRef]:
    """Return `#include` directives in source order."""
    cleaned = _strip_block_comments(text)
    # Remove line comments so we don't pick up commented-out includes
    cleaned = _LINE_COMMENT_RE.sub("", cleaned)
    return [
        IncludeRef(path=m.group("path"), system=m.group("quote") == "<")
        for m in _INCLUDE_RE.finditer(cleaned)
    ]


def parse_file(path: Path) -> dict:
    """High-level convenience: parse inputs + includes from a single file."""
    text = _read_text(Path(path))
    return {
        "path": str(path),
        "inputs": [p.to_dict() for p in extract_inputs(text)],
        "includes": [i.to_dict() for i in extract_includes(text)],
    }
