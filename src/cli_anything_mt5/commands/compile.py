"""`climt5 compile` — compile an .mq5 file via MetaEditor64 on Windows targets.

MetaEditor sometimes returns exit 0 with a stale .ex5 on disk, so the command
*always* parses the produced log to confirm success.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import click

from cli_anything_core.ssh_powershell import (
    resolve_powershell_path,
    scp_from_powershell,
    scp_to_powershell,
)
from cli_anything_core.targets import Target

from .. import config
from ..multi import dispatch, resolve_targets
from ..output import emit_error
from ..parsers import compile_log
from ..ssh import SshError

SUBDIR_CHOICES = ("Experts", "Indicators", "Scripts", "Include")


def _guess_subdir(filename: str) -> str:
    if filename.endswith(".mqh"):
        return "Include"
    return "Experts"


@click.command("compile", help="Compile an MQL5 source on one or more Windows targets.")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--target",
    "target_pattern",
    default=None,
    help="Target selector: name, glob, comma list, @group, or 'all'.",
)
@click.option(
    "--subdir",
    type=click.Choice(SUBDIR_CHOICES),
    default=None,
    help="MQL5 subdirectory for upload (default: inferred).",
)
@click.option("--terminal-id", default=None, help="Override terminal_id (Windows targets).")
@click.option("--autofix", is_flag=True, help="Reserved (not implemented).")
@click.option("--max-iters", default=5, show_default=True, help="Reserved.")
@click.option("--sequential", is_flag=True, default=False, help="Run targets sequentially.")
@click.option("--json", "json_mode", is_flag=True)
def compile_cmd(
    source: Path,
    target_pattern: str | None,
    subdir: str | None,
    terminal_id: str | None,
    autofix: bool,  # noqa: ARG001
    max_iters: int,  # noqa: ARG001
    sequential: bool,
    json_mode: bool,
) -> None:
    targets = resolve_targets(target_pattern, platform="mt5", json_mode=json_mode)

    # Compile only makes sense on Windows targets (MetaEditor64).
    non_windows = [t.name for t in targets if t.os != "windows"]
    if non_windows:
        emit_error(
            code="compile_unsupported",
            message=f"compile is Windows-only; refusing for: {non_windows}",
            json_mode=json_mode,
        )

    sub = subdir or _guess_subdir(source.name)
    subdir_kind = {"Experts": "ea", "Indicators": "indicator",
                   "Scripts": "script", "Include": "include"}[sub]
    tf = config.targets()
    platform_subdirs = tf.platform_subdirs("mt5")

    def _runner(client, t: Target) -> dict[str, Any]:
        binding = t.binding("mt5")
        if terminal_id is not None:
            object.__setattr__(binding, "terminal_id", terminal_id)
        tid = binding.terminal_id
        if not tid:
            raise SshError(f"target {t.name!r} has no terminal_id (set in targets.toml or pass --terminal-id)")

        remote_dir_expr = t.remote_dir("mt5", subdir_kind, platform_subdirs)
        scp_to_powershell(client, source, remote_dir_expr)
        resolved_dir = resolve_powershell_path(client, remote_dir_expr)
        remote_mq5 = f"{resolved_dir}/{source.name}".replace("\\", "/")

        editor = f'"{config.MT5_ROOT}/metaeditor64.exe"'
        log_path = remote_mq5 + ".log"
        cmd = (
            f"cmd /c {editor} /compile:\"{remote_mq5}\" "
            f"/log:\"{log_path}\" /inc:\"{remote_mq5}\""
        )
        client.ssh_cmd(cmd, timeout=config.MT5_COMPILE_TIMEOUT)

        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as tmp:
            local_log = tmp.name
        try:
            scp_from_powershell(client, f'"{log_path}"', local_log)
            raw = Path(local_log).read_bytes()
        finally:
            Path(local_log).unlink(missing_ok=True)

        text = compile_log.decode_log_bytes(raw)
        log = compile_log.parse(text)

        entry = {
            "source": str(source),
            "subdir": sub,
            "terminal_id": tid,
            "remote_path": remote_mq5,
            **log.to_dict(),
        }
        if not log.success:
            raise SshError(
                f"compile_errors: {log.errors} error(s), {log.warnings} warning(s)"
            )
        return entry

    dispatch(targets, _runner, sequential=sequential, json_mode=json_mode)
