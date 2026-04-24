"""Parse MetaEditor64 compile logs.

The log is typically UTF-16 LE with BOM. MetaEditor writes lines like::

    /path/to/file.mq5(42,11) : error 123: some message
    /path/to/file.mq5(99,5)  : warning 42: something else

and a final summary::

    Result: 1 errors, 2 warnings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


LINE_RE = re.compile(
    r"(?P<path>[^()]+)\((?P<line>\d+),(?P<col>\d+)\)\s*:\s*"
    r"(?P<severity>error|warning|information)\s+"
    r"(?P<code>\d+)?\s*:?\s*(?P<message>.*)"
)
SUMMARY_RE = re.compile(
    r"Result:\s*(?P<errors>\d+)\s+errors?,\s*(?P<warnings>\d+)\s+warnings?",
    re.IGNORECASE,
)


@dataclass
class Diagnostic:
    path: str
    line: int
    column: int
    severity: str  # error | warning | information
    code: str | None
    message: str

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class CompileLog:
    diagnostics: list[Diagnostic] = field(default_factory=list)
    errors: int = 0
    warnings: int = 0

    @property
    def success(self) -> bool:
        return self.errors == 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "errors": self.errors,
            "warnings": self.warnings,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


def decode_log_bytes(raw: bytes) -> str:
    """Decode MetaEditor log bytes, honouring UTF-16 LE/BE BOMs."""
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


def parse(text: str) -> CompileLog:
    result = CompileLog()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = LINE_RE.match(line)
        if m:
            result.diagnostics.append(
                Diagnostic(
                    path=m.group("path").strip(),
                    line=int(m.group("line")),
                    column=int(m.group("col")),
                    severity=m.group("severity").lower(),
                    code=m.group("code"),
                    message=m.group("message").strip(),
                )
            )
            continue
        m = SUMMARY_RE.search(line)
        if m:
            result.errors = int(m.group("errors"))
            result.warnings = int(m.group("warnings"))
    # Fallback if no "Result:" line: count diagnostics by severity
    if not result.errors and not result.warnings:
        result.errors = sum(1 for d in result.diagnostics if d.severity == "error")
        result.warnings = sum(1 for d in result.diagnostics if d.severity == "warning")
    return result
