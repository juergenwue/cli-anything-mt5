"""Root Click group for cli-anything-mt5.

Entry point: ``climt5``. All commands accept ``--json`` for machine output.
"""

from __future__ import annotations

import click

from . import __version__
from .commands import (
    compile as compile_cmd,
)
from .commands import (
    deploy as deploy_cmd,
)
from .commands import (
    list_deployed as list_deployed_cmd,
)
from .commands import (
    parse_report as parse_report_cmd,
)
from .commands import (
    version_check as version_check_cmd,
)
from .commands import (
    extract_params as extract_params_cmd,
)
from .commands import (
    resolve_includes as resolve_includes_cmd,
)
from .commands import (
    generate_set as generate_set_cmd,
)
from .commands import (
    backtest as backtest_cmd_mod,
)
from .commands import (
    optimize as optimize_cmd_mod,
)


@click.group(
    help=(
        "Agent-native CLI for MetaTrader 5.\n\n"
        "Drives a remote Windows MT5 terminal over SSH: compile, deploy, "
        "backtest MQL5 EAs and indicators. Every command supports --json "
        "for machine-readable output."
    )
)
@click.version_option(__version__, prog_name="climt5")
def cli() -> None:
    pass


cli.add_command(version_check_cmd.version_check)
cli.add_command(compile_cmd.compile_cmd, name="compile")
cli.add_command(deploy_cmd.deploy_cmd, name="deploy")
cli.add_command(list_deployed_cmd.list_deployed, name="list-deployed")
cli.add_command(parse_report_cmd.parse_report, name="parse-report")
cli.add_command(extract_params_cmd.extract_params, name="extract-params")
cli.add_command(resolve_includes_cmd.resolve_includes, name="resolve-includes")
cli.add_command(generate_set_cmd.generate_set, name="generate-set")
cli.add_command(backtest_cmd_mod.backtest_cmd, name="backtest")
cli.add_command(optimize_cmd_mod.optimize_cmd, name="optimize")


if __name__ == "__main__":
    cli()
