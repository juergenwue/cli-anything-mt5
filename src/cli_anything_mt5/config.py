"""Configuration for cli-anything-mt5.

Loads MT5_HOST, MT5_USER, MT5_ROOT, MT5_TERMINAL_ID from a .env file in the
current working directory or the user's home. Umlaut-safe PowerShell helpers
are used for Windows paths.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from CWD first, then from home as a fallback
for candidate in (Path.cwd() / ".env", Path.home() / ".cli-anything-mt5.env"):
    if candidate.exists():
        load_dotenv(candidate)
        break

MT5_HOST: str = os.getenv("MT5_HOST", "192.168.178.83")
MT5_USER: str = os.getenv("MT5_USER", "Juergen")

# MT5 installation root on the Windows host. Colon form ("C:/Program Files/...")
# plays nicely with scp and bash; the PowerShell layer accepts both.
MT5_ROOT: str = os.getenv("MT5_ROOT", "C:/Program Files/MT5/ICMarkets")

# Terminal-data ID. Empty string means "let version-check auto-discover".
MT5_TERMINAL_ID: str = os.getenv("MT5_TERMINAL_ID", "")

# Timeouts (seconds)
MT5_SSH_TIMEOUT: int = int(os.getenv("MT5_SSH_TIMEOUT", "30"))
MT5_SCP_TIMEOUT: int = int(os.getenv("MT5_SCP_TIMEOUT", "60"))
MT5_COMPILE_TIMEOUT: int = int(os.getenv("MT5_COMPILE_TIMEOUT", "60"))
MT5_TESTER_TIMEOUT: int = int(os.getenv("MT5_TESTER_TIMEOUT", "900"))


# PowerShell expressions that resolve on the Windows host. Using env vars
# avoids hardcoding paths that contain umlauts (e.g. C:/Users/Jürgen/...).
def metaquotes_terminal_root() -> str:
    """PowerShell expression for the MetaQuotes Terminal parent directory."""
    return '(Join-Path $env:APPDATA "MetaQuotes\\Terminal")'


def terminal_mql5_dir(terminal_id: str, subdir: str = "Experts") -> str:
    """PowerShell expression for a MQL5 subdirectory under a given terminal."""
    return (
        f'(Join-Path $env:APPDATA '
        f'"MetaQuotes\\Terminal\\{terminal_id}\\MQL5\\{subdir}")'
    )


def terminal_tester_dir(terminal_id: str) -> str:
    """PowerShell expression for the Tester output directory."""
    return (
        f'(Join-Path $env:APPDATA '
        f'"MetaQuotes\\Terminal\\{terminal_id}\\Tester")'
    )


# --- TOML targets integration -------------------------------------------------
#
# Multi-target callers should resolve via `cli_anything_core.targets.load_targets`
# and `resolve(...)`. The wrapper below is a convenience that picks the legacy
# default target when the user did not pass `--target=`.

_targets_cache = None


def targets():
    """Load and cache the targets.toml file (lazy)."""
    global _targets_cache
    if _targets_cache is None:
        from cli_anything_core.targets import load_targets

        _targets_cache = load_targets()
    return _targets_cache


def default_target_name() -> str:
    """Default target when --target was not given.

    Priority:
    1. Env var MT5_DEFAULT_TARGET
    2. First target in targets.toml that supports 'mt5' on a Windows host
    3. 'windowsvm' (legacy expectation)
    """
    if env := os.getenv("MT5_DEFAULT_TARGET"):
        return env
    try:
        tf = targets()
    except Exception:
        return "windowsvm"
    for name, t in tf.targets.items():
        if t.os == "windows" and "mt5" in t.platforms:
            return name
    return "windowsvm"
