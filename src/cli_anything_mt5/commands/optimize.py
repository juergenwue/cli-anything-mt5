"""`climt5 optimize` - run a Strategy Tester optimization pass.

Optimization-range syntax for .set lines:
    Name=default||start||step||stop||F
where F is 0 (fixed) or 1 (optimize). We generate those lines from
a JSON ranges file of the form::

    {
      "LotSize":     {"start": 0.05, "step": 0.05, "stop": 0.50, "default": 0.10},
      "TakeProfit":  {"start": 20,   "step": 10,   "stop": 120,  "default": 50}
    }

Leaving a param out of the ranges file keeps it fixed at its source default.
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import click

from .. import config, ssh
from ..commands.backtest import _launch_terminal, _render_tester_ini
from ..output import emit_error, emit_ok


def _write_opt_set(path: Path, ranges: dict) -> None:
    lines = []
    for name, spec in ranges.items():
        default = spec.get("default", spec.get("start", 0))
        start = spec["start"]
        step = spec["step"]
        stop = spec["stop"]
        flag = int(spec.get("enabled", 1))
        lines.append(f"{name}={default}||{start}||{step}||{stop}||{flag}")
    text = "\r\n".join(lines) + "\r\n"
    path.write_bytes(b"\xff\xfe" + text.encode("utf-16-le"))


@click.command("optimize", help="Run a Strategy Tester optimization pass on the VM.")
@click.argument("expert", type=str)
@click.option("--symbol", required=True)
@click.option("--tf", "period", required=True)
@click.option("--from", "from_date", required=True, help="YYYY.MM.DD")
@click.option("--to", "to_date", required=True, help="YYYY.MM.DD")
@click.option(
    "--ranges",
    "ranges_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--mode",
    type=click.Choice(["slow", "fast", "genetic"]),
    default="genetic",
    show_default=True,
    help="slow=full enumeration (1), fast=ticks-only (2), genetic=GA (4).",
)
@click.option(
    "--criterion",
    type=click.IntRange(0, 8),
    default=6,
    show_default=True,
    help="Optimization criterion (6 = Custom, see MT5 docs).",
)
@click.option("--terminal-id", default=None)
@click.option("--timeout", type=int, default=None)
@click.option("--json", "json_mode", is_flag=True)
def optimize_cmd(
    expert: str,
    symbol: str,
    period: str,
    from_date: str,
    to_date: str,
    ranges_path: Path,
    mode: str,
    criterion: int,
    terminal_id: str | None,
    timeout: int | None,
    json_mode: bool,
) -> None:
    tid = terminal_id or config.MT5_TERMINAL_ID
    if not tid:
        emit_error(
            code="terminal_id_missing",
            message="No MT5_TERMINAL_ID configured.",
            json_mode=json_mode,
        )
    timeout = timeout or config.MT5_TESTER_TIMEOUT

    try:
        ranges = json.loads(ranges_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        emit_error(code="ranges_invalid", message=str(e), json_mode=json_mode)
    if not isinstance(ranges, dict):
        emit_error(
            code="ranges_invalid",
            message="Ranges JSON must be an object.",
            json_mode=json_mode,
        )

    mode_to_opt = {"slow": 1, "fast": 2, "genetic": 4}
    optimization = mode_to_opt[mode]

    tester_dir_expr = config.terminal_tester_dir(tid)
    try:
        tester_dir = ssh.resolve_powershell_path(tester_dir_expr)
    except ssh.SshError as e:
        emit_error(code="path_resolve_failed", message=str(e), json_mode=json_mode)

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    report_name = f"climt5-opt-{expert}-{stamp}.xml"
    set_name = f"climt5-opt-{expert}-{stamp}.set"
    remote_report = f"{tester_dir}\\{report_name}".replace("\\", "/")
    remote_set = f"{tester_dir}\\{set_name}".replace("\\", "/")
    remote_ini = f"{tester_dir}\\climt5-opt.ini".replace("\\", "/")

    ctx = {
        "generator_version": "climt5",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "expert": expert,
        "symbol": symbol,
        "period": period,
        "from_date": from_date,
        "to_date": to_date,
        "optimization": optimization,
        "optimization_criterion": criterion,
        "report": remote_report,
        "set_file": remote_set,
    }
    ini_text = _render_tester_ini(ctx)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ini", encoding="utf-8", delete=False
    ) as tmp_ini:
        tmp_ini.write(ini_text)
        local_ini = Path(tmp_ini.name)

    with tempfile.NamedTemporaryFile(suffix=".set", delete=False) as tmp_set:
        local_set = Path(tmp_set.name)
    _write_opt_set(local_set, ranges)

    try:
        try:
            ssh.scp_to_vm(local_ini, f'(Join-Path "{tester_dir}" "climt5-opt.ini")')
            ssh.scp_to_vm(local_set, f'(Join-Path "{tester_dir}" "{set_name}")')
        except ssh.SshError as e:
            emit_error(code="scp_failed", message=str(e), json_mode=json_mode)

        _launch_terminal(remote_ini, tid, timeout)
    finally:
        local_ini.unlink(missing_ok=True)
        local_set.unlink(missing_ok=True)

    emit_ok(
        {
            "expert": expert,
            "symbol": symbol,
            "period": period,
            "from": from_date,
            "to": to_date,
            "mode": mode,
            "optimization_criterion": criterion,
            "remote_report_xml": remote_report,
            "remote_set": remote_set,
            "ranges": ranges,
        },
        json_mode=json_mode,
    )
