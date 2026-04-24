"""Test fixtures for cli-anything-mt5.

The `fake_ssh` fixture patches the SSH/SCP layer with a programmable stub
that maps command-substring patterns to canned responses. Use it to assert
that commands behave correctly without a real Windows VM.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest


class FakeSsh:
    """Programmable stub for the SSH layer.

    Usage in a test::

        fake_ssh.on(r"Get-Process", "stopped")
        fake_ssh.on(r"Write-Output 'OK'", "OK")
    """

    def __init__(self) -> None:
        self._rules: list[tuple[re.Pattern[str], str | Callable[[str], str]]] = []
        self.calls: list[str] = []
        self.scp_calls: list[tuple[str, str]] = []

    def on(
        self,
        pattern: str,
        response: str | Callable[[str], str],
    ) -> None:
        self._rules.append((re.compile(pattern), response))

    def ssh_cmd(self, cmd: str, timeout: int | None = None) -> str:
        return self._dispatch(cmd)

    def ssh_powershell(self, script: str, timeout: int | None = None) -> str:
        return self._dispatch(script)

    def scp_to_vm(self, local: str, remote_expr: str) -> str:
        self.scp_calls.append((str(local), remote_expr))
        return self._dispatch(f"scp:{remote_expr}")

    def scp_from_vm(self, remote_expr: str, local: str) -> str:
        self.scp_calls.append((remote_expr, str(local)))
        return self._dispatch(f"scp:{remote_expr}")

    def resolve_powershell_path(self, expr: str) -> str:
        return self._dispatch(expr)

    def ping_vm(self, port: int = 22, timeout: float = 3.0) -> bool:
        return True

    def ssh_ok(self) -> bool:
        return True

    def _dispatch(self, key: str) -> str:
        self.calls.append(key)
        for pattern, response in self._rules:
            if pattern.search(key):
                return response(key) if callable(response) else response
        raise AssertionError(
            f"No fake_ssh rule matched: {key!r}\n"
            f"Rules registered: {[p.pattern for p, _ in self._rules]}"
        )


@pytest.fixture
def fake_ssh(monkeypatch: pytest.MonkeyPatch) -> FakeSsh:
    """Patch the `ssh` module with a FakeSsh instance."""
    fake = FakeSsh()
    import cli_anything_mt5.ssh as ssh_mod

    monkeypatch.setattr(ssh_mod, "ssh_cmd", fake.ssh_cmd)
    monkeypatch.setattr(ssh_mod, "ssh_powershell", fake.ssh_powershell)
    monkeypatch.setattr(ssh_mod, "scp_to_vm", fake.scp_to_vm)
    monkeypatch.setattr(ssh_mod, "scp_from_vm", fake.scp_from_vm)
    monkeypatch.setattr(ssh_mod, "resolve_powershell_path", fake.resolve_powershell_path)
    monkeypatch.setattr(ssh_mod, "ping_vm", fake.ping_vm)
    monkeypatch.setattr(ssh_mod, "ssh_ok", fake.ssh_ok)
    return fake
