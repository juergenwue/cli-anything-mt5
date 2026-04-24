"""`climt5 resolve-includes` - walk the transitive `#include` graph locally.

Scope: local resolution only. If the caller wants to resolve `<System.mqh>`
against the terminal's MQL5/Include directory on the VM, they can point
`--include-root` at a mirrored local copy.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

import click

from ..output import emit_error, emit_ok
from ..parsers import mql5_source


def _resolve_one(
    base: Path,
    ref: mql5_source.IncludeRef,
    include_root: Path | None,
    seen: set[Path],
) -> Path | None:
    candidates: list[Path] = []
    if not ref.system:
        candidates.append(base.parent / ref.path)
    if include_root is not None:
        candidates.append(include_root / ref.path)
    for c in candidates:
        try:
            c_res = c.resolve()
        except OSError:
            continue
        if c_res.exists() and c_res not in seen:
            return c_res
    return None


@click.command(
    "resolve-includes",
    help="Return the transitive #include tree of an .mq5/.mqh file.",
)
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--include-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Local mirror of MQL5/Include for resolving `<...>` includes.",
)
@click.option(
    "--max-depth",
    default=10,
    show_default=True,
    help="Abort recursion after this many levels.",
)
@click.option("--json", "json_mode", is_flag=True)
def resolve_includes(
    source: Path,
    include_root: Path | None,
    max_depth: int,
    json_mode: bool,
) -> None:
    root = source.resolve()
    seen: set[Path] = {root}
    tree: list[dict] = []
    missing: list[dict] = []
    queue: deque[tuple[Path, int]] = deque([(root, 0)])

    while queue:
        current, depth = queue.popleft()
        try:
            text = mql5_source._read_text(current)
        except OSError as e:
            emit_error(
                code="read_failed",
                message=f"Could not read {current}: {e}",
                json_mode=json_mode,
            )
        refs = mql5_source.extract_includes(text)
        for ref in refs:
            resolved = _resolve_one(current, ref, include_root, seen)
            entry = {
                "from": str(current),
                "ref": ref.path,
                "system": ref.system,
                "depth": depth,
            }
            if resolved is None:
                missing.append(entry)
                continue
            entry["resolved"] = str(resolved)
            tree.append(entry)
            if depth + 1 <= max_depth:
                seen.add(resolved)
                queue.append((resolved, depth + 1))

    emit_ok(
        {
            "root": str(root),
            "files": sorted(str(p) for p in seen),
            "edges": tree,
            "missing": missing,
        },
        json_mode=json_mode,
    )
