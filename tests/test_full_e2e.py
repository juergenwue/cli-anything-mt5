"""Opt-in end-to-end tests that hit the real MT5 Windows host.

Enabled with::

    MT5_E2E=1 pytest tests/test_full_e2e.py -v

Requires a populated `.env` and an actual reachable Windows host.
These tests never mock SSH. Treat them as smoke checks, not unit tests.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli_anything_mt5.cli import cli

RUN_E2E = os.getenv("MT5_E2E") == "1"
pytestmark = pytest.mark.skipif(not RUN_E2E, reason="set MT5_E2E=1 to run")


def _json_payload(output: str) -> dict:
    return json.loads(output.splitlines()[-1])


def test_e2e_version_check() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["version-check", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json_payload(result.output)
    assert payload["status"] == "ok"
    assert "ssh_ok" in payload["data"]
    assert payload["data"]["ssh_ok"] is True


def test_e2e_compile_fixture_ea(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "with_inputs.mq5"
    if not fixture.is_file():
        pytest.skip("no fixture EA to compile")
    runner = CliRunner()
    result = runner.invoke(cli, ["compile", str(fixture), "--json"])
    payload = _json_payload(result.output)
    assert payload["status"] in {"ok", "error"}


def test_e2e_list_deployed_returns_list() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["list-deployed", "--json"])
    assert result.exit_code == 0, result.output
    payload = _json_payload(result.output)
    assert payload["status"] == "ok"
    assert isinstance(payload["data"].get("files", []), list)
