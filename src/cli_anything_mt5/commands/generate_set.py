"""`climt5 generate-set` - produce an MT5 `.set` file from a JSON param map.

The `.set` format is UTF-16-LE with BOM and uses `Param=Value` per line.
For optimization fields MT5 uses a 5-tuple suffix `||start||step||stop||flag`
(flag 0 = fixed, 1 = enabled). We only emit the fixed-value form here;
optimization ranges are written by `climt5 optimize`.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from ..output import emit_error, emit_ok
from ..parsers import mql5_source


def _fmt_value(val: object) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    return str(val)


def _write_set(path: Path, entries: list[tuple[str, str]]) -> None:
    lines = [f"{k}={v}" for k, v in entries]
    text = "\r\n".join(lines) + "\r\n"
    path.write_bytes(b"\xff\xfe" + text.encode("utf-16-le"))


@click.command(
    "generate-set",
    help="Write an MT5 .set file from a JSON map of input overrides.",
)
@click.option(
    "--params",
    "params_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help='JSON object: {"Name": value, ...}',
)
@click.option(
    "--source",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Optional .mq5 source — unknown param names will raise an error.",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
)
@click.option("--json", "json_mode", is_flag=True)
def generate_set(
    params_path: Path,
    source: Path | None,
    output_path: Path,
    json_mode: bool,
) -> None:
    try:
        params = json.loads(params_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        emit_error(code="params_invalid", message=str(e), json_mode=json_mode)
    if not isinstance(params, dict):
        emit_error(
            code="params_invalid",
            message="Params JSON must be an object.",
            json_mode=json_mode,
        )

    if source is not None:
        known = {p.name for p in mql5_source.extract_inputs(mql5_source._read_text(source))}
        unknown = sorted(k for k in params if k not in known)
        if unknown:
            emit_error(
                code="unknown_params",
                message=f"Params not declared in {source.name}: {', '.join(unknown)}",
                json_mode=json_mode,
                details={"unknown": unknown, "known": sorted(known)},
            )

    entries = [(k, _fmt_value(v)) for k, v in params.items()]
    _write_set(output_path, entries)

    emit_ok(
        {
            "output": str(output_path),
            "count": len(entries),
            "params": [k for k, _ in entries],
        },
        json_mode=json_mode,
    )
