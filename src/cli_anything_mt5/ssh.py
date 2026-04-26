"""SSH/SCP layer for the Windows MT5 host (built on cli-anything-core).

Single-target legacy API (module-level functions) is preserved so existing
commands and the FakeSsh test fixture keep working. Multi-target callers use
``make_client(target)`` and call methods on the resulting client directly.

All Windows paths are resolved server-side through PowerShell using
``$env:APPDATA`` / ``$env:LOCALAPPDATA`` to avoid locale and umlaut issues.
"""

from __future__ import annotations

from pathlib import Path

from cli_anything_core.ssh import SshClient, SshError
from cli_anything_core.ssh_powershell import (
    resolve_powershell_path as _core_resolve,
)
from cli_anything_core.ssh_powershell import (
    scp_from_powershell as _core_scp_from,
)
from cli_anything_core.ssh_powershell import (
    scp_to_powershell as _core_scp_to,
)
from cli_anything_core.ssh_powershell import (
    ssh_ok_powershell as _core_ssh_ok,
)
from cli_anything_core.ssh_powershell import (
    ssh_powershell as _core_ssh_powershell,
)
from cli_anything_core.targets import Target

from . import config

__all__ = [
    "SshError",
    "SshClient",
    "default_client",
    "make_client",
    "ssh_cmd",
    "ssh_powershell",
    "resolve_powershell_path",
    "scp_to_vm",
    "scp_from_vm",
    "ping_vm",
    "ssh_ok",
]


# --- Client factories ---

_default: SshClient | None = None


def default_client() -> SshClient:
    """Build the legacy single-target client from .env config."""
    global _default
    if _default is None:
        _default = SshClient(
            user=config.MT5_USER,
            host=config.MT5_HOST,
            ssh_timeout=config.MT5_SSH_TIMEOUT,
            scp_timeout=config.MT5_SCP_TIMEOUT,
        )
    return _default


def make_client(target: Target) -> SshClient:
    """Build a SshClient for a resolved target from targets.toml."""
    return SshClient(
        user=target.user,
        host=target.host,
        port=target.port,
        ssh_timeout=config.MT5_SSH_TIMEOUT,
        scp_timeout=config.MT5_SCP_TIMEOUT,
    )


# --- Legacy module-level shims (FakeSsh-compatible) ---


def ssh_cmd(cmd: str, timeout: int | None = None) -> str:
    return default_client().ssh_cmd(cmd, timeout=timeout)


def ssh_powershell(script: str, timeout: int | None = None) -> str:
    return _core_ssh_powershell(default_client(), script, timeout=timeout)


def resolve_powershell_path(expr: str) -> str:
    return _core_resolve(default_client(), expr)


def scp_to_vm(local_path: str | Path, remote_powershell_expr: str) -> str:
    return _core_scp_to(default_client(), local_path, remote_powershell_expr)


def scp_from_vm(remote_powershell_expr: str, local_path: str | Path) -> str:
    return _core_scp_from(default_client(), remote_powershell_expr, local_path)


def ping_vm(port: int = 22, timeout: float = 3.0) -> bool:
    # Backwards-compat: legacy callers ignored client.port; honor explicit port.
    client = default_client()
    if port and port != client.port:
        client = SshClient(user=client.user, host=client.host, port=port)
    return client.ping(timeout=timeout)


def ssh_ok() -> bool:
    return _core_ssh_ok(default_client())
