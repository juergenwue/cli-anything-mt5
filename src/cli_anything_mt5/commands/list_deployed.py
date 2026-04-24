"""`climt5 list-deployed` - enumerate MQL5 artefacts on the VM."""

from __future__ import annotations

import click

from .. import config, ssh
from ..output import emit_error, emit_ok


@click.command("list-deployed", help="List .ex5 (or .mq5/.mqh) files on the VM.")
@click.option(
    "--target",
    type=click.Choice(["Experts", "Indicators", "Scripts", "Include"]),
    default="Experts",
    show_default=True,
)
@click.option(
    "--ext",
    type=click.Choice(["ex5", "mq5", "mqh"]),
    default="ex5",
    show_default=True,
)
@click.option("--terminal-id", default=None, help="Override MT5_TERMINAL_ID.")
@click.option("--json", "json_mode", is_flag=True)
def list_deployed(target: str, ext: str, terminal_id: str | None, json_mode: bool) -> None:
    tid = terminal_id or config.MT5_TERMINAL_ID
    if not tid:
        emit_error(
            code="terminal_id_missing",
            message="No MT5_TERMINAL_ID configured.",
            json_mode=json_mode,
        )

    dir_expr = config.terminal_mql5_dir(tid, target)
    script = (
        f"$d = {dir_expr}; "
        "if (-not (Test-Path $d)) { return }; "
        f"Get-ChildItem -Path $d -Filter *.{ext} -Recurse | "
        "ForEach-Object { "
        "Write-Output (\"$($_.FullName)`t$($_.Length)`t$($_.LastWriteTime.ToString('o'))\") }"
    )
    try:
        out = ssh.ssh_powershell(script)
    except ssh.SshError as e:
        emit_error(code="ssh_failed", message=str(e), json_mode=json_mode)

    entries = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        entries.append(
            {
                "path": parts[0].replace("\\", "/"),
                "size_bytes": int(parts[1]),
                "mtime": parts[2],
            }
        )
    emit_ok(
        {
            "target": target,
            "extension": ext,
            "terminal_id": tid,
            "count": len(entries),
            "files": entries,
        },
        json_mode=json_mode,
    )
