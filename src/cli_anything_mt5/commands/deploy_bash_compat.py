"""`climt5 deploy-bash-compat` — translate legacy deploy-mt5.sh CLI flags.

The old shell wrapper accepted ``--target=windowsvm|sqx --broker=NAME|all
--type=ea|indicator --compile --dry-run``. This command maps those onto the
new ``climt5 deploy``/``climt5 compile`` calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from .compile import compile_cmd
from .deploy import deploy_cmd

_TYPE_TO_SUBDIR = {
    "ea": "Experts",
    "indicator": "Indicators",
    "script": "Scripts",
    "include": "Include",
}


def _translate_target(target: str, broker: str) -> str:
    """Map old (target, broker) onto a new --target= pattern."""
    target = (target or "windowsvm").lower()
    if target == "windowsvm":
        return "windowsvm"
    if target in {"sqx", "sqx1"}:
        if not broker or broker == "all":
            return "sqx1.*"
        return f"sqx1.{broker.lower()}"
    if target == "sqx2":
        if not broker or broker == "all":
            return "sqx2.*"
        return f"sqx2.{broker.lower()}"
    return target


@click.command(
    "deploy-bash-compat",
    help="Compatibility shim for the legacy deploy-mt5.sh shell flags.",
    context_settings={"ignore_unknown_options": False},
)
@click.option("--target", "target", default="windowsvm", show_default=True)
@click.option("--broker", "broker", default="all", show_default=True)
@click.option("--type", "file_type", default=None, type=click.Choice(list(_TYPE_TO_SUBDIR)))
@click.option("--compile", "do_compile", is_flag=True, default=False)
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.option("--json", "json_mode", is_flag=True)
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def deploy_bash_compat(
    ctx: click.Context,
    target: str,
    broker: str,
    file_type: str | None,
    do_compile: bool,
    dry_run: bool,
    json_mode: bool,
    source: Path,
) -> None:
    new_target = _translate_target(target, broker)
    subdir = _TYPE_TO_SUBDIR[file_type] if file_type else None

    deploy_args: list[str] = ["--target", new_target]
    if subdir:
        deploy_args += ["--subdir", subdir]
    if json_mode:
        deploy_args.append("--json")
    deploy_args.append(str(source))

    if dry_run:
        click.echo(f"DRY-RUN: climt5 deploy {' '.join(deploy_args)}", err=True)
        if do_compile and source.suffix.lower() == ".mq5":
            click.echo(
                f"DRY-RUN: climt5 compile --target {new_target} {source}", err=True
            )
        sys.exit(0)

    # Invoke deploy via Click's runner (re-enters this process).
    try:
        ctx.invoke(deploy_cmd, **_args_to_kwargs(deploy_cmd, deploy_args))
    except SystemExit as e:
        if e.code not in (None, 0):
            raise

    if do_compile and source.suffix.lower() == ".mq5":
        compile_args: list[str] = ["--target", new_target]
        if subdir:
            compile_args += ["--subdir", subdir]
        if json_mode:
            compile_args.append("--json")
        compile_args.append(str(source))
        ctx.invoke(compile_cmd, **_args_to_kwargs(compile_cmd, compile_args))


def _args_to_kwargs(cmd: click.Command, argv: list[str]) -> dict:
    """Parse a list of CLI args against a Click command into a kwargs dict.

    Click's `ctx.invoke()` requires kwargs, not argv. We use the command's own
    parser to do the translation so option aliases stay in sync.
    """
    parser = cmd.make_context("compat", argv, allow_extra_args=False, resilient_parsing=False)
    return dict(parser.params)
