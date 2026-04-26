"""`climt5 list-deployed` — enumerate MQL5 artefacts on one or more targets."""

from __future__ import annotations

from typing import Any

import click

from cli_anything_core.ssh_powershell import ssh_powershell
from cli_anything_core.targets import Target

from .. import config
from ..multi import dispatch, resolve_targets
from ..ssh import SshError

SUBDIR_CHOICES = ("Experts", "Indicators", "Scripts", "Include")


def _list_windows(client, t: Target, subdir: str, ext: str, terminal_id: str | None) -> dict[str, Any]:
    binding = t.binding("mt5")
    if terminal_id is not None:
        object.__setattr__(binding, "terminal_id", terminal_id)
    tid = binding.terminal_id
    if not tid:
        raise SshError(f"target {t.name!r} has no terminal_id")
    tf = config.targets()
    subdirs = tf.platform_subdirs("mt5")
    subdir_kind = {"Experts": "ea", "Indicators": "indicator",
                   "Scripts": "script", "Include": "include"}[subdir]
    dir_expr = t.remote_dir("mt5", subdir_kind, subdirs)
    script = (
        f"$d = {dir_expr}; "
        "if (-not (Test-Path $d)) { return }; "
        f"Get-ChildItem -Path $d -Filter *.{ext} -Recurse | "
        "ForEach-Object { "
        "Write-Output (\"$($_.FullName)`t$($_.Length)`t$($_.LastWriteTime.ToString('o'))\") }"
    )
    out = ssh_powershell(client, script)
    files = _parse_listing(out)
    return {"subdir": subdir, "extension": ext, "terminal_id": tid,
            "count": len(files), "files": files}


def _list_posix(client, t: Target, subdir: str, ext: str) -> dict[str, Any]:
    tf = config.targets()
    subdirs = tf.platform_subdirs("mt5")
    subdir_kind = {"Experts": "ea", "Indicators": "indicator",
                   "Scripts": "script", "Include": "include"}[subdir]
    dir_path = t.remote_dir("mt5", subdir_kind, subdirs)
    cmd = (
        f"if [ -d {dir_path!r} ]; then "
        f"find {dir_path!r} -name '*.{ext}' "
        "-printf '%p\\t%s\\t%TY-%Tm-%TdT%TH:%TM:%TS\\n'; fi"
    )
    out = client.ssh_cmd(cmd)
    files = _parse_listing(out)
    return {"subdir": subdir, "extension": ext,
            "count": len(files), "files": files}


def _parse_listing(out: str) -> list[dict[str, Any]]:
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
    return entries


@click.command("list-deployed", help="List .ex5/.mq5/.mqh files on one or more targets.")
@click.option(
    "--target",
    "target_pattern",
    default=None,
    help="Target selector: name, glob, comma list, @group, or 'all'.",
)
@click.option(
    "--subdir",
    type=click.Choice(SUBDIR_CHOICES),
    default="Experts",
    show_default=True,
)
@click.option(
    "--ext",
    type=click.Choice(["ex5", "mq5", "mqh"]),
    default="ex5",
    show_default=True,
)
@click.option("--terminal-id", default=None, help="Override Windows terminal_id.")
@click.option("--sequential", is_flag=True, default=False)
@click.option("--json", "json_mode", is_flag=True)
def list_deployed(
    target_pattern: str | None,
    subdir: str,
    ext: str,
    terminal_id: str | None,
    sequential: bool,
    json_mode: bool,
) -> None:
    targets = resolve_targets(target_pattern, platform="mt5", json_mode=json_mode)

    def _runner(client, t: Target) -> dict[str, Any]:
        if t.os == "windows":
            return _list_windows(client, t, subdir, ext, terminal_id)
        return _list_posix(client, t, subdir, ext)

    dispatch(targets, _runner, sequential=sequential, json_mode=json_mode)
