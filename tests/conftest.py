"""Test fixtures for cli-anything-mt5.

Two layers:

- ``fake_ssh`` — replaces both the legacy module-level ssh shims (used by
  single-target commands like version-check) and the new core SshClient/
  ssh_powershell layer (used by multi-target commands like deploy/compile/
  list-deployed). One canonical FakeSshClient handles both.
- ``mock_targets`` — autouse: points CLI_ANYTHING_TARGETS at a small TOML
  fixture so multi-target commands can resolve ``windowsvm``/``sqx1.*``
  without touching the user's real config.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

SAMPLE_TARGETS_TOML = """
schema_version = 1

[platforms.mt5]
subdirs = { ea = "Experts", indicator = "Indicators", script = "Scripts", include = "Include" }

[platforms.atas]
subdirs = { indicator = "Indicators" }

[platforms.ctrader]
subdirs = { indicator = "Indicators", robot = "Robots" }

[targets.windowsvm]
host = "192.168.178.83"
user = "Juergen"
port = 22
os = "windows"
platforms = ["mt5", "atas", "ctrader"]

[targets.windowsvm.mt5]
terminal_id = "DEADBEEFDEADBEEFDEADBEEFDEADBEEF"
base_expr = '(Join-Path $env:APPDATA "MetaQuotes\\\\Terminal\\\\{terminal_id}\\\\MQL5\\\\{subdir}")'

[targets.windowsvm.atas]
base_expr = '(Join-Path $env:APPDATA "ATAS\\\\{subdir}")'

[targets.windowsvm.ctrader]
base = "C:/Users/Juergen/Documents/cAlgo/Sources/{subdir}"

[targets."sqx1.icmarkets"]
host = "192.168.178.78"
user = "juergen"
port = 22
os = "linux-wine"
platforms = ["mt5"]
group = "sqx1"

[targets."sqx1.icmarkets".mt5]
base = "/home/juergen/trading/wine/icmarkets/drive_c/MT5/MQL5/{subdir}"

[targets."sqx1.tickmill"]
host = "192.168.178.78"
user = "juergen"
port = 22
os = "linux-wine"
platforms = ["mt5"]
group = "sqx1"

[targets."sqx1.tickmill".mt5]
base = "/home/juergen/trading/wine/tickmill/drive_c/MT5/MQL5/{subdir}"
"""


class FakeSsh:
    """Programmable stub mirroring SshClient + ssh_powershell helpers."""

    def __init__(self) -> None:
        self._rules: list[tuple[re.Pattern[str], str | Callable[[str], str]]] = []
        self.calls: list[str] = []
        self.scp_calls: list[tuple[str, str]] = []
        # Default attributes a real SshClient exposes
        self.user = "fake"
        self.host = "fake.local"
        self.port = 22
        self.ssh_timeout = 30
        self.scp_timeout = 60

    def on(self, pattern: str, response: str | Callable[[str], str]) -> None:
        self._rules.append((re.compile(pattern), response))

    def _dispatch(self, key: str) -> str:
        self.calls.append(key)
        for pattern, response in self._rules:
            if pattern.search(key):
                return response(key) if callable(response) else response
        raise AssertionError(
            f"No fake_ssh rule matched: {key!r}\n"
            f"Rules registered: {[p.pattern for p, _ in self._rules]}"
        )

    # --- legacy mt5.ssh module-level surface ---

    def ssh_cmd(self, cmd: str, timeout: int | None = None) -> str:
        return self._dispatch(cmd)

    def ssh_powershell(self, script: str, timeout: int | None = None) -> str:
        return self._dispatch(script)

    def scp_to_vm(self, local: str, remote_expr: str) -> str:
        self.scp_calls.append((str(local), remote_expr))
        try:
            return self._dispatch(f"scp:{remote_expr}")
        except AssertionError:
            return self._dispatch(remote_expr)

    def scp_from_vm(self, remote_expr: str, local: str) -> str:
        self.scp_calls.append((remote_expr, str(local)))
        try:
            return self._dispatch(f"scp:{remote_expr}")
        except AssertionError:
            return self._dispatch(remote_expr)

    def resolve_powershell_path(self, expr: str) -> str:
        return self._dispatch(expr)

    def ping_vm(self, port: int = 22, timeout: float = 3.0) -> bool:
        return True

    def ssh_ok(self) -> bool:
        return True

    # --- core SshClient surface ---

    def scp_to(self, local_path, remote_path: str) -> None:
        self.scp_calls.append((str(local_path), remote_path))

    def scp_from(self, remote_path: str, local_path) -> None:
        self.scp_calls.append((remote_path, str(local_path)))

    def ping(self, timeout: float = 3.0) -> bool:
        return True

    def ok(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def mock_targets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point CLI_ANYTHING_TARGETS at a temp file; reset config cache."""
    p = tmp_path / "targets.toml"
    p.write_text(SAMPLE_TARGETS_TOML)
    monkeypatch.setenv("CLI_ANYTHING_TARGETS", str(p))

    # Reset cached targets in mt5 config
    from cli_anything_mt5 import config as mt5_config

    monkeypatch.setattr(mt5_config, "_targets_cache", None)
    return p


