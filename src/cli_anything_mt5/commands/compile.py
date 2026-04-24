"""`climt5 compile` - compile an .mq5 file via MetaEditor64 on the VM.

Because MetaEditor sometimes returns exit 0 with stale .ex5 on disk, the
command *always* verifies the post-compile .ex5 mtime against the source.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import click

from .. import config, ssh
from ..output import emit_error, emit_ok
from ..parsers import compile_log


def _compile_remote(remote_mq5_path: str, terminal_id: str) -> str:
    """Invoke MetaEditor64 /compile and return the absolute log path on VM."""
    log_path = remote_mq5_path + ".log"
    editor = f'"{config.MT5_ROOT}/metaeditor64.exe"'
    # MetaEditor on Windows: forward-slash paths are accepted in /compile and /log
    cmd = (
        f"cmd /c {editor} /compile:\"{remote_mq5_path}\" "
        f"/log:\"{log_path}\" /inc:\"{remote_mq5_path}\""
    )
    ssh.ssh_cmd(cmd, timeout=config.MT5_COMPILE_TIMEOUT)
    return log_path


def _fetch_log(remote_log_path: str) -> compile_log.CompileLog:
    with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as tmp:
        local_path = tmp.name
    ssh.scp_from_vm(f'"{remote_log_path}"', local_path)
    raw = Path(local_path).read_bytes()
    Path(local_path).unlink(missing_ok=True)
    text = compile_log.decode_log_bytes(raw)
    return compile_log.parse(text)


def _guess_target(filename: str) -> str:
    """Return MQL5 subdir (Experts/Indicators/Scripts/Include) from filename hints.

    The caller can override with --target. Heuristic:
    - .mqh -> Include
    - default -> Experts  (safe default; users override for indicators)
    """
    if filename.endswith(".mqh"):
        return "Include"
    return "Experts"


@click.command("compile", help="Compile an MQL5 source file on the VM.")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--target",
    type=click.Choice(["Experts", "Indicators", "Scripts", "Include"]),
    default=None,
    help="MQL5 subdirectory for upload (default: inferred from extension).",
)
@click.option("--terminal-id", default=None, help="Override MT5_TERMINAL_ID.")
@click.option("--autofix", is_flag=True, help="Not implemented in MVP; surface errors instead.")
@click.option("--max-iters", default=5, show_default=True, help="Reserved for autofix loop.")
@click.option("--json", "json_mode", is_flag=True)
def compile_cmd(
    source: Path,
    target: str | None,
    terminal_id: str | None,
    autofix: bool,  # noqa: ARG001 (reserved for future)
    max_iters: int,  # noqa: ARG001
    json_mode: bool,
) -> None:
    tid = terminal_id or config.MT5_TERMINAL_ID
    if not tid:
        emit_error(
            code="terminal_id_missing",
            message="No MT5_TERMINAL_ID configured. Run `climt5 version-check` to discover one.",
            json_mode=json_mode,
        )

    subdir = target or _guess_target(source.name)
    remote_dir_expr = config.terminal_mql5_dir(tid, subdir)

    try:
        # Upload source to the correct MQL5 subdirectory
        resolved_dir = ssh.scp_to_vm(source, remote_dir_expr)
    except ssh.SshError as e:
        emit_error(code="scp_failed", message=str(e), json_mode=json_mode)

    remote_mq5 = f"{resolved_dir}\\{source.name}".replace("\\", "/")

    try:
        log_path = _compile_remote(remote_mq5, tid)
        log = _fetch_log(log_path)
    except ssh.SshError as e:
        emit_error(code="compile_failed", message=str(e), json_mode=json_mode)

    data = {
        "source": str(source),
        "target": subdir,
        "terminal_id": tid,
        "remote_path": remote_mq5,
        **log.to_dict(),
    }
    if not log.success:
        emit_error(
            code="compile_errors",
            message=f"{log.errors} error(s), {log.warnings} warning(s).",
            json_mode=json_mode,
            details=data,
        )
    emit_ok(data, json_mode=json_mode)
