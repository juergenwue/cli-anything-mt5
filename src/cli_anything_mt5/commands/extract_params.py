"""`climt5 extract-params` - dump `input`/`sinput`/`extern` variables as JSON."""

from __future__ import annotations

from pathlib import Path

import click

from ..output import emit_error, emit_ok
from ..parsers import mql5_source


@click.command("extract-params", help="Extract `input`/`sinput`/`extern` variables from an .mq5/.mqh file.")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--json", "json_mode", is_flag=True)
def extract_params(source: Path, json_mode: bool) -> None:
    try:
        parsed = mql5_source.parse_file(source)
    except OSError as e:
        emit_error(
            code="read_failed",
            message=f"Could not read source: {e}",
            json_mode=json_mode,
            details={"path": str(source)},
        )

    emit_ok(
        {
            "path": parsed["path"],
            "count": len(parsed["inputs"]),
            "inputs": parsed["inputs"],
        },
        json_mode=json_mode,
    )
