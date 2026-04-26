"""Multi-target dispatch helpers for climt5 commands.

A command implements a single-target ``run(client, target, **opts)`` callable
and lets ``dispatch(...)`` fan out across resolved targets, in parallel by
default.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from cli_anything_core.targets import Target

from . import config, ssh
from .output import emit_error, emit_ok

MAX_PARALLEL = 4


def resolve_targets(
    target_pattern: str | None,
    *,
    platform: str = "mt5",
    json_mode: bool,
) -> list[Target]:
    """Resolve a ``--target=`` pattern, defaulting to the configured default.

    Emits an error and exits if the pattern matches nothing or the targets
    file is missing.
    """
    pattern = target_pattern or config.default_target_name()
    try:
        tf = config.targets()
    except FileNotFoundError as e:
        emit_error(
            code="targets_file_missing",
            message=str(e),
            json_mode=json_mode,
        )
    except Exception as e:
        emit_error(
            code="targets_load_failed",
            message=str(e),
            json_mode=json_mode,
        )
    from cli_anything_core.targets import resolve as _resolve

    try:
        targets = _resolve(pattern, tf, platform=platform)
    except KeyError as e:
        emit_error(
            code="target_not_found",
            message=str(e),
            json_mode=json_mode,
            details={"pattern": pattern},
        )
    if not targets:
        emit_error(
            code="no_targets_matched",
            message=f"Pattern {pattern!r} matched no targets supporting {platform!r}.",
            json_mode=json_mode,
        )
    return targets


def dispatch(
    targets: list[Target],
    runner: Callable[[Any, Target], dict[str, Any]],
    *,
    sequential: bool,
    json_mode: bool,
) -> None:
    """Run ``runner(client, target)`` per target and emit a combined envelope.

    Each runner returns a per-target dict; failures should raise ``ssh.SshError``
    (caught here and folded into the envelope as a per-target error).
    """
    def _one(t: Target) -> dict[str, Any]:
        client = ssh.make_client(t)
        entry: dict[str, Any] = {"target": t.name, "host": t.host}
        try:
            entry.update(runner(client, t))
            entry["status"] = "ok"
        except ssh.SshError as e:
            entry["status"] = "error"
            entry["error"] = {"code": "ssh_failed", "message": str(e)}
        except Exception as e:  # noqa: BLE001 — surface anything per-target
            entry["status"] = "error"
            entry["error"] = {"code": "runner_failed", "message": str(e)}
        return entry

    if len(targets) == 1 or sequential:
        results = [_one(t) for t in targets]
    else:
        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL, len(targets))) as pool:
            results = list(pool.map(_one, targets))

    n_err = sum(1 for r in results if r["status"] != "ok")
    payload = {"targets": results, "ok_count": len(results) - n_err, "error_count": n_err}
    if n_err and len(results) == 1:
        # Single target: fail the command entirely (legacy semantics).
        err = results[0].get("error", {})
        emit_error(
            code=err.get("code", "deploy_failed"),
            message=err.get("message", "deploy failed"),
            json_mode=json_mode,
            details=results[0],
        )
    if n_err:
        emit_error(
            code="partial_failure",
            message=f"{n_err}/{len(results)} target(s) failed.",
            json_mode=json_mode,
            details=payload,
        )
    emit_ok(payload, json_mode=json_mode)
