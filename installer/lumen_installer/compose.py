"""Safe Docker Compose command construction for the Linux installer.

Compose is deliberately treated as an argument-vector API.  This keeps
paths, profiles, and optional overlays out of a shell, and gives lifecycle
callers one place to preserve the ordering required by Compose's global
options.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .commands import CommandResult, CommandRunner, LONG_COMMAND_TIMEOUT, normalize_stream
from .errors import InvalidInputError
from .state import KNOWN_GPU_MODES, KNOWN_PROFILES
from .storage import normalize_storage_mode


def _path(value: str | Path, *, name: str) -> str:
    if not isinstance(value, (str, Path)):
        raise InvalidInputError(f"{name} must be a path")
    text = str(value)
    if not text or "\x00" in text:
        raise InvalidInputError(f"{name} is invalid")
    return text


def _profiles(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray)):
        raise InvalidInputError("profiles must be a sequence of known profile names")
    try:
        values = tuple(value)
    except TypeError as exc:
        raise InvalidInputError("profiles must be a sequence of known profile names") from exc
    result: list[str] = []
    for profile in values:
        if not isinstance(profile, str) or profile not in KNOWN_PROFILES:
            raise InvalidInputError(f"unknown Compose profile: {profile!r}")
        if profile in result:
            raise InvalidInputError(f"duplicate Compose profile: {profile}")
        result.append(profile)
    return tuple(result)


def _gpu(value: Any) -> bool | None:
    if value is None:
        return None
    if type(value) is bool:
        # ``--gpu`` from the original Linux installer was a boolean NVIDIA
        # switch.  Keep that input compatible while allowing the explicit
        # mode names owned by the GPU phase.
        return "nvidia" if value else "none"
    if isinstance(value, str) and value.strip().lower() in KNOWN_GPU_MODES:
        return value.strip().lower()
    raise InvalidInputError("gpu must be a boolean or a known GPU mode")


def _compose_files(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray)):
        raise InvalidInputError("compose files must be a sequence of paths")
    try:
        values = tuple(value)
    except TypeError as exc:
        raise InvalidInputError("compose files must be a sequence of paths") from exc
    return tuple(_path(item, name="Compose file") for item in values)


@dataclass(frozen=True)
class ComposeOptions:
    """Compose overlays and profiles selected for one lifecycle operation.

    ``None`` means "use the saved installer choice" for profiles/GPU.  The
    concrete command builder accepts saved defaults explicitly, avoiding a
    hidden read of state and making dry-run output deterministic.
    """

    profiles: tuple[str, ...] | Sequence[str] | None = None
    gpu: bool | str | None = None
    dev: bool = False
    compose_files: tuple[str | Path, ...] | Sequence[str | Path] | None = None
    storage_mode: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "profiles", _profiles(self.profiles))
        object.__setattr__(self, "gpu", _gpu(self.gpu))
        object.__setattr__(self, "compose_files", _compose_files(self.compose_files))
        if self.storage_mode is not None:
            object.__setattr__(self, "storage_mode", normalize_storage_mode(self.storage_mode))
        if type(self.dev) is not bool:
            raise InvalidInputError("dev must be a boolean")

    @property
    def selected_profiles(self) -> tuple[str, ...]:
        return tuple(self.profiles or ())

    @property
    def gpu_enabled(self) -> bool:
        return self.gpu_mode in {"nvidia", "vaapi"}

    @property
    def gpu_mode(self) -> str:
        """Return the normalized requested/selected GPU mode."""

        return self.gpu or "none"

    def resolved(
        self,
        *,
        saved_profiles: Sequence[str] = (),
        saved_gpu: bool | str = "none",
        saved_dev: bool = False,
        saved_storage_mode: str = "shared",
    ) -> "ComposeOptions":
        profiles = self.profiles if self.profiles is not None else tuple(saved_profiles)
        gpu = self.gpu if self.gpu is not None else saved_gpu
        dev = self.dev if self.dev is not False else bool(saved_dev)
        storage_mode = (
            self.storage_mode
            if self.storage_mode is not None
            else normalize_storage_mode(saved_storage_mode)
        )
        # ``dev`` is not currently persisted, so callers normally leave the
        # saved value false.  This method still supports a future state field.
        return ComposeOptions(
            profiles=profiles,
            gpu=gpu,
            dev=dev,
            compose_files=self.compose_files,
            storage_mode=storage_mode,
        )

    @classmethod
    def from_state(
        cls,
        state: Any,
        *,
        profiles: Sequence[str] | None = None,
        gpu: bool | str | None = None,
        dev: bool = False,
        storage_mode: str | None = None,
    ) -> "ComposeOptions":
        """Resolve persisted profiles/GPU while honoring explicit overrides."""

        requested = cls(profiles=profiles, gpu=gpu, dev=dev, storage_mode=storage_mode)
        return requested.resolved(
            saved_profiles=getattr(state, "profiles", ()),
            saved_gpu=getattr(state, "gpu_mode", False),
            saved_storage_mode=getattr(state, "storage_mode", "shared"),
        )

    def global_argv(self, repo_root: str | Path, env_file: str | Path) -> tuple[str, ...]:
        root = _path(repo_root, name="repository root")
        env = _path(env_file, name="environment file")
        argv: list[str] = ["docker", "compose", "--env-file", env]
        if self.compose_files is not None:
            for compose_file in self.compose_files:
                candidate = Path(compose_file)
                if not candidate.is_absolute():
                    candidate = Path(root) / candidate
                argv.extend(("-f", str(candidate)))
        else:
            argv.extend(("-f", str(Path(root) / "docker-compose.yml")))
            override = Path(root) / "docker-compose.override.yml"
            if override.is_file():
                argv.extend(("-f", str(override)))
            overlay = {
                "nvidia": "docker-compose.gpu.yml",
                "vaapi": "docker-compose.vaapi.yml",
            }.get(self.gpu_mode)
            if overlay is not None:
                argv.extend(("-f", str(Path(root) / overlay)))
            if self.storage_mode == "separate":
                argv.extend(("-f", str(Path(root) / "docker-compose.separate.yml")))
            if self.dev:
                argv.extend(("-f", str(Path(root) / "docker-compose.dev.yml")))
        for profile in self.selected_profiles:
            argv.extend(("--profile", profile))
        return tuple(argv)

    def argv(
        self,
        repo_root: str | Path,
        env_file: str | Path,
        *command: str,
    ) -> tuple[str, ...]:
        if not command or any(not isinstance(item, str) or not item for item in command):
            raise InvalidInputError("a Compose command is required")
        return self.global_argv(repo_root, env_file) + tuple(command)

    command = argv
    build_argv = argv


def compose_argv(
    repo_root: str | Path,
    env_file: str | Path,
    options: ComposeOptions,
    *command: str,
) -> tuple[str, ...]:
    """Build one complete Compose argv vector."""

    if not isinstance(options, ComposeOptions):
        raise InvalidInputError("Compose options are required")
    return options.argv(repo_root, env_file, *command)


def _default_compose_files(
    repo_root: str | Path,
    env_file: str | Path,
    options: ComposeOptions,
) -> list[Path]:
    """Resolve the default Compose file list when no explicit ``-f`` list is
    supplied by the caller.

    Order: base, local override if present, GPU overlay if applicable,
    development overlay if applicable. The local override is inserted before
    the development overlay so the development overlay's intentional port
    replacement remains authoritative.
    """

    root = _path(repo_root, name="repository root")
    files: list[Path] = [Path(root) / "docker-compose.yml"]
    override = Path(root) / "docker-compose.override.yml"
    if override.is_file():
        files.append(override)
    if options.gpu_mode not in {"none", False, None}:
        overlay_name = {
            "nvidia": "docker-compose.gpu.yml",
            "vaapi": "docker-compose.vaapi.yml",
        }.get(options.gpu_mode)
        if overlay_name is not None:
            files.append(Path(root) / overlay_name)
    if options.storage_mode == "separate":
        files.append(Path(root) / "docker-compose.separate.yml")
    if options.dev:
        files.append(Path(root) / "docker-compose.dev.yml")
    return files


def _config_services(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, (str, bytes, bytearray)):
        try:
            payload = json.loads(normalize_stream(payload, name="Compose config"))
        except (TypeError, ValueError) as exc:
            raise InvalidInputError("docker compose config returned invalid JSON") from exc
    if not isinstance(payload, Mapping) or not isinstance(payload.get("services"), Mapping):
        raise InvalidInputError("docker compose config did not contain services")
    return payload["services"]


def derive_pull_services(payload: Any) -> tuple[str, ...]:
    """Return enabled service names with an image and no active build block."""

    services = _config_services(payload)
    selected: list[str] = []
    for name, service in services.items():
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(service, Mapping):
            continue
        # docker-compose.dev.yml sets dashboard's build to null; that is an
        # image-backed dev service and must remain pullable.  A real mapping
        # (including an empty mapping from a fake config) is a build service.
        if service.get("build") is not None:
            continue
        if service.get("image") is not None:
            selected.append(name)
    if not selected:
        raise InvalidInputError("Compose config contains no enabled non-build services to pull")
    return tuple(selected)


def derive_build_services(payload: Any) -> tuple[str, ...]:
    """Return enabled local-build service names in Compose config order."""

    services = _config_services(payload)
    result = []
    for name, service in services.items():
        if isinstance(name, str) and isinstance(service, Mapping) and service.get("build") is not None:
            result.append(name)
    return tuple(result)


def run_compose(
    runner: CommandRunner,
    repo_root: str | Path,
    env_file: str | Path,
    options: ComposeOptions,
    *command: str,
    redact: Sequence[Any] = (),
    timeout: float | None = None,
) -> CommandResult:
    """Execute one safe Compose command through the injected runner."""

    argv = options.argv(repo_root, env_file, *command)
    kwargs: dict[str, Any] = {}
    if redact:
        kwargs["redact"] = redact
    if timeout is not None:
        try:
            parameters = tuple(inspect.signature(runner.run).parameters.values())
        except (TypeError, ValueError):
            parameters = ()
        if "timeout" in {parameter.name for parameter in parameters} or any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters
        ):
            kwargs["timeout"] = timeout
    return runner.run(argv, **kwargs)


def config(
    runner: CommandRunner,
    repo_root: str | Path,
    env_file: str | Path,
    options: ComposeOptions,
    *,
    redact: Sequence[Any] = (),
) -> dict[str, Any]:
    result = run_compose(runner, repo_root, env_file, options, "config", "--format", "json", redact=redact)
    try:
        value = json.loads(result.stdout)
    except (TypeError, ValueError) as exc:
        raise InvalidInputError("docker compose config returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise InvalidInputError("docker compose config returned an invalid document")
    return value


def validate_storage_mounts(
    payload: Mapping[str, Any],
    *,
    root_path: str | Path,
    downloads_path: str | Path,
    storage_mode: str,
) -> None:
    """Require the role-specific expanded view used by separate storage.

    The host mount root is intentionally not a container-wide writable mount:
    writers get staging plus the library child, while readers/backend get only
    the library child read-only.  Config/state mounts are outside this check.
    """

    if storage_mode != "separate":
        return
    root = Path(root_path)
    media = root / "media"
    downloads = Path(downloads_path)
    services = payload.get("services") if isinstance(payload, Mapping) else None
    if not isinstance(services, Mapping):
        raise InvalidInputError("Compose storage view is invalid")

    expected_by_service: dict[str, dict[str, tuple[Path, bool]]] = {
        "qbittorrent": {"/downloads": (downloads, False)},
        "sonarr": {
            "/data/media": (media, False),
            "/downloads": (downloads, False),
        },
        "radarr": {
            "/data/media": (media, False),
            "/downloads": (downloads, False),
        },
        "bazarr": {
            "/data/media": (media, False),
        },
        "unpackerr": {
            "/data/media": (media, False),
            "/downloads": (downloads, False),
        },
        "jellyfin": {"/data/media": (media, True)},
        "homepage-actions": {
            "/data/media": (media, True),
            "/downloads": (downloads, True),
        },
    }
    required_services = {"qbittorrent", "sonarr", "radarr"}
    missing = required_services.difference(services)
    if missing:
        raise InvalidInputError(
            "Compose storage view is missing required services: "
            + ", ".join(sorted(missing))
        )
    for service, definition in services.items():
        volumes = definition.get("volumes") if isinstance(definition, Mapping) else None
        if not isinstance(volumes, Sequence) or isinstance(
            volumes, (str, bytes, bytearray)
        ):
            continue
        expected = expected_by_service.get(service, {})
        for volume in volumes:
            if isinstance(volume, Mapping):
                source = volume.get("source")
                target = volume.get("target")
            elif isinstance(volume, str):
                parts = volume.split(":")
                source, target = (parts[0], parts[1]) if len(parts) >= 2 else (None, None)
            else:
                continue
            if not isinstance(source, str) or not isinstance(target, str):
                continue
            source_path = Path(source)
            if source_path == root:
                raise InvalidInputError(
                    f"Compose storage root is exposed for {service}"
                )
            if target == "/data":
                raise InvalidInputError(
                    f"Compose storage mount /data is too broad for {service}"
                )
            storage_source = (
                root in source_path.parents
                or source_path == downloads
                or downloads in source_path.parents
            )
            allowed = expected.get(target)
            if storage_source and (allowed is None or source_path != allowed[0]):
                raise InvalidInputError(
                    f"Compose storage mount {target} is unexpected for {service}"
                )
    for service in tuple(expected_by_service):
        if service not in services:
            continue
        expected = expected_by_service[service]
        definition = services.get(service)
        volumes = definition.get("volumes") if isinstance(definition, Mapping) else None
        if not isinstance(volumes, Sequence) or isinstance(volumes, (str, bytes, bytearray)):
            raise InvalidInputError(f"Compose storage mounts are missing for {service}")
        mounts: dict[str, tuple[str, bool]] = {}
        for volume in volumes:
            if isinstance(volume, Mapping):
                source = volume.get("source")
                target = volume.get("target")
                read_only = bool(volume.get("read_only", False))
            elif isinstance(volume, str):
                parts = volume.split(":")
                if len(parts) < 2:
                    continue
                source, target = parts[0], parts[1]
                read_only = len(parts) > 2 and "ro" in parts[2].split(",")
            else:
                continue
            if isinstance(source, str) and isinstance(target, str):
                mounts[target] = (source, read_only)
        if any(Path(source) == root for source, _read_only in mounts.values()):
            raise InvalidInputError(f"Compose storage root is exposed for {service}")
        if "/data" in mounts:
            raise InvalidInputError(f"Compose storage mount /data is too broad for {service}")
        for target, (source, _read_only) in mounts.items():
            if Path(source) in {media, downloads} and target not in expected:
                raise InvalidInputError(
                    f"Compose storage mount {target} is unexpected for {service}"
                )
        for target, (source, read_only) in expected.items():
            actual = mounts.get(target)
            if actual is None or Path(actual[0]) != source:
                raise InvalidInputError(f"Compose storage mount {target} is incorrect for {service}")
            if actual[1] != read_only:
                access = "read-only" if read_only else "writable"
                raise InvalidInputError(
                    f"Compose storage mount {target} must be {access} for {service}"
                )


def pull(
    runner: CommandRunner,
    repo_root: str | Path,
    env_file: str | Path,
    options: ComposeOptions,
    services: Sequence[str],
    *,
    redact: Sequence[Any] = (),
) -> CommandResult:
    names = tuple(services)
    if not names or any(not isinstance(item, str) or not item for item in names):
        raise InvalidInputError("Compose pull requires service names")
    return run_compose(runner, repo_root, env_file, options, "pull", *names, redact=redact, timeout=LONG_COMMAND_TIMEOUT)


def build(
    runner: CommandRunner,
    repo_root: str | Path,
    env_file: str | Path,
    options: ComposeOptions,
    services: Sequence[str] = ("dashboard",),
    *,
    redact: Sequence[Any] = (),
) -> CommandResult:
    names = tuple(services)
    if not names or any(not isinstance(item, str) or not item for item in names):
        raise InvalidInputError("Compose build requires service names")
    return run_compose(runner, repo_root, env_file, options, "build", *names, redact=redact, timeout=LONG_COMMAND_TIMEOUT)


def up(
    runner: CommandRunner,
    repo_root: str | Path,
    env_file: str | Path,
    options: ComposeOptions,
    *,
    force_recreate: bool = False,
    build_images: bool = False,
    services: Sequence[str] = (),
    redact: Sequence[Any] = (),
) -> CommandResult:
    command: list[str] = ["up", "-d"]
    if build_images:
        command.append("--build")
    if force_recreate:
        command.append("--force-recreate")
    command.extend(tuple(services))
    return run_compose(runner, repo_root, env_file, options, *command, redact=redact, timeout=LONG_COMMAND_TIMEOUT)


def down(
    runner: CommandRunner,
    repo_root: str | Path,
    env_file: str | Path,
    options: ComposeOptions,
    *,
    redact: Sequence[Any] = (),
) -> CommandResult:
    return run_compose(runner, repo_root, env_file, options, "down", redact=redact)


def redeploy_dashboard(
    runner: CommandRunner,
    repo_root: str | Path,
    env_file: str | Path,
    options: ComposeOptions,
    *,
    redact: Sequence[Any] = (),
) -> CommandResult:
    # Compose's --build and --force-recreate are scoped to the named service;
    # no other stack service is rebuilt or recreated.
    return up(runner, repo_root, env_file, options, force_recreate=True, build_images=True, services=("dashboard",), redact=redact)


# Descriptive aliases retained for callers that prefer an explicit command
# naming style over the short lifecycle verbs.
build_compose_argv = compose_argv
build_compose_command = compose_argv
compose_config = config
compose_pull = pull
compose_build = build
compose_up = up
compose_down = down
compose_redeploy_dashboard = redeploy_dashboard


__all__ = [
    "ComposeOptions",
    "build",
    "compose_argv",
    "config",
    "build_compose_argv",
    "build_compose_command",
    "compose_build",
    "compose_config",
    "compose_down",
    "compose_pull",
    "compose_redeploy_dashboard",
    "compose_up",
    "derive_build_services",
    "derive_pull_services",
    "down",
    "pull",
    "redeploy_dashboard",
    "run_compose",
    "validate_storage_mounts",
    "up",
]
