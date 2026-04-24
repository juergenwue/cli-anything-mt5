"""Core test suite for cli-anything-mt5.

These tests do NOT touch a real VM. They exercise:
- Click argparse surface (--help, --json, missing args)
- Parser units (compile log, tester report)
- The envelope contract (`ok` / `error` shape)

E2E tests against the real VM live in `test_full_e2e.py` and are opt-in
via the `MT5_E2E=1` environment variable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli_anything_mt5 import config as mt5_config
from cli_anything_mt5.cli import cli
from cli_anything_mt5.output import Envelope
from cli_anything_mt5.parsers import compile_log, mql5_source, tester_report


FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Click argparse surface
# ---------------------------------------------------------------------------

def test_help_lists_all_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("version-check", "compile", "deploy", "list-deployed", "parse-report"):
        assert cmd in result.output


@pytest.mark.parametrize(
    "cmd",
    [
        ["version-check", "--help"],
        ["compile", "--help"],
        ["deploy", "--help"],
        ["list-deployed", "--help"],
        ["parse-report", "--help"],
    ],
)
def test_subcommand_help(cmd: list[str]) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, cmd)
    assert result.exit_code == 0


def test_compile_missing_source_errors() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["compile"])
    assert result.exit_code != 0


def test_deploy_missing_source_errors() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["deploy"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Parser: compile log
# ---------------------------------------------------------------------------

def test_compile_log_decode_utf16_bom() -> None:
    text = "Result: 0 errors, 0 warnings.\n"
    raw = b"\xff\xfe" + text.encode("utf-16-le")
    assert compile_log.decode_log_bytes(raw).startswith("Result: 0 errors")


def test_compile_log_ok_has_zero_errors() -> None:
    text = (FIXTURES / "compile_log_ok.log").read_text(encoding="utf-8")
    log = compile_log.parse(text)
    assert log.success
    assert log.errors == 0
    assert log.warnings == 0


def test_compile_log_with_errors_parses_summary_and_diagnostics() -> None:
    text = (FIXTURES / "compile_log_errors.log").read_text(encoding="utf-8")
    log = compile_log.parse(text)
    assert not log.success
    assert log.errors == 2
    assert log.warnings == 1
    assert len(log.diagnostics) == 3
    errors = [d for d in log.diagnostics if d.severity == "error"]
    warnings = [d for d in log.diagnostics if d.severity == "warning"]
    assert len(errors) == 2
    assert len(warnings) == 1
    assert errors[0].line == 12 and errors[0].column == 5


def test_compile_log_fallback_without_summary() -> None:
    text = "foo.mq5(10,1) : error 1: broken\nfoo.mq5(11,1) : warning 1: dodgy\n"
    log = compile_log.parse(text)
    assert log.errors == 1
    assert log.warnings == 1


# ---------------------------------------------------------------------------
# Parser: tester report
# ---------------------------------------------------------------------------

def test_tester_report_parses_core_metrics() -> None:
    rpt = tester_report.parse_file(FIXTURES / "report_minimal.html")
    m = rpt.metrics
    assert m["symbol"] == "EURUSD"
    assert m["expert"] == "SampleEA"
    assert m["net_profit"] == pytest.approx(1234.56)
    assert m["profit_factor"] == pytest.approx(1.33)
    assert m["total_trades"] == 100


def test_tester_report_handles_utf16_bom(tmp_path: Path) -> None:
    html = (FIXTURES / "report_minimal.html").read_text(encoding="utf-8")
    utf16 = tmp_path / "report.html"
    utf16.write_bytes(b"\xff\xfe" + html.encode("utf-16-le"))
    rpt = tester_report.parse_file(utf16)
    assert rpt.metrics["symbol"] == "EURUSD"


# ---------------------------------------------------------------------------
# Envelope contract
# ---------------------------------------------------------------------------

def test_envelope_ok_validates() -> None:
    env = Envelope(status="ok", data={"foo": 1})
    payload = env.model_dump(exclude_none=True)
    assert payload == {"status": "ok", "data": {"foo": 1}}


def test_envelope_error_validates() -> None:
    env = Envelope.model_validate(
        {"status": "error", "error": {"code": "x", "message": "boom"}}
    )
    assert env.error is not None
    assert env.error.code == "x"


# ---------------------------------------------------------------------------
# parse-report command (pure; touches no SSH)
# ---------------------------------------------------------------------------

def test_parse_report_command_json_envelope() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["parse-report", str(FIXTURES / "report_minimal.html"), "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.splitlines()[-1])
    assert payload["status"] == "ok"
    metrics = payload["data"]["metrics"]
    assert metrics["symbol"] == "EURUSD"


def test_parse_report_command_metrics_filter() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "parse-report",
            str(FIXTURES / "report_minimal.html"),
            "--metrics",
            "symbol,net_profit",
            "--json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output.splitlines()[-1])
    keys = set(payload["data"]["metrics"].keys())
    assert keys == {"symbol", "net_profit"}


# ---------------------------------------------------------------------------
# list-deployed command with fake SSH
# ---------------------------------------------------------------------------

def test_list_deployed_parses_tab_separated_output(fake_ssh, monkeypatch) -> None:
    monkeypatch.setattr(mt5_config, "MT5_TERMINAL_ID", "DEADBEEF" * 4)
    fake_ssh.on(
        r"Get-ChildItem",
        "C:\\Users\\Juergen\\AppData\\Roaming\\MetaQuotes\\Terminal\\X\\MQL5\\Experts\\EA.ex5\t12345\t2026-04-01T12:00:00+00:00\n"
        "C:\\Users\\Juergen\\AppData\\Roaming\\MetaQuotes\\Terminal\\X\\MQL5\\Experts\\Other.ex5\t54321\t2026-04-02T08:30:00+00:00",
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["list-deployed", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.splitlines()[-1])
    assert payload["status"] == "ok"
    assert payload["data"]["count"] == 2
    files = payload["data"]["files"]
    assert files[0]["size_bytes"] == 12345
    assert "/" in files[0]["path"]  # backslashes normalized


def test_list_deployed_errors_without_terminal_id(fake_ssh, monkeypatch) -> None:
    monkeypatch.setattr(mt5_config, "MT5_TERMINAL_ID", "")
    runner = CliRunner()
    result = runner.invoke(cli, ["list-deployed", "--json"])
    assert result.exit_code != 0
    payload = json.loads(result.output.splitlines()[-1])
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "terminal_id_missing"


# ---------------------------------------------------------------------------
# version-check command with fake SSH
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Parser: mql5 source (inputs + includes)
# ---------------------------------------------------------------------------

def test_extract_inputs_covers_all_kinds() -> None:
    text = (FIXTURES / "with_inputs.mq5").read_text(encoding="utf-8")
    params = mql5_source.extract_inputs(text)
    by_name = {p.name: p for p in params}
    assert set(by_name) == {
        "MagicNumber", "LotSize", "CommentText", "UseFilter",
        "HiddenParam", "LegacyLot",
    }
    assert by_name["MagicNumber"].type == "int"
    assert by_name["MagicNumber"].default == "1234"
    assert by_name["MagicNumber"].label == "Magic number"
    assert by_name["HiddenParam"].kind == "sinput"
    assert by_name["LegacyLot"].kind == "extern"
    assert by_name["CommentText"].default.strip('"') == "hello"


def test_extract_includes_skips_commented() -> None:
    text = (FIXTURES / "with_inputs.mq5").read_text(encoding="utf-8")
    incs = mql5_source.extract_includes(text)
    paths = [i.path for i in incs]
    assert "Trade\\Trade.mqh" in paths
    assert "../shared/helpers.mqh" in paths
    assert "commented.mqh" not in paths
    systems = {i.path: i.system for i in incs}
    assert systems["Trade\\Trade.mqh"] is True
    assert systems["../shared/helpers.mqh"] is False


# ---------------------------------------------------------------------------
# extract-params command
# ---------------------------------------------------------------------------

def test_extract_params_command_json() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["extract-params", str(FIXTURES / "with_inputs.mq5"), "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.splitlines()[-1])
    assert payload["status"] == "ok"
    assert payload["data"]["count"] == 6


# ---------------------------------------------------------------------------
# generate-set command
# ---------------------------------------------------------------------------

def test_generate_set_writes_utf16_bom(tmp_path: Path) -> None:
    params_file = tmp_path / "p.json"
    params_file.write_text(
        json.dumps({"MagicNumber": 9999, "LotSize": 0.25, "UseFilter": False}),
        encoding="utf-8",
    )
    out = tmp_path / "out.set"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate-set",
            "--params", str(params_file),
            "--source", str(FIXTURES / "with_inputs.mq5"),
            "-o", str(out),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    raw = out.read_bytes()
    assert raw.startswith(b"\xff\xfe")
    text = raw[2:].decode("utf-16-le")
    assert "MagicNumber=9999" in text
    assert "UseFilter=false" in text


def test_generate_set_rejects_unknown_params(tmp_path: Path) -> None:
    params_file = tmp_path / "p.json"
    params_file.write_text(json.dumps({"DoesNotExist": 1}), encoding="utf-8")
    out = tmp_path / "out.set"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate-set",
            "--params", str(params_file),
            "--source", str(FIXTURES / "with_inputs.mq5"),
            "-o", str(out),
            "--json",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output.splitlines()[-1])
    assert payload["error"]["code"] == "unknown_params"


# ---------------------------------------------------------------------------
# resolve-includes command
# ---------------------------------------------------------------------------

def test_resolve_includes_finds_local_includes(tmp_path: Path) -> None:
    # Build a tiny include chain: root.mq5 -> a.mqh -> b.mqh
    (tmp_path / "b.mqh").write_text("// leaf\n", encoding="utf-8")
    (tmp_path / "a.mqh").write_text('#include "b.mqh"\n', encoding="utf-8")
    (tmp_path / "root.mq5").write_text('#include "a.mqh"\n', encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["resolve-includes", str(tmp_path / "root.mq5"), "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.splitlines()[-1])
    files = payload["data"]["files"]
    assert len(files) == 3
    assert payload["data"]["missing"] == []


def test_resolve_includes_reports_missing_system(tmp_path: Path) -> None:
    (tmp_path / "root.mq5").write_text("#include <MissingSystem.mqh>\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["resolve-includes", str(tmp_path / "root.mq5"), "--json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output.splitlines()[-1])
    assert len(payload["data"]["missing"]) == 1
    assert payload["data"]["missing"][0]["system"] is True


def test_version_check_reports_terminal_ids_and_build(fake_ssh) -> None:
    fake_ssh.on(r"Write-Output 'OK'", "OK")
    fake_ssh.on(
        r"MetaQuotes.Terminal",
        "DEADBEEFDEADBEEFDEADBEEFDEADBEEF\t2026-04-01T12:00:00+00:00\n"
        "COFFEECOFFEECOFFEECOFFEECOFFEECO\t2026-03-01T12:00:00+00:00",
    )
    fake_ssh.on(r"terminal64\.exe", "5.00.4000")

    runner = CliRunner()
    result = runner.invoke(cli, ["version-check", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.splitlines()[-1])
    assert payload["status"] == "ok"
    data = payload["data"]
    assert data["ssh_ok"] is True
    assert data["mt5_build"] == "5.00.4000"
    assert len(data["terminal_ids"]) == 2
    assert data["active_terminal_id"] == "DEADBEEFDEADBEEFDEADBEEFDEADBEEF"
