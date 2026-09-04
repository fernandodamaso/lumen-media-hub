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
    PartialError,
)
from .commands import CommandExecutionError, CommandRunner
from .compose import (
    ComposeOptions,
    build as compose_build,
    config as compose_config,
    derive_build_services,
    derive_pull_services,
    pull as compose_pull,
    run_compose,
    up as compose_up,
)
from .docker import run_host_doctor
from .configure import run_configure
from .gpu import GPU_MODES
from .setup import (
    doctor_diagnostics,
    run_down,
    run_foundation,
    run_frontend_dev,
    run_redeploy_dashboard,
    run_up,
    wait_for_health,
)
from .trakt import run_connect_trakt
from .update import (
    UpdateManifest,
    _digest_repository,
    _normalize_repo_digest,
    _safe_run_id,
    _validate_compose_name,
    _validate_image_id,
    _validate_image_reference,
    run_rollback,
    run_update,
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


_KNOWN_UPDATE_GPU_MODES = frozenset({"none", "auto", "nvidia", "vaapi"})


def _update_gpu_mode(values: Mapping[str, str], args: argparse.Namespace | None) -> str:
    """Return the concrete saved/requested GPU mode without probing Docker."""

    requested = getattr(args, "gpu_mode", None) if args is not None else None
    if requested is None and args is not None:
        requested = getattr(args, "gpu", None)
    if requested is None:
        requested = values.get("GPU_MODE")
    if requested is None:
        requested = values.get("GPU_ENABLED", values.get("GPU", "none"))
    if isinstance(requested, bool):
        return "nvidia" if requested else "none"
    normalized = str(requested).strip().lower()
    if normalized in _KNOWN_UPDATE_GPU_MODES:
        return normalized
    if normalized in {"", "false", "0", "off", "no", "disabled"}:
        return "none"
    raise InvalidInputError("GPU mode must be none, auto, nvidia, or vaapi")


def _active_update_profiles(
    values: Mapping[str, str],
    args: argparse.Namespace | None,
    *,
    saved_profiles: Sequence[str] = (),
) -> list[str]:
    requested = getattr(args, "profiles", None) if args is not None else None
    if requested is None:
        configured = values.get("COMPOSE_PROFILES", "")
        requested = configured.split(",") if configured.strip() else saved_profiles
    if isinstance(requested, str):
        requested = requested.split(",")
    result: list[str] = []
    for profile in requested or ():
        value = str(profile).strip()
        if value and value not in result:
            result.append(value)
    return result


def _gpu_overlay_mode(mode: str, values: Mapping[str, str]) -> str:
    """Resolve an ``auto`` selection from saved metadata when available."""

    if mode != "auto":
        return mode
    resolved = str(values.get("GPU_RESOLVED_MODE", "")).strip().lower()
    if resolved in {"none", "nvidia", "vaapi"}:
        return resolved
    raise InvalidInputError("GPU_MODE=auto requires a persisted concrete GPU mode")


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
        requested_gpu = _gpu_overlay_mode(_update_gpu_mode(values, args), values)
        if requested_gpu == "nvidia":
            candidates.append(root / "docker-compose.gpu.yml")
        elif requested_gpu == "vaapi":
            candidates.append(root / "docker-compose.vaapi.yml")
        if args is not None and bool(getattr(args, "dev", False)):
            candidates.append(root / "docker-compose.dev.yml")

    unique: list[Path] = []
    for candidate in candidates:
        candidate = candidate.resolve(strict=False)
        if candidate not in unique:
            unique.append(candidate)
    return unique


def _compose_metadata(
    compose_files: Sequence[Path],
    values: Mapping[str, str],
    active_profiles: Sequence[str] = (),
) -> tuple[dict[str, str], list[str]]:
    """Extract image refs for active services and all declared profile names."""

    image_refs: dict[str, str] = {}
    profiles: list[str] = []
    active = set(active_profiles)
    for compose_file in compose_files:
        try:
            lines = compose_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        service: str | None = None
        image: str | None = None
        service_profiles: list[str] = []
        in_profiles = False

        def flush() -> None:
            if service is None:
                return
            for profile in service_profiles:
                if profile not in profiles:
                    profiles.append(profile)
            if image and (not service_profiles or active.intersection(service_profiles)):
                image_refs[service] = image

        for line in lines:
            service_match = _COMPOSE_SERVICE.match(line)
            if service_match:
                flush()
                service = service_match.group(1)
                image = None
                service_profiles = []
                in_profiles = False
                continue
            if _COMPOSE_KEY.match(line) and not line.startswith((" ", "\t")):
                flush()
                service = None
                image = None
                service_profiles = []
                in_profiles = False
                continue
            if service is None:
                continue
            image_match = _COMPOSE_IMAGE.match(line)
            if image_match:
                candidate = _expand_update_env(
                    image_match.group(1).split(" #", 1)[0], values
                )
                if candidate:
                    image = candidate
                in_profiles = False
                continue
            profile_match = _COMPOSE_PROFILES.match(line)
            if profile_match:
                in_profiles = True
                inline = profile_match.group(1).strip()
                if inline.startswith("[") and inline.endswith("]"):
                    service_profiles.extend(
                        item.strip().strip("'\"")
                        for item in inline[1:-1].split(",")
                        if item.strip()
                    )
                continue
            if in_profiles:
                profile_item = _COMPOSE_PROFILE_ITEM.match(line)
                if profile_item:
                    service_profiles.append(profile_item.group(1))
                elif line.strip():
                    in_profiles = False
        flush()

    return image_refs, profiles


def _compose_service_activity(
    compose_files: Sequence[Path], active_profiles: Sequence[str]
) -> tuple[set[str], set[str]]:
    """Return declared and active service names from selected Compose files."""

    active_profiles_set = set(active_profiles)
    declared: set[str] = set()
    active: set[str] = set()
    for compose_file in compose_files:
        try:
            lines = compose_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        service: str | None = None
        service_profiles: list[str] = []
        in_profiles = False

        def flush() -> None:
            if service is None:
                return
            declared.add(service)
            if not service_profiles or active_profiles_set.intersection(service_profiles):
                active.add(service)

        for line in lines:
            service_match = _COMPOSE_SERVICE.match(line)
            if service_match:
                flush()
                service = service_match.group(1)
                service_profiles = []
                in_profiles = False
                continue
            if _COMPOSE_KEY.match(line) and not line.startswith((" ", "\t")):
                flush()
                service = None
                service_profiles = []
                in_profiles = False
                continue
            if service is None:
                continue
            profile_match = _COMPOSE_PROFILES.match(line)
            if profile_match:
                in_profiles = True
                inline = profile_match.group(1).strip()
                if inline.startswith("[") and inline.endswith("]"):
                    service_profiles.extend(
                        item.strip().strip("'\"")
                        for item in inline[1:-1].split(",")
                        if item.strip()
                    )
                continue
            if in_profiles:
                profile_item = _COMPOSE_PROFILE_ITEM.match(line)
                if profile_item:
                    service_profiles.append(profile_item.group(1))
                elif line.strip():
                    in_profiles = False
        flush()
    return declared, active


def _compose_build_services(compose_files: Sequence[Path]) -> set[str]:
    """Find services with a real Compose build block in the selected files."""

    result: set[str] = set()
    for compose_file in compose_files:
        try:
            lines = compose_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        service: str | None = None
        for line in lines:
            service_match = _COMPOSE_SERVICE.match(line)
            if service_match:
                service = service_match.group(1)
                continue
            if _COMPOSE_KEY.match(line) and not line.startswith((" ", "\t")):
                service = None
                continue
            if service is not None and re.match(r"^\s{4}build:\s*(.*?)\s*$", line):
                build_value = line.split(":", 1)[1].strip()
                if build_value not in {"null", "!reset null"}:
                    result.add(service)
    return result


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


def _secret_values(values: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(
        value
        for key, value in values.items()
        if _SECRET_FIELD.search(str(key)) and str(value)
    )


def _image_repository(reference: str) -> str:
    value = str(reference).strip().split("@", 1)[0]
    slash = value.rfind("/")
    colon = value.rfind(":")
    return value[:colon] if colon > slash else value


def _inspect_update_image(
    runner: CommandRunner,
    reference: str,
    *,
    redact: Sequence[str] = (),
) -> tuple[str, list[str]]:
    """Return Docker's local image ID and RepoDigests for one image."""

    result = runner.run(
        ["docker", "image", "inspect", "--format", "{{json .}}", reference],
        redact=redact,
    )
    try:
        payload = json.loads(result.stdout)
        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if not isinstance(payload, Mapping):
            raise ValueError
        image_id = str(payload.get("Id", payload.get("ID", ""))).strip()
        repo_digests = payload.get("RepoDigests", ())
        if isinstance(repo_digests, str):
            repo_digests = [repo_digests]
        if not image_id or not isinstance(repo_digests, Sequence):
            raise ValueError
        digests = [str(item).strip() for item in repo_digests if str(item).strip()]
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise InvalidInputError("Docker image inspection returned invalid metadata") from exc
    return image_id, digests


def _saved_update_state(root: Path) -> Mapping[str, object]:
    state_path = root / ".state" / "installer" / "state.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _saved_update_gpu_mode(
    root: Path,
    values: dict[str, str],
    saved_state: Mapping[str, object] | None = None,
) -> dict[str, str]:
    state = saved_state if saved_state is not None else _saved_update_state(root)
    saved_mode = str(state.get("gpu_mode", "")).strip().lower()
    if saved_mode not in {"none", "nvidia", "vaapi"}:
        saved_mode = str(state.get("resolved_gpu_mode", "")).strip().lower()
    requested = str(values.get("GPU_MODE", "")).strip().lower()
    if requested in {"", "auto"} and saved_mode in {"none", "nvidia", "vaapi"}:
        values["GPU_RESOLVED_MODE"] = saved_mode
        if not requested:
            values["GPU_MODE"] = saved_mode
    return values


def _update_manifest(
    root: Path,
    args: argparse.Namespace | None = None,
    *,
    dry_run: bool = False,
    runner: CommandRunner | None = None,
) -> UpdateManifest:
    values = _read_update_env(root / ".env")
    saved_state = _saved_update_state(root)
    values = _saved_update_gpu_mode(root, values, saved_state)
    profiles = _active_update_profiles(
        values,
        args,
        saved_profiles=(
            tuple(str(profile).strip() for profile in saved_state.get("profiles", ()))
            if isinstance(saved_state.get("profiles", ()), Sequence)
            and not isinstance(saved_state.get("profiles", ()), (str, bytes, bytearray))
            else ()
        ),
    )
    gpu_mode = _update_gpu_mode(values, args)
    if gpu_mode == "auto":
        gpu_mode = _gpu_overlay_mode(gpu_mode, values)
    # The manifest is the source of truth for every later update/rollback
    # command.  Store the concrete mode so a lifecycle callback cannot fall
    # back to Compose's no-overlay interpretation of ``auto``.
    values["GPU_MODE"] = gpu_mode
    compose_files = _known_compose_files(root, values, args)
    image_refs, _declared_profiles = _compose_metadata(compose_files, values, profiles)
    declared_services, active_services = _compose_service_activity(compose_files, profiles)
    build_services = _compose_build_services(compose_files)
    configured_image_refs = _env_json_map(values, ("LUMEN_IMAGE_REFS", "IMAGE_REFS"))
    configured_image_refs.update(_env_service_values(values, ("_IMAGE_REF", "_IMAGE")))
    image_refs.update(
        {
            service: reference
            for service, reference in configured_image_refs.items()
            if service not in declared_services or service in active_services
        }
    )

    repo_digests = _env_json_map(values, ("LUMEN_REPO_DIGESTS", "REPO_DIGESTS"))
    repo_digests.update(_env_service_values(values, ("_REPO_DIGEST", "_IMAGE_DIGEST")))
    local_image_ids = _env_json_map(values, ("LUMEN_LOCAL_IMAGE_IDS", "LOCAL_IMAGE_IDS"))
    local_image_ids.update(_env_service_values(values, ("_LOCAL_IMAGE_ID", "_IMAGE_ID")))
    repo_digests = {
        service: digest
        for service, digest in repo_digests.items()
        if service not in declared_services or service in active_services
    }
    local_image_ids = {
        service: image_id
        for service, image_id in local_image_ids.items()
        if service not in declared_services or service in active_services
    }
    if not dry_run:
        invalid_local_services = set(local_image_ids) - build_services
        if invalid_local_services:
            raise InvalidInputError(
                "local image metadata is only valid for Compose build services"
            )
        try:
            for service, reference in image_refs.items():
                _validate_compose_name(service, kind="service")
                _validate_image_reference(reference)
            for service, digest in repo_digests.items():
                _validate_compose_name(service, kind="digest service")
                str(digest)
            for service, image_id in local_image_ids.items():
                _validate_compose_name(service, kind="local image service")
                _validate_image_id(image_id)
        except ValueError as exc:
            raise InvalidInputError("update manifest metadata is invalid") from exc
    for service, reference in image_refs.items():
        if "@" in reference and service not in repo_digests:
            repo_digests[service] = reference.rsplit("@", 1)[1]

    overlay_mode = gpu_mode
    gpu_environment: dict[str, str] = {}
    if overlay_mode == "vaapi":
        for key, placeholder in (("RENDER_GID", "65534"), ("VIDEO_GID", "65533")):
            value = str(values.get(key, "")).strip()
            if value.isdigit():
                gpu_environment[key] = value
            elif dry_run:
                # Planning metadata must render without touching the host or
                # probing /dev/dri.  These values are disposable and never
                # become activation state.
                gpu_environment[key] = placeholder

    if not dry_run and image_refs:
        for service, configured_digest in repo_digests.items():
            if service not in image_refs:
                continue
            try:
                configured_repository = _digest_repository(configured_digest)
                if configured_repository is not None and configured_repository != _image_repository(
                    image_refs[service]
                ):
                    raise InvalidInputError(
                        "configured image digest repository does not match image reference"
                    )
                _normalize_repo_digest(configured_digest)
            except InvalidInputError:
                raise
            except ValueError as exc:
                raise InvalidInputError("configured image digest is invalid") from exc
        image_runner = runner if runner is not None else CommandRunner()
        redact = _secret_values(values)
        for service, reference in image_refs.items():
            image_id, inspected_digests = _inspect_update_image(
                image_runner, reference, redact=redact
            )
            repository = _image_repository(reference)
            matching = next(
                (
                    digest
                    for digest in inspected_digests
                    if "@" in digest and _image_repository(digest) == repository
                ),
                None,
            )
            if matching is not None:
                inspected_digest = matching.rsplit("@", 1)[1]
                try:
                    normalized_inspected = _normalize_repo_digest(inspected_digest)
                    configured_digest = repo_digests.get(service)
                    if configured_digest is not None:
                        normalized_configured = _normalize_repo_digest(configured_digest)
                        if normalized_configured != normalized_inspected:
                            raise InvalidInputError(
                                "configured image digest does not match Docker inspection"
                            )
                except ValueError as exc:
                    raise InvalidInputError(
                        "Docker image inspection returned an invalid repository digest"
                    ) from exc
                repo_digests[service] = normalized_inspected
            elif service in repo_digests:
                raise InvalidInputError(
                    "Docker image inspection did not contain the configured repository digest"
                )
            if service in build_services:
                configured_local_id = local_image_ids.get(service)
                if configured_local_id is not None and configured_local_id != image_id:
                    raise InvalidInputError(
                        "configured local image id does not match Docker inspection"
                    )
                local_image_ids[service] = image_id

    # A normal update must have an immutable source for every service.  A
    # local image ID is sufficient for a build service; registry-backed
    # services require a matching RepoDigest, even when their configured tag
    # happens to be ``latest``.
    if not dry_run:
        missing = [
            service
            for service in image_refs
            if service not in local_image_ids and service not in repo_digests
        ]
        if missing:
            raise InvalidInputError("Docker image metadata did not contain immutable digests")

    try:
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
            gpu_environment=gpu_environment,
            allow_unverified_local_ids=dry_run,
        )
    except ValueError as exc:
        raise InvalidInputError("update manifest is invalid") from exc


