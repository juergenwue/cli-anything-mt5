"""`climt5 version-check` - VM reachability + Terminal ID discovery (multi-target)."""

from __future__ import annotations

from typing import Any

import click

from cli_anything_core.ssh import SshError
from cli_anything_core.ssh_powershell import ssh_ok_powershell, ssh_powershell
from cli_anything_core.targets import Target

from .. import config
from ..multi import dispatch, resolve_targets


def _discover_terminal_ids(client) -> list[dict[str, str]]:
    # Note: keep ForEach-Object on a single line — PowerShell's `-Command -`
    # stdin reader trips over scriptblocks split across lines.
    script = (
        '$root = Join-Path $env:APPDATA "MetaQuotes\\Terminal"; '
        "if (-not (Test-Path $root)) { return }; "
        "Get-ChildItem $root -Directory | ForEach-Object "
        "{ Write-Output (\"$($_.Name)`t$($_.LastWriteTime.ToString('o'))\") }"
    )
    out = ssh_powershell(client, script)
    ids: list[dict[str, str]] = []
    for line in out.splitlines():
        if "\t" not in line:
            continue
        tid, mtime = line.split("\t", 1)
        if len(tid) >= 16:
            ids.append({"id": tid, "mtime": mtime})
    ids.sort(key=lambda r: r["mtime"], reverse=True)
    return ids


def _mt5_build_windows(client, t: Target) -> str | None:
    """Probe terminal64.exe ProductVersion at the per-target install root.

    Resolution order: binding.install_root (TOML) > config.MT5_ROOT (env/.env).
    """
    binding = t.binding("mt5")
    install_root = (
        getattr(binding, "install_root", None)
        or binding.model_extra.get("install_root") if binding.model_extra else None
    ) or config.MT5_ROOT
    try:
        script = (
            f'$exe = Join-Path "{install_root}" "terminal64.exe"; '
            "if (Test-Path $exe) { (Get-Item $exe).VersionInfo.ProductVersion } "
            "else { Write-Output 'missing' }"
        )
        out = ssh_powershell(client, script)
    except SshError:
        return None
    return out if out and out != "missing" else None


def _windows_runner(client, t: Target) -> dict[str, Any]:
    data: dict[str, Any] = {
        "user": t.user,
        "tcp_reachable": client.ping(),
    }
    if not data["tcp_reachable"]:
        raise SshError(f"Cannot reach {t.host}:{t.port} over TCP.")

    data["ssh_ok"] = ssh_ok_powershell(client)
    if not data["ssh_ok"]:
        raise SshError("PowerShell smoke test failed.")

    try:
        data["terminal_ids"] = _discover_terminal_ids(client)
    except SshError as e:
        data["terminal_ids"] = []
        data["terminal_ids_error"] = str(e)

    binding = t.binding("mt5")
    configured = binding.terminal_id or None
    if configured is None and data["terminal_ids"]:
        configured = data["terminal_ids"][0]["id"]
    data["active_terminal_id"] = configured

    try:
        data["mt5_build"] = _mt5_build_windows(client, t)
    except SshError as e:
        data["mt5_build"] = None
        data["mt5_build_error"] = str(e)

    return data


def _posix_runner(client, t: Target) -> dict[str, Any]:
    data: dict[str, Any] = {
        "user": t.user,
        "tcp_reachable": client.ping(),
    }
    if not data["tcp_reachable"]:
        raise SshError(f"Cannot reach {t.host}:{t.port} over TCP.")

    data["ssh_ok"] = client.ok()
    if not data["ssh_ok"]:
        raise SshError("SSH smoke test failed.")

    binding = t.binding("mt5")
    base = binding.base or ""
    if base:
        # Strip {subdir} / {terminal_id} for a parent-root probe.
        rendered = base.replace("{subdir}", "Experts").replace(
            "{terminal_id}", binding.terminal_id or ""
        )
        try:
            out = client.ssh_cmd(
                f"if [ -d {rendered!r} ]; then echo present; else echo missing; fi"
            )
            data["mt5_root_status"] = out.strip()
        except SshError as e:
            data["mt5_root_status"] = f"error: {e}"
    return data


@click.command(
    "version-check",
    help="Verify VM reachability, terminal build, Terminal ID across one or more targets.",
)
@click.option(
    "--target",
    "target_pattern",
    default=None,
    help="Target selector: name, glob, comma list, @group, or 'all'.",
)
@click.option("--sequential", is_flag=True, default=False)
@click.option("--json", "json_mode", is_flag=True, help="Machine-readable output.")
def version_check(
    target_pattern: str | None,
    sequential: bool,
    json_mode: bool,
) -> None:
    targets = resolve_targets(target_pattern, platform="mt5", json_mode=json_mode)

    def _runner(client, t: Target) -> dict[str, Any]:
        if t.os == "windows":
            return _windows_runner(client, t)
        return _posix_runner(client, t)

    dispatch(targets, _runner, sequential=sequential, json_mode=json_mode)
