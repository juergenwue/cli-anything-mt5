"""`climt5 parse-report` - normalize a Strategy Tester HTML report."""

from __future__ import annotations

from pathlib import Path

import click

from ..output import emit_error, emit_ok
from ..parsers import tester_report


@click.command("parse-report", help="Parse an MT5 tester HTML/XML report.")
@click.argument("report", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--metrics",
    default=None,
    help="Comma-separated list of canonical metric keys to keep (default: all).",
)
@click.option("--json", "json_mode", is_flag=True)
def parse_report(report: Path, metrics: str | None, json_mode: bool) -> None:
    try:
        parsed = tester_report.parse_file(report)
    except Exception as e:
        emit_error(
            code="parse_failed",
            message=f"Could not parse report: {e}",
            json_mode=json_mode,
            details={"path": str(report)},
        )

    data = parsed.to_dict()
    data["path"] = str(report)
    if metrics:
        wanted = {m.strip() for m in metrics.split(",") if m.strip()}
        data["metrics"] = {k: v for k, v in data["metrics"].items() if k in wanted}
    emit_ok(data, json_mode=json_mode)
