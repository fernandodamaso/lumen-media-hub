"""Argument parsing and dispatch boundary for the Linux installer."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Any, Callable

from .errors import (
    ExitCode,
    HelpRequested,
    InstallerError,
    InvalidInputError,
    NotAvailableError,
)


PUBLIC_COMMANDS = (
    "setup",
    "doctor",
    "up",
    "down",
    "frontend-dev",
    "redeploy-dashboard",
    "configure",
    "connect-trakt",
    "update",
)

# This alias lets callers inspect command discovery without spelling the
# private argparse implementation type themselves.
CommandChoicesAction = argparse._SubParsersAction


class InstallerArgumentParser(argparse.ArgumentParser):
    """Convert expected argparse failures into typed installer errors."""

    def error(self, message: str) -> None:
        raise InvalidInputError(f"argument error: {message}")

    def exit(self, status: int = 0, message: str | None = None) -> None:
        if message:
            self._print_message(message, sys.stderr if status else sys.stdout)
        if status == 0:
            raise HelpRequested()
        raise InvalidInputError(message or "argument parsing failed")


Handler = Callable[[argparse.Namespace], int | ExitCode | None]


def _not_available(args: argparse.Namespace) -> None:
    raise NotAvailableError(
        f"command '{args.command}' is not available in this installer phase"
    )


def build_parser() -> InstallerArgumentParser:
    """Build the parser containing the complete public Linux command set."""

    parser = InstallerArgumentParser(
        prog="lumen_installer",
        description="Lumen Media Hub Linux installer",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        metavar="COMMAND",
        title="commands",
        parser_class=InstallerArgumentParser,
        required=True,
    )

    descriptions = {
        "setup": "Prepare and configure the Lumen Media Hub stack.",
        "doctor": "Inspect host and stack prerequisites.",
        "up": "Start the configured media stack.",
        "down": "Stop the configured media stack.",
        "frontend-dev": "Install frontend dependencies for development.",
        "redeploy-dashboard": "Rebuild and redeploy the production dashboard.",
        "configure": "Reconcile managed service configuration.",
        "connect-trakt": "Connect the local Trakt account.",
        "update": "Update stack images and managed configuration.",
    }
    for command in PUBLIC_COMMANDS:
        subparser = subparsers.add_parser(
            command,
            help=descriptions[command],
            description=descriptions[command],
        )
        if command == "update":
            subparser.add_argument(
                "--rollback",
                metavar="RUN_ID",
                help="Roll back a recorded update run.",
            )

    return parser


COMMAND_HANDLERS: dict[str, Handler] = {
    command: _not_available for command in PUBLIC_COMMANDS
}


def dispatch(args: argparse.Namespace) -> int | ExitCode | None:
    """Dispatch parsed arguments to the handler owned by the current phase."""

    try:
        handler = COMMAND_HANDLERS[args.command]
    except (AttributeError, KeyError) as exc:
        raise InvalidInputError("a valid installer command is required") from exc
    return handler(args)


def _normalize_handler_result(result: Any) -> int:
    if result is None:
        return int(ExitCode.OK)
    if isinstance(result, ExitCode):
        return int(result)
    valid_codes = {int(code) for code in ExitCode}
    if isinstance(result, int) and result in valid_codes:
        return result
    raise InvalidInputError("installer command returned an invalid exit code")


def main(argv: Sequence[str] | None = None) -> int:
    """Parse and dispatch a command, returning its stable process exit code."""

    try:
        args = build_parser().parse_args(argv)
        return _normalize_handler_result(dispatch(args))
    except InstallerError as error:
        if error.message:
            print(error.message, file=sys.stderr)
        return int(error.exit_code)


__all__ = [
    "COMMAND_HANDLERS",
    "CommandChoicesAction",
    "PUBLIC_COMMANDS",
    "build_parser",
    "dispatch",
    "main",
]
