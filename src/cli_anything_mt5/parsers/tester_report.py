"""Parse MT5 Strategy Tester reports (HTML or XML) into normalized metrics.

MT5 writes HTML reports as UTF-16 LE with BOM. The layout is stable across
terminal builds: a table of ``<tr><td>Key</td><td>Value</td></tr>`` pairs
in the header, followed by the trade list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Keys we care about; the raw HTML uses German or English labels depending on
# the terminal locale. We canonicalize to snake_case.
LABEL_MAP: dict[str, str] = {
    "Total Net Profit": "net_profit",
    "Gross Profit": "gross_profit",
    "Gross Loss": "gross_loss",
    "Profit Factor": "profit_factor",
    "Expected Payoff": "expected_payoff",
    "Recovery Factor": "recovery_factor",
    "Sharpe Ratio": "sharpe_ratio",
    "Balance Drawdown Absolute": "balance_drawdown_abs",
    "Balance Drawdown Maximal": "balance_drawdown_max",
    "Equity Drawdown Maximal": "equity_drawdown_max",
    "Total Trades": "total_trades",
    "Short Trades (won %)": "short_trades_won_pct",
    "Long Trades (won %)": "long_trades_won_pct",
    "Profit Trades (% of total)": "profit_trades_pct",
    "Loss Trades (% of total)": "loss_trades_pct",
    "Symbol": "symbol",
    "Period": "period",
    "Expert": "expert",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# MT5 uses plain space, U+00A0 (NBSP), or U+202F (narrow NBSP) for thousands.
_SPACE_RE = re.compile(r"[\s  ]+")


@dataclass
class TesterReport:
    raw: dict[str, str]
    metrics: dict[str, float | int | str]

    def to_dict(self) -> dict:
        return {"metrics": self.metrics, "raw": self.raw}


def _strip_tags(s: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub("", s)).strip()


def _coerce(key: str, val: str) -> float | int | str:
    """Convert numeric strings, keep strings for symbol/period/expert.

    Handles MT5 quirks: thousand-separator spaces, NBSPs, trailing percent,
    and parenthesized suffixes like "500.00 (5.00%)".
    """
    if key in {"symbol", "period", "expert"}:
        return val
    # Take the leading token up to the first paren or percent sign.
    token = re.split(r"[(%]", val.strip(), maxsplit=1)[0].strip()
    # Remove any whitespace-like separators used as thousands separator.
    token = _SPACE_RE.sub("", token)
    # If comma is used as decimal separator (German locale), swap.
    if "," in token and "." not in token:
        token = token.replace(",", ".")
    try:
        if "." in token:
            return float(token)
        return int(token)
    except ValueError:
        return val


def decode_report_bytes(raw: bytes) -> str:
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le", errors="replace")
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def parse_html(text: str) -> TesterReport:
    raw: dict[str, str] = {}
    # Match <tr><td>Label:</td><td>Value</td>...</tr> variants
    row_re = re.compile(
        r"<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>",
        re.IGNORECASE | re.DOTALL,
    )
    for m in row_re.finditer(text):
        label = _strip_tags(m.group(1)).rstrip(":").strip()
        value = _strip_tags(m.group(2))
        if label and label not in raw:
            raw[label] = value
    metrics: dict[str, float | int | str] = {}
    for label, canonical in LABEL_MAP.items():
        if label in raw:
            metrics[canonical] = _coerce(canonical, raw[label])
    return TesterReport(raw=raw, metrics=metrics)


def parse_file(path: Path) -> TesterReport:
    data = Path(path).read_bytes()
    text = decode_report_bytes(data)
    return parse_html(text)
