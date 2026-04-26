"""Tests for multi-target deploy + bash-compat shim."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli_anything_mt5.cli import cli


@pytest.fixture
def sample_mq5(tmp_path: Path) -> Path:
    src = tmp_path / "EA-Sample.mq5"
    src.write_text("// stub MQL5 source\n")
    return src


def test_deploy_resolves_glob_to_multiple_targets(fake_ssh, sample_mq5: Path) -> None:
    """sqx1.* deploys to two Wine prefixes (no PowerShell, posix verify)."""
    fake_ssh.on(r"mkdir -p", "")
    fake_ssh.on(r"^stat -c", f"{sample_mq5.stat().st_size}\t2026-04-26T00:00:00")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["deploy", "--target", "sqx1.*", "--json", str(sample_mq5)]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.splitlines()[-1])
    assert payload["status"] == "ok"
    targets = payload["data"]["targets"]
    assert {t["target"] for t in targets} == {"sqx1.icmarkets", "sqx1.tickmill"}
    assert all(t["status"] == "ok" for t in targets)


def test_deploy_group_alias(fake_ssh, sample_mq5: Path) -> None:
    fake_ssh.on(r"mkdir -p", "")
    fake_ssh.on(r"^stat -c", f"{sample_mq5.stat().st_size}\t2026-04-26T00:00:00")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["deploy", "--target", "@sqx1", "--json", str(sample_mq5)]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.splitlines()[-1])
    assert {t["target"] for t in payload["data"]["targets"]} == {
        "sqx1.icmarkets",
        "sqx1.tickmill",
    }


def test_deploy_unknown_target_errors(fake_ssh, sample_mq5: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["deploy", "--target", "doesnotexist", "--json", str(sample_mq5)]
    )
    assert result.exit_code != 0
    payload = json.loads(result.output.splitlines()[-1])
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "target_not_found"


def test_deploy_windowsvm_uses_powershell_resolve(fake_ssh, sample_mq5: Path) -> None:
    """Windows path: PowerShell resolves base_expr; verify checks file size."""
    expected_size = sample_mq5.stat().st_size
    fake_ssh.on(r"Join-Path \$env:APPDATA", "C:/Users/Juergen/AppData/Roaming/MetaQuotes/Terminal/X/MQL5/Experts")
    fake_ssh.on(r"if \(Test-Path \$p\)", f"{expected_size}\t2026-04-26T00:00:00")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["deploy", "--target", "windowsvm", "--json", str(sample_mq5)]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.splitlines()[-1])
    entry = payload["data"]["targets"][0]
    assert entry["target"] == "windowsvm"
    assert entry["verified"] is True


def test_partial_failure_envelope(fake_ssh, sample_mq5: Path) -> None:
    """One target ok, one target SshError → status=error, partial_failure code."""
    seen_hosts: list[str] = []

    expected_size = sample_mq5.stat().st_size

    def _stat_response(_key):
        # First call wins ok, second call fails
        seen_hosts.append("x")
        if len(seen_hosts) == 1:
            return f"{expected_size}\t2026-04-26T00:00:00"
        return "MISSING"

    fake_ssh.on(r"mkdir -p", "")
    fake_ssh.on(r"^stat -c", _stat_response)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["deploy", "--target", "sqx1.*", "--sequential", "--json", str(sample_mq5)]
    )
    assert result.exit_code != 0, result.output
    payload = json.loads(result.output.splitlines()[-1])
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "partial_failure"


# --- bash-compat shim ---------------------------------------------------------


def test_bash_compat_translates_sqx_broker(fake_ssh, sample_mq5: Path) -> None:
    fake_ssh.on(r"mkdir -p", "")
    fake_ssh.on(r"^stat -c", f"{sample_mq5.stat().st_size}\t2026-04-26T00:00:00")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy-bash-compat",
            "--target=sqx",
            "--broker=ICMarkets",
            "--type=ea",
            "--json",
            str(sample_mq5),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.splitlines()[-1])
    targets = payload["data"]["targets"]
    assert {t["target"] for t in targets} == {"sqx1.icmarkets"}


def test_bash_compat_broker_all_glob(fake_ssh, sample_mq5: Path) -> None:
    fake_ssh.on(r"mkdir -p", "")
    fake_ssh.on(r"^stat -c", f"{sample_mq5.stat().st_size}\t2026-04-26T00:00:00")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy-bash-compat",
            "--target=sqx",
            "--broker=all",
            "--type=indicator",
            "--json",
            str(sample_mq5),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.splitlines()[-1])
    assert {t["target"] for t in payload["data"]["targets"]} == {
        "sqx1.icmarkets",
        "sqx1.tickmill",
    }


def test_bash_compat_dry_run(fake_ssh, sample_mq5: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy-bash-compat",
            "--target=sqx",
            "--broker=ICMarkets",
            "--dry-run",
            str(sample_mq5),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert "sqx1.icmarkets" in result.output
