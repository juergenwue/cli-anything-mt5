"""Output schemas and helpers for machine-readable (`--json`) results.

Every command emits a top-level envelope: ``{"status": "ok"|"error", ...}``.
Exit code 0 on ok, 1 on error.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import click
from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class Envelope(BaseModel):
    status: str  # "ok" or "error"
    data: dict[str, Any] | None = None
    error: ErrorBody | None = None


def emit_ok(data: dict[str, Any] | BaseModel, *, json_mode: bool) -> None:
    """Emit a success envelope and exit 0."""
    if isinstance(data, BaseModel):
        payload = data.model_dump(mode="json")
    else:
        payload = data
    if json_mode:
        env = Envelope(status="ok", data=payload)
        click.echo(json.dumps(env.model_dump(mode="json", exclude_none=True)))
    else:
        _human_print(payload)
    sys.exit(0)


def emit_error(
    code: str,
    message: str,
    *,
    json_mode: bool,
    details: dict[str, Any] | None = None,
    exit_code: int = 1,
) -> None:
    """Emit an error envelope and exit with a non-zero status."""
    env = Envelope(
        status="error",
        error=ErrorBody(code=code, message=message, details=details),
    )
    if json_mode:
        click.echo(json.dumps(env.model_dump(mode="json", exclude_none=True)))
    else:
        click.secho(f"ERROR [{code}]: {message}", fg="red", err=True)
        if details:
            click.secho(json.dumps(details, indent=2), fg="yellow", err=True)
    sys.exit(exit_code)


def _human_print(payload: Any, indent: int = 0) -> None:
    """Render a dict/list payload for humans. Readable for small outputs."""
    prefix = "  " * indent
    if isinstance(payload, dict):
        for k, v in payload.items():
            if isinstance(v, (dict, list)):
                click.echo(f"{prefix}{k}:")
                _human_print(v, indent + 1)
            else:
                click.echo(f"{prefix}{k}: {v}")
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, (dict, list)):
                _human_print(item, indent)
                click.echo("")
            else:
                click.echo(f"{prefix}- {item}")
    else:
        click.echo(f"{prefix}{payload}")
