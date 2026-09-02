"""Argument parsing and dispatch boundary for the Linux installer."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from .errors import (
    ExitCode,
    HelpRequested,
    InstallerError,
    InvalidInputError,
    NotAvailableError,
)
from .docker import run_host_doctor
from .compose import ComposeOptions
from .setup import (
    doctor_diagnostics,
    run_down,
    run_foundation,
    run_frontend_dev,
    run_redeploy_dashboard,
    run_up,
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


def _safe_argument_error(message: str) -> str:
    """Keep invalid-argument diagnostics useful without echoing raw values."""

    if message.startswith("unrecognized arguments:"):
        return "unrecognized arguments"
    return message


class InstallerArgumentParser(argparse.ArgumentParser):
    """Convert expected argparse failures into typed installer errors."""

    def error(self, message: str) -> None:
        raise InvalidInputError(f"argument error: {_safe_argument_error(message)}")

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


_SECRET_FIELD = re.compile(
    r"(?:password|secret|token|api[_-]?key|private[_-]?key|credential|cookie|account[_-]?id)",
    re.IGNORECASE,
)


def _redact_report(value: Any) -> Any:
    """Redact secret-looking fields before a doctor report reaches stdout."""

    if isinstance(value, Mapping):
        return {
            str(key): "<redacted>"
            if _SECRET_FIELD.search(str(key))
            else _redact_report(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [_redact_report(item) for item in value]
    if isinstance(value, list):
        return [_redact_report(item) for item in value]
    return value


def _doctor(args: argparse.Namespace) -> int:
    report = run_host_doctor(
        uid=getattr(args, "uid", None),
        gid=getattr(args, "gid", None),
        timezone=getattr(args, "timezone", None),
        image=getattr(args, "image", None),
    )
    # Keep the host preflight call at this boundary for compatibility with
    # callers that inject only the Docker portion, then add safe local
    # environment/network/storage/state diagnostics from the lifecycle layer.
    diagnostics = doctor_diagnostics(host_report=report)
    report = {**report, **diagnostics}
    print(json.dumps(_redact_report(report), sort_keys=True))
    return int(ExitCode.OK)


def _compose_options(args: argparse.Namespace) -> ComposeOptions:
    return ComposeOptions(
        profiles=getattr(args, "profiles", None),
        gpu=getattr(args, "gpu", None),
        dev=bool(getattr(args, "dev", False)),
    )


def _setup(args: argparse.Namespace) -> int:
    result = run_foundation(
        options=_compose_options(args),
        answers_path=getattr(args, "answers", None),
        uid=getattr(args, "uid", None),
        gid=getattr(args, "gid", None),
        timezone=getattr(args, "timezone", None),
        root_path=getattr(args, "root_path", None),
        downloads_path=getattr(args, "downloads_path", None),
        network_mode=getattr(args, "network_mode", None),
        public_host=getattr(args, "public_host", None),
        interactive=not bool(getattr(args, "noninteractive", False)),
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    print(json.dumps(_redact_report(result.report), sort_keys=True))
    return int(ExitCode.OK)


def _up(args: argparse.Namespace) -> int:
    result = run_up(options=_compose_options(args), dry_run=bool(getattr(args, "dry_run", False)))
    print(json.dumps(_redact_report(result.report), sort_keys=True))
    return int(ExitCode.OK)


def _down(args: argparse.Namespace) -> int:
    result = run_down(options=_compose_options(args), dry_run=bool(getattr(args, "dry_run", False)))
    print(json.dumps(_redact_report(result.report), sort_keys=True))
    return int(ExitCode.OK)


def _redeploy_dashboard(args: argparse.Namespace) -> int:
    result = run_redeploy_dashboard(options=_compose_options(args), dry_run=bool(getattr(args, "dry_run", False)))
    print(json.dumps(_redact_report(result.report), sort_keys=True))
    return int(ExitCode.OK)


def _frontend_dev(args: argparse.Namespace) -> int:
    result = run_frontend_dev(dry_run=bool(getattr(args, "dry_run", False)))
    print(json.dumps(_redact_report(result.report), sort_keys=True))
    return int(ExitCode.OK)


def _owner_id(value: str) -> int:
    candidate = value.strip()
    try:
        parsed = int(candidate, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a nonzero integer") from exc
    if parsed <= 0 or not candidate.isdigit():
        raise argparse.ArgumentTypeError("must be a nonzero integer")
    return parsed


def _add_shared_options(parser: argparse.ArgumentParser, *, suppress_defaults: bool = False) -> None:
    """Add options shared by every installer command.

    They are accepted both before and after the command name.  Child parser
    defaults are suppressed so a value supplied before the command is not
    overwritten while argparse descends into the subparser.
    """

    default = argparse.SUPPRESS if suppress_defaults else None
    parser.add_argument(
        "--uid",
        "--puid",
        dest="uid",
        type=_owner_id,
        default=default,
        metavar="UID",
        help="numeric owner UID for files and containers",
    )
    parser.add_argument(
        "--gid",
        "--pgid",
        dest="gid",
        type=_owner_id,
        default=default,
        metavar="GID",
        help="numeric owner GID for files and containers",
    )
    parser.add_argument(
        "--timezone",
        "--tz",
        dest="timezone",
        default=default,
        metavar="ZONE",
        help="override detected host timezone",
    )
    parser.add_argument(
        "--answers",
        dest="answers",
        default=default,
        metavar="PATH",
        help="load non-secret answers from a version-1 JSON file",
    )
    parser.add_argument(
        "--non-interactive",
        dest="noninteractive",
        action="store_true",
        default=argparse.SUPPRESS if suppress_defaults else False,
        help="fail when a required value is missing instead of prompting",
    )
    parser.add_argument(
        "--profile",
        dest="profiles",
        action="append",
        default=argparse.SUPPRESS if suppress_defaults else argparse.SUPPRESS,
        metavar="NAME",
        help="enable a Compose profile (repeatable)",
    )
    parser.add_argument(
        "--gpu",
        dest="gpu",
        action="store_true",
        default=argparse.SUPPRESS,
        help="enable the NVIDIA Compose overlay when available",
    )
    parser.add_argument(
        "--no-gpu",
        dest="gpu",
        action="store_false",
        default=argparse.SUPPRESS,
        help="disable the saved GPU Compose overlay",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        default=argparse.SUPPRESS,
        help="use the Docker hot-reload development overlay",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=argparse.SUPPRESS,
        help="render checks and commands without mutation",
    )
    parser.add_argument("--root-path", dest="root_path", metavar="PATH", default=default)
    parser.add_argument("--downloads-path", dest="downloads_path", metavar="PATH", default=default)
    parser.add_argument("--network-mode", dest="network_mode", metavar="MODE", default=default)
    parser.add_argument("--public-host", dest="public_host", metavar="HOST", default=default)


def build_parser() -> InstallerArgumentParser:
    """Build the parser containing the complete public Linux command set."""

    parser = InstallerArgumentParser(
        prog="lumen_installer",
        description="Lumen Media Hub Linux installer",
    )
    _add_shared_options(parser)
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
        _add_shared_options(subparser, suppress_defaults=True)
        if command == "doctor":
            subparser.add_argument(
                "--image",
                metavar="IMAGE",
                help="inspect a registry manifest without pulling the image",
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
COMMAND_HANDLERS["doctor"] = _doctor
COMMAND_HANDLERS["setup"] = _setup
COMMAND_HANDLERS["up"] = _up
COMMAND_HANDLERS["down"] = _down
COMMAND_HANDLERS["frontend-dev"] = _frontend_dev
COMMAND_HANDLERS["redeploy-dashboard"] = _redeploy_dashboard


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
