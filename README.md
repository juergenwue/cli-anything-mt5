# cli-anything-mt5

Agent-friendly CLI harness for MetaTrader 5: compile, deploy, backtest, and
parse reports on a remote Windows host via SSH.

Part of the [CLI-Anything](https://github.com/HKUDS/CLI-Anything) ecosystem.

## Install

```bash
pip install cli-anything-mt5
```

## Prerequisites

- Windows host running MetaTrader 5 + MetaEditor64, reachable via SSH
- Environment: `MT5_HOST`, `MT5_USER`, `MT5_ROOT`, `MT5_TERMINAL_ID`
  (copy `.env.example` as a starting point)

## Commands

| Command | Purpose |
|---|---|
| `climt5 version-check` | Probe VM, discover Terminal ID, read MT5 build. |
| `climt5 compile <file.mq5>` | Compile via MetaEditor64 on the VM (with `--autofix`). |
| `climt5 deploy <file>` | Upload `.mq5`/`.ex5` with post-SCP mtime verify. |
| `climt5 list-deployed` | Enumerate compiled artefacts on the VM. |
| `climt5 parse-report <file>` | Normalize Strategy Tester HTML/XML metrics. |
| `climt5 extract-params <file.mq5>` | Extract `input`/`sinput`/`extern` variables as JSON. |
| `climt5 resolve-includes <file.mq5>` | Build the transitive `#include` graph. |
| `climt5 generate-set <file.mq5> --params …` | Write a UTF-16 LE `.set` file. |
| `climt5 backtest <EA> --symbol … --tf …` | Render tester.ini, run, parse report. |
| `climt5 optimize <EA> --ranges r.json --mode …` | Grid/fast/genetic optimization. |

All commands accept `--json` for machine-readable output following the
envelope `{"status":"ok"|"error", …}`.

## Testing

```bash
pip install -e ".[dev]"
pytest tests/test_core.py -v           # 28 mocked-SSH tests, no VM required
MT5_E2E=1 pytest tests/test_full_e2e.py # opt-in against a real VM
```

## Agent integration

See [`SKILL.md`](./SKILL.md) for the agent-facing contract: triggers,
decision tree, known failure modes (MetaEditor silent-fail, umlaut paths,
UTF-16 LE BOM handling), and the stable error-code taxonomy.