def _update_compose_options(manifest: UpdateManifest, args: argparse.Namespace) -> ComposeOptions:
    gpu = manifest.gpu_mode
    if type(gpu) is bool:
        gpu = "nvidia" if gpu else "none"
    if gpu == "auto":
        env_path = Path(manifest.env_path)
        values = _read_update_env(env_path)
        values = _saved_update_gpu_mode(env_path.parent, values)
        try:
            gpu = _gpu_overlay_mode(gpu, values)
        except InvalidInputError:
            compose_names = {Path(path).name for path in manifest.compose_files}
            if "docker-compose.vaapi.yml" in compose_names:
                gpu = "vaapi"
            elif "docker-compose.gpu.yml" in compose_names:
                gpu = "nvidia"
            else:
                raise
    dev = bool(getattr(args, "dev", False)) or any(
        Path(path).name == "docker-compose.dev.yml" for path in manifest.compose_files
    )
    return ComposeOptions(profiles=tuple(manifest.profiles), gpu=gpu, dev=dev)


def _update_callbacks(
    root: Path,
    manifest: UpdateManifest,
    args: argparse.Namespace,
    runner: CommandRunner,
) -> tuple[Callable[..., object], Callable[..., object], Callable[..., object]]:
    """Build the update's injectable tag, pull, and recreate callbacks."""

    env_path = Path(manifest.env_path)
    options = _update_compose_options(manifest, args)
    values = _read_update_env(env_path)
    redact = _secret_values(values)
    config_payload: dict[str, Any] | None = None

    def config_payload_once() -> dict[str, Any]:
        nonlocal config_payload
        if config_payload is None:
            config_payload = compose_config(
                runner, root, env_path, options, redact=redact
            )
        return config_payload

    def tag_local_images(run_id: str) -> dict[str, str]:
        build_services = _compose_build_services(
            [Path(path) for path in manifest.compose_files]
        )
        # A persisted local ID is authoritative for built services discovered
        # during manifest creation.  Keep service ordering deterministic.
        services = set(manifest.local_image_ids)
        services.update(build_services.intersection(manifest.image_refs))
        tags: dict[str, str] = {}
        for service in sorted(services):
            source = manifest.image_refs.get(service) or manifest.local_image_ids.get(service)
            if not source:
                raise PartialError("a built service has no local image to preserve")
            tag = f"lumen-rollback/{service}:{run_id}"
            runner.run(["docker", "image", "tag", source, tag], redact=redact)
            tags[service] = tag
        return tags

    def pull_images(_run_id: str) -> None:
        payload = config_payload_once()
        services = derive_pull_services(payload)
        if services:
            compose_pull(runner, root, env_path, options, services, redact=redact)

    def recreate_stack(_run_id: str) -> None:
        payload = config_payload_once()
        build_services = derive_build_services(payload)
        if build_services:
            compose_build(
                runner, root, env_path, options, build_services, redact=redact
            )
        compose_up(
            runner,
            root,
            env_path,
            options,
            force_recreate=True,
            redact=redact,
        )
        wait_for_health()

    return tag_local_images, pull_images, recreate_stack


