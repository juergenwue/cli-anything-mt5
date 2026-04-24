"""SSH/SCP layer for the Windows MT5 host.

All Windows paths are resolved server-side through PowerShell using
`$env:APPDATA`/`$env:LOCALAPPDATA` to avoid locale and umlaut issues
(e.g. German Windows paths like C:\\Users\\Jürgen\\...).
"""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path

from . import config


class SshError(RuntimeError):
    """Raised when an SSH/SCP operation fails."""


def ssh_cmd(cmd: str, timeout: int | None = None) -> str:
    """Run a single command on the Windows host via SSH."""
    timeout = timeout or config.MT5_SSH_TIMEOUT
    try:
        result = subprocess.run(
            ["ssh", f"{config.MT5_USER}@{config.MT5_HOST}", cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise SshError(f"SSH timeout after {timeout}s: {cmd}") from e
    except OSError as e:
        raise SshError(f"SSH invocation failed: {e}") from e
    if result.returncode != 0:
        raise SshError(result.stderr.strip() or f"exit {result.returncode}")
    return result.stdout.strip()


def ssh_powershell(script: str, timeout: int | None = None) -> str:
    """Run a PowerShell script on the Windows host.

    The script is piped in via stdin to avoid quoting hazards.
    """
    timeout = timeout or config.MT5_SSH_TIMEOUT
    try:
        result = subprocess.run(
            [
                "ssh",
                f"{config.MT5_USER}@{config.MT5_HOST}",
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "-",
            ],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise SshError(f"PowerShell timeout after {timeout}s") from e
    except OSError as e:
        raise SshError(f"PowerShell invocation failed: {e}") from e
    if result.returncode != 0:
        raise SshError(result.stderr.strip() or f"exit {result.returncode}")
    return result.stdout.strip()


def resolve_powershell_path(expr: str) -> str:
    """Resolve a PowerShell path expression to a Windows absolute path."""
    return ssh_powershell(f"Write-Output ({expr})")


def scp_to_vm(local_path: str | Path, remote_powershell_expr: str) -> str:
    """Copy a file to the Windows host; remote is a PowerShell expression."""
    resolved = resolve_powershell_path(remote_powershell_expr)
    remote_path = resolved.replace("\\", "/")
    target = f"{config.MT5_USER}@{config.MT5_HOST}:{remote_path}"
    try:
        result = subprocess.run(
            ["scp", str(local_path), target],
            capture_output=True,
            text=True,
            timeout=config.MT5_SCP_TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        raise SshError(f"SCP timeout after {config.MT5_SCP_TIMEOUT}s") from e
    if result.returncode != 0:
        raise SshError(result.stderr.strip() or "scp failed")
    return resolved


def scp_from_vm(remote_powershell_expr: str, local_path: str | Path) -> str:
    """Copy a file from the Windows host to the local filesystem."""
    resolved = resolve_powershell_path(remote_powershell_expr)
    remote_path = resolved.replace("\\", "/")
    source = f"{config.MT5_USER}@{config.MT5_HOST}:{remote_path}"
    try:
        result = subprocess.run(
            ["scp", source, str(local_path)],
            capture_output=True,
            text=True,
            timeout=config.MT5_SCP_TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        raise SshError(f"SCP timeout after {config.MT5_SCP_TIMEOUT}s") from e
    if result.returncode != 0:
        raise SshError(result.stderr.strip() or "scp failed")
    return resolved


def ping_vm(port: int = 22, timeout: float = 3.0) -> bool:
    """TCP reachability check (ICMP often blocked on Windows firewalls)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((config.MT5_HOST, port)) == 0
    except OSError:
        return False


def ssh_ok() -> bool:
    """Lightweight end-to-end SSH/PowerShell smoke test."""
    try:
        return ssh_powershell("Write-Output 'OK'", timeout=10) == "OK"
    except SshError:
        return False
