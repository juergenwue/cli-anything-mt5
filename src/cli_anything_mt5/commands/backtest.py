"""`climt5 backtest` - run an MT5 Strategy Tester cycle on the VM.

Flow:
  1. Render tester.ini from the Jinja2 template.
  2. SCP the .ini (+ optional .set) to the terminal's Tester directory.
  3. Launch `terminal64.exe /config:<ini> /portable` (with timeout).
  4. SCP the resulting HTML report back.
  5. Parse and return metrics.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

import click
from jinja2 import Template

from .. import config, ssh
from ..output import emit_error, emit_ok
from ..parsers import tester_report


def _render_tester_ini(ctx: dict) -> str:
    tpl_text = resources.files("cli_anything_mt5.templates").joinpath("tester.ini.j2").read_text(
        encoding="utf-8"
    )
    return Template(tpl_text, keep_trailing_newline=True).render(**ctx)


def _launch_terminal(ini_remote: str, terminal_id: str, timeout: int) -> None:
    """Invoke terminal64.exe with the prepared .ini; ignore exit code (MT5 quirk)."""
    editor = f'"{config.MT5_ROOT}/terminal64.exe"'
    cmd = f'cmd /c {editor} /config:"{ini_remote}" /portable'
    # MT5 terminal often returns non-zero even on success; we rely on the
    # resulting report file to confirm a good run.
    try:
        ssh.ssh_cmd(cmd, timeout=timeout)
    except ssh.SshError:
        pass


@click.command("backtest", help="Run a single Strategy Tester cycle on the VM.")
@click.argument("expert", type=str)
@click.option("--symbol", required=True)
@click.option("--tf", "period", required=True, help="Timeframe (M1, M5, H1, ...).")
@click.option("--from", "from_date", required=True, help="YYYY.MM.DD")
@click.option("--to", "to_date", required=True, help="YYYY.MM.DD")
@click.option(
    "--model",
    type=click.IntRange(0, 4),
    default=4,
    show_default=True,
    help="0=every tick, 1=1-minute OHLC, 2=open price, 4=every tick based on real ticks.",
)
@click.option("--deposit", type=int, default=10000, show_default=True)
@click.option("--leverage", type=int, default=100, show_default=True)
@click.option("--currency", default="USD", show_default=True)
@click.option(
    "--set",
    "set_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Optional .set parameter file to upload and reference.",
)
@click.option("--terminal-id", default=None, help="Override MT5_TERMINAL_ID.")
@click.option(
    "--timeout",
    type=int,
    default=None,
    help="Max seconds for the tester run (default: MT5_TESTER_TIMEOUT or 900).",
)
@click.option("--json", "json_mode", is_flag=True)
def backtest_cmd(
    expert: str,
    symbol: str,
    period: str,
    from_date: str,
    to_date: str,
    model: int,
    deposit: int,
    leverage: int,
    currency: str,
    set_file: Path | None,
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

    tester_dir_expr = config.terminal_tester_dir(tid)
    try:
        tester_dir = ssh.resolve_powershell_path(tester_dir_expr)
    except ssh.SshError as e:
        emit_error(code="path_resolve_failed", message=str(e), json_mode=json_mode)

    report_name = (
        f"climt5-{expert}-{symbol}-{period}-{from_date}-{to_date}.html".replace(" ", "_")
    )
    remote_report = f"{tester_dir}\\{report_name}".replace("\\", "/")
    remote_ini = f"{tester_dir}\\climt5.ini".replace("\\", "/")
    remote_set = None
    if set_file is not None:
        remote_set = f"{tester_dir}\\{set_file.name}".replace("\\", "/")

    ctx = {
        "generator_version": "climt5",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "expert": expert,
        "symbol": symbol,
        "period": period,
        "from_date": from_date,
        "to_date": to_date,
        "model": model,
        "deposit": deposit,
        "leverage": leverage,
        "currency": currency,
        "report": remote_report,
        "set_file": remote_set,
    }
    ini_text = _render_tester_ini(ctx)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ini", encoding="utf-8", delete=False
    ) as tmp:
        tmp.write(ini_text)
        local_ini = Path(tmp.name)
    try:
        try:
            ssh.scp_to_vm(local_ini, f'(Join-Path "{tester_dir}" "climt5.ini")')
            if set_file is not None:
                ssh.scp_to_vm(set_file, f'(Join-Path "{tester_dir}" "{set_file.name}")')
        except ssh.SshError as e:
            emit_error(code="scp_failed", message=str(e), json_mode=json_mode)

        _launch_terminal(remote_ini, tid, timeout)

        # Fetch report
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as rpt_tmp:
            local_report = Path(rpt_tmp.name)
        try:
            ssh.scp_from_vm(f'"{remote_report}"', local_report)
        except ssh.SshError as e:
            emit_error(
                code="report_missing",
                message=f"Could not retrieve tester report: {e}",
                json_mode=json_mode,
                details={"expected_remote_path": remote_report},
            )

        try:
            report = tester_report.parse_file(local_report)
        finally:
            local_report.unlink(missing_ok=True)
    finally:
        local_ini.unlink(missing_ok=True)

    emit_ok(
        {
            "expert": expert,
            "symbol": symbol,
            "period": period,
            "from": from_date,
            "to": to_date,
            "remote_report": remote_report,
            "metrics": report.metrics,
        },
        json_mode=json_mode,
    )
