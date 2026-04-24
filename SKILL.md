---
name: cli-anything-mt5
description: Compile, deploy, backtest, and optimize MetaTrader 5 EAs and indicators over SSH from Linux.
triggers:
  - "backtest MT5 EA"
  - "compile .mq5"
  - "deploy MT5 indicator"
  - "optimize MT5 strategy"
  - "parse MT5 tester report"
entry_point: climt5
---

# cli-anything-mt5 — Agent Skill

`climt5` is a thin, deterministic CLI wrapper around the MT5 Windows
terminal. Every subcommand speaks `--json` and emits
`{"status":"ok"|"error", ...}` envelopes so agents can chain calls
without parsing human output.

## Preconditions

- Windows host with MetaTrader 5 installed and `MetaEditor64.exe` present.
- OpenSSH server on that host, reachable from the Linux dev machine.
- `.env` in CWD (or `$HOME/.cli-anything-mt5.env`) with:
  - `MT5_HOST`, `MT5_USER`
  - `MT5_ROOT` (the MT5 install dir)
  - `MT5_TERMINAL_ID` (32-char hash — use `climt5 version-check` to discover)

## Command surface

| Command | Purpose |
|---|---|
| `version-check` | Probe host + list terminals + pick a `MT5_TERMINAL_ID`. |
| `compile <file.mq5> [--autofix]` | MetaEditor compile with optional auto-retry loop. |
| `deploy <file> [--target experts\|indicators] [--verify]` | SCP + mtime verification (guards against MetaEditor silent-fail). |
| `list-deployed` | Enumerate `.ex5` on the VM with mtimes. |
| `parse-report <report.html\|xml>` | Normalize MT5 tester output → metrics JSON. |
| `extract-params <file.mq5>` | Extract `input`/`sinput`/`extern` variables. |
| `resolve-includes <file.mq5>` | Build the transitive `#include` graph. |
| `generate-set <file.mq5> --params p.json -o out.set` | Write a UTF-16 LE `.set`. |
| `backtest <EA> --symbol … --tf … --from … --to …` | Render tester.ini, run, fetch report, parse. |
| `optimize <EA> --ranges ranges.json --mode genetic` | Same but in optimization mode. |

## Decision tree

1. **New to the host** → run `climt5 version-check --json` first, copy the
   `MT5_TERMINAL_ID` into your `.env`.
2. **Fix compile errors** → `compile --autofix --max-iters 5` before deploying.
3. **Ship a change** → `compile → deploy --verify → list-deployed`.
4. **Evaluate an EA** → `backtest` (single run) or `optimize` (grid/genetic).
5. **Introspect inputs** → `extract-params` to build param dialogs or seed
   `--ranges` for optimization.

## Known failure modes

- **MetaEditor silent-fail** — exit code 0 while the `.ex5` is stale.
  → Always use `deploy --verify` and trust mtime/size, not exit codes.
- **Umlaut paths** — raw `C:/Users/Jürgen/...` breaks scp on non-UTF
  locales. `climt5` resolves every user-scoped path through
  `PowerShell Join-Path $env:APPDATA` to sidestep it.
- **UTF-16-LE BOM** — compile logs and tester reports are UTF-16 with BOM.
  All parsers strip the BOM before decoding; do not feed the raw file to
  a naive text reader.
- **Terminal-ID drift** — reinstalling MT5 regenerates the 32-char folder.
  Re-run `version-check` whenever compile/deploy can't find the target.
- **MT5 terminal exit codes** — `terminal64.exe /config:…` often returns
  non-zero on a successful run. `backtest`/`optimize` ignore the exit and
  rely on the report file appearing.

## JSON envelope

All commands emit exactly one line of JSON when `--json` is set:

```json
{"status":"ok","data":{...}}
{"status":"error","error":{"code":"…","message":"…","details":{...}}}
```

Error codes are stable: `terminal_id_missing`, `path_resolve_failed`,
`scp_failed`, `report_missing`, `compile_failed`, `ranges_invalid`,
`include_missing`, `unknown_params`.
