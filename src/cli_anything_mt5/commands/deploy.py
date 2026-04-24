"""`climt5 deploy` - upload an .mq5/.mqh/.ex5 and optionally verify."""

from __future__ import annotations

from pathlib import Path

import click

from .. import config, ssh
from ..output import emit_error, emit_ok


def _stat_remote(remote_path_expr: str) -> dict | None:
    """Return {size, mtime} for a remote file or None if missing."""
    script = (
        f"$p = {remote_path_expr}; "
        "if (Test-Path $p) { "
        "$i = Get-Item $p; "
        "Write-Output (\"$($i.Length)`t$($i.LastWriteTime.ToString('o'))\") "
        "} else { Write-Output 'MISSING' }"
    )
    try:
        out = ssh.ssh_powershell(script)
    except ssh.SshError:
        return None
    if out.strip() == "MISSING" or "\t" not in out:
        return None
    size, mtime = out.split("\t", 1)
    return {"size_bytes": int(size), "mtime": mtime}


@click.command("deploy", help="Deploy an MQL5 source or compiled .ex5 to the VM.")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--target",
    type=click.Choice(["Experts", "Indicators", "Scripts", "Include"]),
    default=None,
    help="MQL5 subdirectory (default: inferred).",
)
@click.option("--terminal-id", default=None, help="Override MT5_TERMINAL_ID.")
@click.option("--verify/--no-verify", default=True, help="Verify mtime after upload.")
@click.option("--json", "json_mode", is_flag=True)
def deploy_cmd(
    source: Path,
    target: str | None,
    terminal_id: str | None,
    verify: bool,
    json_mode: bool,
) -> None:
    tid = terminal_id or config.MT5_TERMINAL_ID
    if not tid:
        emit_error(
            code="terminal_id_missing",
            message="No MT5_TERMINAL_ID configured.",
            json_mode=json_mode,
        )

    ext = source.suffix.lower()
    if target is None:
        if ext == ".mqh":
            target = "Include"
        elif ext == ".ex5":
            target = "Experts"  # neutral default; user can override
        else:
            target = "Experts"

    remote_dir_expr = config.terminal_mql5_dir(tid, target)
    try:
        resolved_dir = ssh.scp_to_vm(source, remote_dir_expr)
    except ssh.SshError as e:
        emit_error(code="scp_failed", message=str(e), json_mode=json_mode)

    data: dict = {
        "source": str(source),
        "target": target,
        "terminal_id": tid,
        "remote_dir": resolved_dir,
        "verified": False,
    }

    if verify:
        remote_file_expr = (
            f'(Join-Path $env:APPDATA "MetaQuotes\\Terminal\\{tid}\\MQL5\\{target}\\{source.name}")'
        )
        stat = _stat_remote(remote_file_expr)
        if stat is None:
            emit_error(
                code="verify_failed",
                message="Uploaded file not found on VM after SCP.",
                json_mode=json_mode,
                details=data,
            )
        data["remote_stat"] = stat
        local_size = source.stat().st_size
        data["local_size_bytes"] = local_size
        if stat["size_bytes"] != local_size:
            emit_error(
                code="size_mismatch",
                message=(
                    f"Size mismatch: local {local_size} vs remote {stat['size_bytes']}."
                ),
                json_mode=json_mode,
                details=data,
            )
        data["verified"] = True

    emit_ok(data, json_mode=json_mode)
