"""Re-export of the core JSON envelope helpers (kept for import stability)."""

from __future__ import annotations

from cli_anything_core.output import (
    Envelope,
    ErrorBody,
    emit_error,
    emit_ok,
)

__all__ = ["Envelope", "ErrorBody", "emit_error", "emit_ok"]