@pytest.fixture
def fake_ssh(monkeypatch: pytest.MonkeyPatch) -> FakeSsh:
    """Patch every SSH/SCP/PowerShell entry point with a single FakeSsh."""
    fake = FakeSsh()

    # Reset legacy default client
    import cli_anything_mt5.ssh as ssh_mod

    monkeypatch.setattr(ssh_mod, "_default", None)

    # Legacy module-level shims (single-target commands)
    monkeypatch.setattr(ssh_mod, "ssh_cmd", fake.ssh_cmd)
    monkeypatch.setattr(ssh_mod, "ssh_powershell", fake.ssh_powershell)
    monkeypatch.setattr(ssh_mod, "scp_to_vm", fake.scp_to_vm)
    monkeypatch.setattr(ssh_mod, "scp_from_vm", fake.scp_from_vm)
    monkeypatch.setattr(ssh_mod, "resolve_powershell_path", fake.resolve_powershell_path)
    monkeypatch.setattr(ssh_mod, "ping_vm", fake.ping_vm)
    monkeypatch.setattr(ssh_mod, "ssh_ok", fake.ssh_ok)
    monkeypatch.setattr(ssh_mod, "default_client", lambda: fake)
    monkeypatch.setattr(ssh_mod, "make_client", lambda t: fake)

    # New multi-target commands import these directly from core or
    # bind them at module-import time, so patch every known import site.
    from cli_anything_core import ssh_powershell as core_ps

    def _ssh_powershell(client, script, timeout=None):  # noqa: ANN001
        return fake._dispatch(script)

    def _resolve(client, expr):  # noqa: ANN001
        return fake._dispatch(expr)

    def _scp_to(client, local, remote_expr):  # noqa: ANN001
        fake.scp_calls.append((str(local), remote_expr))
        try:
            return fake._dispatch(f"scp:{remote_expr}")
        except AssertionError:
            return remote_expr

    def _scp_from(client, remote_expr, local):  # noqa: ANN001
        fake.scp_calls.append((remote_expr, str(local)))
        try:
            return fake._dispatch(f"scp:{remote_expr}")
        except AssertionError:
            return remote_expr

    monkeypatch.setattr(core_ps, "ssh_powershell", _ssh_powershell)
    monkeypatch.setattr(core_ps, "resolve_powershell_path", _resolve)
    monkeypatch.setattr(core_ps, "scp_to_powershell", _scp_to)
    monkeypatch.setattr(core_ps, "scp_from_powershell", _scp_from)

    # Patch the from-imports inside command modules too.
    for mod_name in (
        "cli_anything_mt5.commands.deploy",
        "cli_anything_mt5.commands.compile",
        "cli_anything_mt5.commands.list_deployed",
    ):
        import importlib

        mod = importlib.import_module(mod_name)
        if hasattr(mod, "ssh_powershell"):
            monkeypatch.setattr(mod, "ssh_powershell", _ssh_powershell)
        if hasattr(mod, "resolve_powershell_path"):
            monkeypatch.setattr(mod, "resolve_powershell_path", _resolve)
        if hasattr(mod, "scp_to_powershell"):
            monkeypatch.setattr(mod, "scp_to_powershell", _scp_to)
        if hasattr(mod, "scp_from_powershell"):
            monkeypatch.setattr(mod, "scp_from_powershell", _scp_from)

    return fake
