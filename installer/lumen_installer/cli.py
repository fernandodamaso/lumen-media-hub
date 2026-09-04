"""Argument parsing and dispatch boundary for the Linux installer."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
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
from .configure import run_configure
from .gpu import GPU_MODES
from .setup import (
    doctor_diagnostics,
    run_down,
    run_foundation,
    run_frontend_dev,
    run_redeploy_dashboard,
    run_up,
)
from .trakt import run_connect_trakt
from .update import UpdateManifest, run_rollback, run_update


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
    requested_gpu = getattr(args, "gpu_mode", None)
    if requested_gpu is None:
        requested_gpu = getattr(args, "gpu", None)
    diagnostics = doctor_diagnostics(host_report=report, gpu_mode=requested_gpu)
    report = {**report, **diagnostics}
    print(json.dumps(_redact_report(report), sort_keys=True))
    return int(report.get("exit_code", ExitCode.OK))


def _compose_options(args: argparse.Namespace) -> ComposeOptions:
    requested_gpu = getattr(args, "gpu_mode", None)
    if requested_gpu is None:
        requested_gpu = getattr(args, "gpu", None)
    return ComposeOptions(
        profiles=getattr(args, "profiles", None),
        gpu=requested_gpu,
        dev=bool(getattr(args, "dev", False)),
    )


def _setup(args: argparse.Namespace) -> int:
    requested_options = _compose_options(args)
    foundation = run_foundation(
        options=requested_options,
        answers_path=getattr(args, "answers", None),
        uid=getattr(args, "uid", None),
        gid=getattr(args, "gid", None),
        timezone=getattr(args, "timezone", None),
        root_path=getattr(args, "root_path", None),
        downloads_path=getattr(args, "downloads_path", None),
        network_mode=getattr(args, "network_mode", None),
        public_host=getattr(args, "public_host", None),
        interactive=not bool(getattr(args, "noninteractive", False)),
        gpu_confirm=bool(getattr(args, "gpu_confirm", False)),
        confirm=bool(getattr(args, "confirm", False)),
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    configured = run_configure(
        options=getattr(foundation, "options", requested_options),
        interactive=not bool(getattr(args, "noninteractive", False)),
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    print(
        json.dumps(
            {
                "foundation": _redact_report(foundation.report),
                "configure": _redact_report(configured.report),
            },
            sort_keys=True,
        )
    )
    return int(configured.exit_code)


def _up(args: argparse.Namespace) -> int:
    result = run_up(
        options=_compose_options(args),
        gpu_confirm=bool(getattr(args, "gpu_confirm", False)),
        dry_run=bool(getattr(args, "dry_run", False)),
    )
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


def _configure(args: argparse.Namespace) -> int:
    result = run_configure(
        options=_compose_options(args),
        interactive=not bool(getattr(args, "noninteractive", False)),
        confirm=bool(getattr(args, "confirm", False)),
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    print(json.dumps(_redact_report(result.report), sort_keys=True))
    return int(result.exit_code)


def _connect_trakt(args: argparse.Namespace) -> int:
    result = run_connect_trakt(
        Path(__file__).resolve().parents[2],
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    print(json.dumps(_redact_report(result.report), sort_keys=True))
    return int(result.exit_code)


_ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
_COMPOSE_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*):(?:\s|$)")
_COMPOSE_SERVICE = re.compile(r"^  ([A-Za-z_][A-Za-z0-9_.-]*):(?:\s|$)")
_COMPOSE_IMAGE = re.compile(r"^\s{4}image:\s*(.*?)\s*$")
_COMPOSE_PROFILES = re.compile(r"^\s{4}profiles:\s*(.*?)\s*$")
_COMPOSE_PROFILE_ITEM = re.compile(r"^\s+-\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*$")
_ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def _read_update_env(path: Path) -> dict[str, str]:
    """Read simple key/value entries without ever printing their values."""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []

    values: dict[str, str] = {}
    for line in lines:
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        if candidate.startswith("export "):
            candidate = candidate[7:].lstrip()
        match = _ENV_LINE.match(candidate)
        if match is None:
            continue
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[match.group(1)] = value

    # The process environment is the effective Compose environment and takes
    # precedence over values in the checkout's .env file.
    values.update({key: value for key, value in os.environ.items()})
    return values


def _expand_update_env(value: str, values: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(3)
        fallback = match.group(2)
        return values.get(name, fallback or "")

    return _ENV_REFERENCE.sub(replace, value).strip().strip("'\"")


def _known_compose_files(root: Path, values: Mapping[str, str], args: argparse.Namespace | None) -> list[Path]:
    """Resolve only Compose files within the checkout and known overlays."""

    configured = values.get("COMPOSE_FILE", "").strip()
    candidates: list[Path] = []
    if configured:
        for raw_path in configured.split(os.pathsep):
            if not raw_path.strip():
                continue
            candidate = Path(_expand_update_env(raw_path, values)).expanduser()
            if not candidate.is_absolute():
                candidate = root / candidate
            candidate = candidate.resolve(strict=False)
            try:
                candidate.relative_to(root)
            except ValueError:
                # Compose may accept arbitrary host paths, but update backups
                # must remain scoped to this checkout.
                continue
            candidates.append(candidate)
    else:
        candidates.append(root / "docker-compose.yml")
        requested_gpu = getattr(args, "gpu_mode", None) if args is not None else None
        if requested_gpu is None and args is not None:
            requested_gpu = getattr(args, "gpu", None)
        if requested_gpu is None:
            requested_gpu = values.get("GPU_MODE", values.get("GPU", ""))
        gpu_enabled = str(requested_gpu).strip().lower() not in {"", "none", "false", "0", "off", "no"}
        if gpu_enabled:
            candidates.append(root / "docker-compose.gpu.yml")
        if args is not None and bool(getattr(args, "dev", False)):
            candidates.append(root / "docker-compose.dev.yml")

    unique: list[Path] = []
    for candidate in candidates:
        candidate = candidate.resolve(strict=False)
        if candidate not in unique:
            unique.append(candidate)
    return unique


def _compose_metadata(compose_files: Sequence[Path], values: Mapping[str, str]) -> tuple[dict[str, str], list[str]]:
    """Extract service image references and declared profile names safely."""

    image_refs: dict[str, str] = {}
    profiles: list[str] = []
    for compose_file in compose_files:
        try:
            lines = compose_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        service: str | None = None
        in_profiles = False
        for line in lines:
            service_match = _COMPOSE_SERVICE.match(line)
            if service_match:
                service = service_match.group(1)
                in_profiles = False
                continue
            if _COMPOSE_KEY.match(line) and not line.startswith((" ", "\t")):
                service = None
                in_profiles = False
                continue
            if service is None:
                continue
            image_match = _COMPOSE_IMAGE.match(line)
            if image_match:
                image = _expand_update_env(image_match.group(1).split(" #", 1)[0], values)
                if image:
                    image_refs[service] = image
                in_profiles = False
                continue
            profile_match = _COMPOSE_PROFILES.match(line)
            if profile_match:
                in_profiles = True
                inline = profile_match.group(1).strip()
                if inline.startswith("[") and inline.endswith("]"):
                    profiles.extend(
                        item.strip().strip("'\"")
                        for item in inline[1:-1].split(",")
                        if item.strip()
                    )
                continue
            if in_profiles:
                profile_item = _COMPOSE_PROFILE_ITEM.match(line)
                if profile_item:
                    profiles.append(profile_item.group(1))
                elif line.strip():
                    in_profiles = False

    return image_refs, profiles


def _env_service_values(values: Mapping[str, str], suffixes: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in values.items():
        upper_key = key.upper()
        for suffix in suffixes:
            if not upper_key.endswith(suffix):
                continue
            service = upper_key[: -len(suffix)].removeprefix("LUMEN_").lower()
            if service and value.strip():
                result[service] = value.strip()
            break
    return result


def _env_json_map(values: Mapping[str, str], names: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        raw = values.get(name, "").strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, Mapping):
            result.update(
                {str(key): str(item) for key, item in parsed.items() if str(item).strip()}
            )
    return result


def _update_manifest(root: Path, args: argparse.Namespace | None = None) -> UpdateManifest:
    values = _read_update_env(root / ".env")
    compose_files = _known_compose_files(root, values, args)
    image_refs, declared_profiles = _compose_metadata(compose_files, values)
    image_refs.update(_env_json_map(values, ("LUMEN_IMAGE_REFS", "IMAGE_REFS")))
    image_refs.update(_env_service_values(values, ("_IMAGE_REF", "_IMAGE")))

    repo_digests = _env_json_map(values, ("LUMEN_REPO_DIGESTS", "REPO_DIGESTS"))
    repo_digests.update(_env_service_values(values, ("_REPO_DIGEST", "_IMAGE_DIGEST")))
    local_image_ids = _env_json_map(values, ("LUMEN_LOCAL_IMAGE_IDS", "LOCAL_IMAGE_IDS"))
    local_image_ids.update(_env_service_values(values, ("_LOCAL_IMAGE_ID", "_IMAGE_ID")))
    for service, reference in image_refs.items():
        if "@" in reference and service not in repo_digests:
            repo_digests[service] = reference.rsplit("@", 1)[1]

    requested_profiles = getattr(args, "profiles", None) if args is not None else None
    if requested_profiles is None:
        requested_profiles = [item for item in values.get("COMPOSE_PROFILES", "").split(",") if item.strip()]
    if isinstance(requested_profiles, str):
        requested_profiles = requested_profiles.split(",")
    profiles = list(dict.fromkeys(str(item).strip() for item in requested_profiles if str(item).strip()))
    if not profiles:
        profiles = list(dict.fromkeys(profile for profile in declared_profiles if profile))

    requested_gpu = getattr(args, "gpu_mode", None) if args is not None else None
    if requested_gpu is None and args is not None:
        requested_gpu = getattr(args, "gpu", None)
    if requested_gpu is None:
        requested_gpu = values.get("GPU_MODE", values.get("GPU_ENABLED", values.get("GPU", "")))
    if isinstance(requested_gpu, bool):
        gpu_mode = requested_gpu
    else:
        gpu_mode = str(requested_gpu).strip().lower() not in {"", "none", "false", "0", "off", "no", "disabled"}

    return UpdateManifest.from_inputs(
        env_path=root / ".env",
        runtime_paths={
            "config": root / "config",
            "state": root / ".state" / "installer" / "state.json",
        },
        image_refs=image_refs,
        repo_digests=repo_digests,
        local_image_ids=local_image_ids,
        profiles=profiles,
        gpu_mode=gpu_mode,
        compose_files=compose_files,
    )


def _update(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    confirm = bool(getattr(args, "confirm", False))
    dry_run = bool(getattr(args, "dry_run", False))
    rollback_id = getattr(args, "rollback", None)
    if rollback_id is not None and dry_run:
        result: dict[str, object] = {
            "action": "rollback",
            "dry_run": True,
            "run_id": rollback_id,
        }
    elif rollback_id is not None:
        result = run_rollback(root, rollback_id, confirm=confirm)
    else:
        result = run_update(
            root,
            _update_manifest(root, args),
            dry_run=dry_run,
            confirm=confirm,
        )
    print(json.dumps(_redact_report(result), sort_keys=True))
    return _normalize_handler_result(result.get("exit_code", ExitCode.OK))


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
        nargs="?",
        const="nvidia",
        choices=GPU_MODES,
        default=argparse.SUPPRESS,
        help="select GPU mode (auto, none, nvidia, or vaapi); bare flag means nvidia",
    )
    parser.add_argument(
        "--gpu-mode",
        dest="gpu_mode",
        choices=GPU_MODES,
        default=argparse.SUPPRESS,
        help="select GPU mode (auto, none, nvidia, or vaapi)",
    )
    parser.add_argument(
        "--no-gpu",
        dest="gpu",
        action="store_false",
        default=argparse.SUPPRESS,
        help="disable the saved GPU Compose overlay",
    )
    parser.add_argument(
        "--confirm-gpu",
        "--gpu-confirm",
        dest="gpu_confirm",
        action="store_true",
        default=argparse.SUPPRESS,
        help="confirm activation of a detected GPU in auto mode",
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
        if command == "setup":
            subparser.add_argument(
                "--confirm",
                dest="confirm",
                action="store_true",
                default=argparse.SUPPRESS,
                help="approve adopted Seerr configuration ownership changes",
            )
        if command == "update":
            subparser.add_argument(
                "--rollback",
                metavar="RUN_ID",
                help="Roll back a recorded update run.",
            )
            subparser.add_argument(
                "--confirm",
                action="store_true",
                default=argparse.SUPPRESS,
                help="approve the update or rollback operation",
            )
        if command == "configure":
            subparser.add_argument(
                "--confirm",
                "--confirm-drift",
                dest="confirm",
                action="store_true",
                default=argparse.SUPPRESS,
                help="approve managed configuration drift",
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
COMMAND_HANDLERS["configure"] = _configure
COMMAND_HANDLERS["connect-trakt"] = _connect_trakt
COMMAND_HANDLERS["update"] = _update


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