def _rollback_callbacks(
    root: Path,
    manifest: UpdateManifest,
    args: argparse.Namespace,
    runner: CommandRunner,
) -> tuple[Callable[..., object], Callable[..., object]]:
    """Build stop/start seams for a recorded rollback run."""

    env_path = Path(manifest.env_path)
    options = _update_compose_options(manifest, args)
    values = _read_update_env(env_path)
    redact = _secret_values(values)
    services = tuple(
        dict.fromkeys((*manifest.image_refs, *manifest.local_image_ids))
    )

    def stop_affected(_run_id: str) -> None:
        if services:
            run_compose(
                runner,
                root,
                env_path,
                options,
                "stop",
                *services,
                redact=redact,
            )

    def start_with_override(run_id: str) -> None:
        override = root / ".state" / "installer" / "rollback" / f"{run_id}.yml"
        argv = options.global_argv(root, env_path) + (
            "-f",
            str(override),
            "up",
            "-d",
            "--force-recreate",
            *services,
        )
        runner.run(argv, redact=redact)
        wait_for_health()

    return stop_affected, start_with_override


def _update(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    confirm = bool(getattr(args, "confirm", False))
    dry_run = bool(getattr(args, "dry_run", False))
    rollback_id = getattr(args, "rollback", None)
    if rollback_id is None and not dry_run and not confirm:
        # Refuse before manifest discovery or Docker inspection.  Besides
        # avoiding work for an unapproved mutation, this keeps the public
        # command on the typed installer error boundary.
        raise InvalidInputError("update requires confirmation")
    safe_rollback_id: str | None = None
    if rollback_id is not None:
        try:
            safe_rollback_id = _safe_run_id(str(rollback_id))
        except (TypeError, ValueError) as exc:
            raise InvalidInputError("invalid rollback run id") from exc
    if rollback_id is not None and dry_run:
        result: dict[str, object] = {
            "action": "rollback",
            "dry_run": True,
            "run_id": safe_rollback_id,
        }
    elif rollback_id is not None:
        runner = CommandRunner()
        try:
            result = run_rollback(
                root,
                safe_rollback_id,
                confirm=confirm,
                callback_factory=lambda rollback_manifest: _rollback_callbacks(
                    root, rollback_manifest, args, runner
                ),
            )
        except (CommandExecutionError, OSError) as error:
            raise PartialError("stack rollback lifecycle failed") from error
    else:
        runner = CommandRunner()
        try:
            manifest = _update_manifest(root, args, dry_run=dry_run, runner=runner)
        except InstallerError:
            raise
        except OSError as error:
            raise PartialError(
                "update manifest preparation failed; no stack changes were made"
            ) from error
        tag_callback = pull_callback = recreate_callback = None
        if not dry_run:
            tag_callback, pull_callback, recreate_callback = _update_callbacks(
                root, manifest, args, runner
            )
        result = run_update(
            root,
            manifest,
            dry_run=dry_run,
            confirm=confirm,
            tag_callback=tag_callback,
            pull_callback=pull_callback,
            recreate_callback=recreate_callback,
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
