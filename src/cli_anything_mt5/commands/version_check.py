"""`climt5 version-check` - verify VM reachability and discover Terminal ID."""

from __future__ import annotations

import click

from .. import config, ssh
from ..output import emit_error, emit_ok


def _discover_terminal_ids() -> list[dict[str, str]]:
    """Scan MetaQuotes\\Terminal\\* for terminal instances; report mtimes.

    Returns a list of {"id": <hex>, "mtime": <iso>} sorted by mtime desc.
    """
    script = """
$root = Join-Path $env:APPDATA 'MetaQuotes\\Terminal'
if (-not (Test-Path $root)) { return }
Get-ChildItem $root -Directory | ForEach-Object {
    $origin = Join-Path $_.FullName 'origin.txt'
    $mtime = $_.LastWriteTime.ToString('o')
    Write-Output ("{0}`t{1}" -f $_.Name, $mtime)
}
""".strip()
    out = ssh.ssh_powershell(script)
    ids: list[dict[str, str]] = []
    for line in out.splitlines():
        if "\t" not in line:
            continue
        tid, mtime = line.split("\t", 1)
        if len(tid) >= 16:  # rough sanity check for hash-style IDs
            ids.append({"id": tid, "mtime": mtime})
    ids.sort(key=lambda r: r["mtime"], reverse=True)
    return ids


def _mt5_build() -> str | None:
    """Return the installed MT5 build number by inspecting terminal64.exe."""
    script = (
        f'$exe = Join-Path "{config.MT5_ROOT}" "terminal64.exe"; '
        'if (Test-Path $exe) { '
        '(Get-Item $exe).VersionInfo.ProductVersion '
        '} else { Write-Output "missing" }'
    )
    try:
        out = ssh.ssh_powershell(script)
    except ssh.SshError:
        return None
    return out if out and out != "missing" else None


@click.command(help="Verify MT5 VM reachability, terminal build, Terminal ID.")
@click.option("--json", "json_mode", is_flag=True, help="Machine-readable output.")
def version_check(json_mode: bool) -> None:
    data: dict = {
        "host": config.MT5_HOST,
        "user": config.MT5_USER,
        "tcp_reachable": ssh.ping_vm(),
    }
    if not data["tcp_reachable"]:
        emit_error(
            code="vm_unreachable",
            message=f"Cannot reach {config.MT5_HOST}:22 over TCP.",
            json_mode=json_mode,
            details=data,
        )

    try:
        data["ssh_ok"] = ssh.ssh_ok()
    except ssh.SshError as e:
        emit_error(
            code="ssh_failed",
            message=str(e),
            json_mode=json_mode,
            details=data,
        )
    if not data["ssh_ok"]:
        emit_error(
            code="ssh_failed",
            message="PowerShell smoke test failed.",
            json_mode=json_mode,
            details=data,
        )

    try:
        data["terminal_ids"] = _discover_terminal_ids()
    except ssh.SshError as e:
        data["terminal_ids"] = []
        data["terminal_ids_error"] = str(e)

    configured = config.MT5_TERMINAL_ID or None
    if configured is None and data["terminal_ids"]:
        configured = data["terminal_ids"][0]["id"]
    data["active_terminal_id"] = configured

    try:
        data["mt5_build"] = _mt5_build()
    except ssh.SshError as e:
        data["mt5_build"] = None
        data["mt5_build_error"] = str(e)

    emit_ok(data, json_mode=json_mode)
