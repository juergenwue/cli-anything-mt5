"""`climt5 deploy` — upload an .mq5/.mqh/.ex5 to one or more targets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from cli_anything_core.ssh_powershell import (
    resolve_powershell_path,
    scp_to_powershell,
    ssh_powershell,
)
from cli_anything_core.targets import Target

from .. import config
from ..multi import dispatch, resolve_targets
from ..output import emit_error
from ..ssh import SshError

SUBDIR_CHOICES = ("Experts", "Indicators", "Scripts", "Include")


def _stat_remote_windows(client, remote_path_expr: str) -> dict | None:
    script = (
        f"$p = {remote_path_expr}; "
        "if (Test-Path $p) { "
        "$i = Get-Item $p; "
        "Write-Output (\"$($i.Length)`t$($i.LastWriteTime.ToString('o'))\") "
        "} else { Write-Output 'MISSING' }"
    )
    try:
        out = ssh_powershell(client, script)
    except SshError:
        return None
    if out.strip() == "MISSING" or "\t" not in out:
        return None
    size, mtime = out.split("\t", 1)
    return {"size_bytes": int(size), "mtime": mtime}


def _stat_remote_posix(client, remote_path: str) -> dict | None:
    try:
        out = client.ssh_cmd(f"stat -c '%s\t%Y' {remote_path!r} 2>/dev/null || echo MISSING")
    except SshError:
        return None
    if out.strip() == "MISSING" or "\t" not in out:
        return None
    size, mtime = out.split("\t", 1)
    return {"size_bytes": int(size), "mtime": mtime}


def _infer_subdir(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".mqh"):
        return "Include"
    return "Experts"


@click.command("deploy", help="Deploy an MQL5 source or compiled .ex5 to one or more targets.")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--target",
    "target_pattern",
    default=None,
    help="Target selector: name (windowsvm), glob (sqx1.*), comma list, @group, or 'all'.",
)
@click.option(
    "--subdir",
    type=click.Choice(SUBDIR_CHOICES),
    default=None,
    help="MQL5 subdirectory (default: inferred from filename).",
)
@click.option(
    "--terminal-id",
    default=None,
    help="Override Windows MT5 terminal_id (Windows targets only).",
)
@click.option("--verify/--no-verify", default=True, help="Verify mtime/size after upload.")
@click.option("--sequential", is_flag=True, default=False, help="Run targets sequentially.")
@click.option("--json", "json_mode", is_flag=True)
def deploy_cmd(
    source: Path,
    target_pattern: str | None,
    subdir: str | None,
    terminal_id: str | None,
    verify: bool,
    sequential: bool,
    json_mode: bool,
) -> None:
    targets = resolve_targets(target_pattern, platform="mt5", json_mode=json_mode)
    sub = subdir or _infer_subdir(source.name)
    subdir_kind = {"Experts": "ea", "Indicators": "indicator",
                   "Scripts": "script", "Include": "include"}[sub]
    tf = config.targets()
    platform_subdirs = tf.platform_subdirs("mt5")
    local_size = source.stat().st_size

    def _runner(client, t: Target) -> dict[str, Any]:
        binding = t.binding("mt5")
        # Windows: terminal_id override per CLI flag, else from binding
        if terminal_id is not None and t.os == "windows":
            object.__setattr__(binding, "terminal_id", terminal_id)
        remote_dir_repr = t.remote_dir("mt5", subdir_kind, platform_subdirs)
        entry: dict[str, Any] = {
            "source": str(source),
            "subdir": sub,
            "verified": False,
        }
        if t.os == "windows":
            scp_to_powershell(client, source, remote_dir_repr)
            resolved_dir = resolve_powershell_path(client, remote_dir_repr)
            entry["remote_dir"] = resolved_dir
            entry["terminal_id"] = binding.terminal_id
            if verify:
                file_expr = (
                    f'(Join-Path "{resolved_dir}" "{source.name}")'
                )
                stat = _stat_remote_windows(client, file_expr)
                if stat is None:
                    raise SshError("verify_failed: file not found after SCP")
                entry["remote_stat"] = stat
                entry["local_size_bytes"] = local_size
                if stat["size_bytes"] != local_size:
                    raise SshError(
                        f"size_mismatch: local {local_size} vs remote {stat['size_bytes']}"
                    )
                entry["verified"] = True
        else:
            remote_path = f"{remote_dir_repr.rstrip('/')}/{source.name}"
            client.ssh_cmd(f"mkdir -p {remote_dir_repr!r}")
            client.scp_to(source, remote_path)
            entry["remote_dir"] = remote_dir_repr
            if verify:
                stat = _stat_remote_posix(client, remote_path)
                if stat is None:
                    raise SshError("verify_failed: file not found after SCP")
                entry["remote_stat"] = stat
                entry["local_size_bytes"] = local_size
                if stat["size_bytes"] != local_size:
                    raise SshError(
                        f"size_mismatch: local {local_size} vs remote {stat['size_bytes']}"
                    )
                entry["verified"] = True
        return entry

    # Pre-flight: Windows targets need a terminal_id
    for t in targets:
        if t.os == "windows" and "mt5" in t.platforms:
            tid = (terminal_id
                   if terminal_id is not None
                   else t.binding("mt5").terminal_id)
            if not tid:
                emit_error(
                    code="terminal_id_missing",
                    message=f"Windows target {t.name!r} has no terminal_id (set in targets.toml or pass --terminal-id).",
                    json_mode=json_mode,
                )

    dispatch(targets, _runner, sequential=sequential, json_mode=json_mode)
