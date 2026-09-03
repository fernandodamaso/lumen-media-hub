"""Safe Docker Compose command construction for the Linux installer.

Compose is deliberately treated as an argument-vector API.  This keeps
paths, profiles, and optional overlays out of a shell, and gives lifecycle
callers one place to preserve the ordering required by Compose's global
options.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .commands import CommandResult, CommandRunner, normalize_stream
from .errors import InvalidInputError
from .state import KNOWN_GPU_MODES, KNOWN_PROFILES


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "profiles", _profiles(self.profiles))
        object.__setattr__(self, "gpu", _gpu(self.gpu))
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
    ) -> "ComposeOptions":
        profiles = self.profiles if self.profiles is not None else tuple(saved_profiles)
        gpu = self.gpu if self.gpu is not None else saved_gpu
        dev = self.dev if self.dev is not False else bool(saved_dev)
        # ``dev`` is not currently persisted, so callers normally leave the
        # saved value false.  This method still supports a future state field.
        return ComposeOptions(profiles=profiles, gpu=gpu, dev=dev)

    @classmethod
    def from_state(
        cls,
        state: Any,
        *,
        profiles: Sequence[str] | None = None,
        gpu: bool | str | None = None,
        dev: bool = False,
    ) -> "ComposeOptions":
        """Resolve persisted profiles/GPU while honoring explicit overrides."""

        requested = cls(profiles=profiles, gpu=gpu, dev=dev)
        return requested.resolved(
            saved_profiles=getattr(state, "profiles", ()),
            saved_gpu=getattr(state, "gpu_mode", False),
        )

    def global_argv(self, repo_root: str | Path, env_file: str | Path) -> tuple[str, ...]:
        root = _path(repo_root, name="repository root")
        env = _path(env_file, name="environment file")
        argv: list[str] = ["docker", "compose", "--env-file", env, "-f", str(Path(root) / "docker-compose.yml")]
        overlay = {
            "nvidia": "docker-compose.gpu.yml",
            "vaapi": "docker-compose.vaapi.yml",
        }.get(self.gpu_mode)
        if overlay is not None:
            argv.extend(("-f", str(Path(root) / overlay)))
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
) -> CommandResult:
    """Execute one safe Compose command through the injected runner."""

    argv = options.argv(repo_root, env_file, *command)
    if redact:
        return runner.run(argv, redact=redact)
    return runner.run(argv)


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
    return run_compose(runner, repo_root, env_file, options, "pull", *names, redact=redact)


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
    return run_compose(runner, repo_root, env_file, options, "build", *names, redact=redact)


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
    return run_compose(runner, repo_root, env_file, options, *command, redact=redact)


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
    "up",
]
