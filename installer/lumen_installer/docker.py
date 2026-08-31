"""Docker/Compose preflight and dependency policy for the Linux installer."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .commands import CommandExecutionError, CommandRunner, normalize_stream, redact_text
from .errors import (
    InvalidInputError,
    PreflightError,
    UnsupportedDistroError,
    UnsupportedPlatformError,
)
from .platform import HostFacts, detect_host


Version = tuple[int, int, int]
COMPOSE_MINIMUM: Version = (2, 24, 4)
_VERSION_TOKEN = r"v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?"
_SHORT_VERSION = re.compile(rf"^\s*{_VERSION_TOKEN}\s*$", re.IGNORECASE)
_DOCKER_VERSION_LABEL = re.compile(
    rf"^\s*Docker(?: Engine)?\s+version\s+{_VERSION_TOKEN}(?:\s*,[^\r\n]*)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_COMPOSE_VERSION_LABEL = re.compile(
    rf"^\s*Docker[- ]Compose\s+version\s+{_VERSION_TOKEN}\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_OFFLINE_MARKERS = (
    "network",
    "offline",
    "timeout",
    "timed out",
    "connection",
    "resolve",
    "no such host",
    "temporary failure",
    "i/o timeout",
    "not found",
)


def _version_from(value: Any) -> Version | None:
    if value is None:
        return None
    if isinstance(value, tuple) or isinstance(value, list):
        if len(value) != 3:
            return None
        try:
            return tuple(int(part) for part in value)  # type: ignore[return-value]
        except (TypeError, ValueError):
            return None
    match = _SHORT_VERSION.fullmatch(str(value))
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def parse_docker_version(output: Any) -> Version | None:
    """Parse Docker's short, long, client, or server version output."""

    text = normalize_stream(output, name="Docker version output", strict=False)
    short_match = _SHORT_VERSION.fullmatch(text)
    if short_match is not None:
        return tuple(int(part) for part in short_match.groups())  # type: ignore[return-value]

    label_match = _DOCKER_VERSION_LABEL.search(text)
    if label_match is not None:
        return tuple(int(part) for part in label_match.groups())  # type: ignore[return-value]

    # Full ``docker version`` output contains nested containerd and runc
    # versions after the Engine version.  Prefer the first Version field in
    # the Server section so those runtime versions cannot be mistaken for the
    # Docker Engine version.
    server_index = text.lower().find("server:")
    if server_index >= 0:
        server_match = re.search(
            rf"^\s*Version:\s*{_VERSION_TOKEN}",
            text[server_index:],
            re.IGNORECASE | re.MULTILINE,
        )
        if server_match is not None:
            return tuple(int(part) for part in server_match.groups())  # type: ignore[return-value]

    # Client-only long output still has a recognized Client section and a
    # Version field.  Do not accept arbitrary semver-looking diagnostics.
    if text.lstrip().lower().startswith("client:"):
        client_match = re.search(
            rf"^\s*Version:\s*{_VERSION_TOKEN}",
            text,
            re.IGNORECASE | re.MULTILINE,
        )
        if client_match is not None:
            return tuple(int(part) for part in client_match.groups())  # type: ignore[return-value]
    return None


def parse_compose_version(output: Any) -> Version | None:
    """Parse Compose v2 output, including desktop suffixes."""

    text = normalize_stream(output, name="Compose version output", strict=False)
    short_match = _SHORT_VERSION.fullmatch(text)
    if short_match is not None:
        return tuple(int(part) for part in short_match.groups())  # type: ignore[return-value]
    label_match = _COMPOSE_VERSION_LABEL.search(text)
    if label_match is None:
        return None
    return tuple(int(part) for part in label_match.groups())  # type: ignore[return-value]


def validate_compose_version(version: Any) -> bool:
    """Require the inclusive Compose feature floor used by this repository."""

    parsed = (
        _version_from(version)
        if isinstance(version, (tuple, list))
        else parse_compose_version(version)
    )
    if parsed is None:
        raise InvalidInputError("could not determine Docker Compose version")
    if parsed < COMPOSE_MINIMUM:
        raise InvalidInputError(
            "Docker Compose 2.24.4 or newer is required "
            f"(found {parsed[0]}.{parsed[1]}.{parsed[2]})"
        )
    return True


@dataclass(frozen=True)
class DecisionRecord:
    """A human decision/checkpoint intentionally not applied by planning."""

    code: str
    reason: str
    action: str = "review"
    severity: str = "warning"

    @property
    def decision(self) -> str:
        return self.action

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "reason": self.reason,
            "action": self.action,
            "severity": self.severity,
        }


class PlannedCommand(tuple[str, ...]):
    """Argument vector with optional stdin data for a non-shell command."""

    def __new__(
        cls,
        argv: tuple[str, ...] | list[str],
        *,
        input_text: str | None = None,
    ) -> "PlannedCommand":
        command = super().__new__(cls, argv)
        command._input_text = input_text  # type: ignore[attr-defined]
        return command

    @property
    def argv(self) -> tuple[str, ...]:
        return tuple(self)

    @property
    def input_text(self) -> str | None:
        return self._input_text  # type: ignore[attr-defined]


@dataclass(frozen=True)
class DependencyPlan:
    """Explicit dependency command vectors and non-automatic decisions."""

    commands: tuple[PlannedCommand, ...] = ()
    decisions: tuple[DecisionRecord, ...] = ()
    supported: bool = True
    status: str = "supported"
    distro: str = ""
    policy: str = ""
    error: PreflightError | None = None
    # Apt deb822 content is represented as a separate input payload rather
    # than shell syntax; lifecycle code may choose to execute it later.
    input_text: str | None = None

    @property
    def argv(self) -> tuple[tuple[str, ...], ...]:
        return self.commands

    @property
    def steps(self) -> tuple[tuple[str, ...], ...]:
        return self.commands

    @property
    def command_inputs(self) -> tuple[str | None, ...]:
        return tuple(getattr(command, "input_text", None) for command in self.commands)

    @property
    def decision_records(self) -> tuple[DecisionRecord, ...]:
        return self.decisions

    @property
    def report(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "supported": self.supported,
            "distro": self.distro,
            "policy": self.policy,
            "commands": [list(command) for command in self.commands],
            "command_inputs": list(self.command_inputs),
            "decisions": [record.as_dict() for record in self.decisions],
            "error": str(self.error) if self.error is not None else None,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report


def _decision_records(*, unsupported: bool = False) -> tuple[DecisionRecord, ...]:
    records = [
        DecisionRecord(
            "sudo-required",
            "Installing distro packages and enabling Docker may require sudo; request it explicitly.",
        ),
        DecisionRecord(
            "conflicting-packages",
            "Existing/conflicting Docker packages must be reviewed before package mutation.",
        ),
        DecisionRecord(
            "docker-group-membership",
            "Adding the invoking user to the docker group requires explicit consent.",
        ),
        DecisionRecord(
            "logout-required",
            "A docker-group change takes effect only after a new login session.",
        ),
    ]
    if unsupported:
        records.insert(
            0,
            DecisionRecord(
                "unsupported-distro",
                "No approved dependency repository policy exists for this Linux distribution.",
                action="stop",
                severity="error",
            ),
        )
    return tuple(records)


def _apt_plan(
    family: str,
    codename: str,
) -> tuple[tuple[PlannedCommand, ...], str]:
    url = f"https://download.docker.com/linux/{family}/gpg"
    repo_url = f"https://download.docker.com/linux/{family}"
    source = (
        "Types: deb\n"
        f"URIs: {repo_url}\n"
        f"Suites: {codename}\n"
        "Components: stable\n"
        "Architectures: amd64 arm64\n"
        "Signed-By: /etc/apt/keyrings/docker.gpg\n"
    )
    commands = (
        PlannedCommand(("sudo", "install", "-m", "0755", "-d", "/etc/apt/keyrings")),
        PlannedCommand(("sudo", "apt-get", "update")),
        PlannedCommand(("sudo", "apt-get", "install", "-y", "ca-certificates", "curl", "gnupg")),
        PlannedCommand(("curl", "-fsSL", url, "--output", "/tmp/lumen-docker.asc")),
        PlannedCommand((
            "sudo",
            "gpg",
            "--dearmor",
            "--yes",
            "--output",
            "/etc/apt/keyrings/docker.gpg",
            "/tmp/lumen-docker.asc",
        )),
        PlannedCommand(("sudo", "chmod", "a+r", "/etc/apt/keyrings/docker.gpg")),
        PlannedCommand(
            ("sudo", "tee", "/etc/apt/sources.list.d/docker.sources"),
            input_text=source,
        ),
        PlannedCommand(("sudo", "apt-get", "update")),
        PlannedCommand((
            "sudo",
            "apt-get",
            "install",
            "-y",
            "docker-ce",
            "docker-ce-cli",
            "containerd.io",
            "docker-buildx-plugin",
            "docker-compose-plugin",
        )),
    )
    return commands, source


def dependency_plan(host: HostFacts) -> DependencyPlan:
    """Return approved package policy without installing or changing packages."""

    distro = str(host.distro_id or "").strip().lower()
    records = _decision_records()
    if distro in {"ubuntu", "debian"}:
        codename = getattr(host, "codename", None)
        if not isinstance(codename, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", codename.strip()):
            codename_record = DecisionRecord(
                "codename-required",
                "A concrete distribution codename is required before configuring Docker's apt repository.",
                action="stop",
                severity="error",
            )
            return DependencyPlan(
                commands=(),
                decisions=records + (codename_record,),
                supported=True,
                status="needs-codename",
                distro=distro,
                policy=f"docker-official-apt-{distro}",
                error=PreflightError("distribution codename is required for the Docker apt repository"),
            )
        commands, source = _apt_plan(distro, codename.strip())
        return DependencyPlan(
            commands=commands,
            decisions=records,
            distro=distro,
            policy=f"docker-official-apt-{distro}",
            input_text=source,
        )
    if distro in {"fedora"}:
        commands = (
            ("sudo", "dnf", "-y", "install", "dnf-plugins-core", "ca-certificates", "curl"),
            (
                "sudo",
                "dnf",
                "config-manager",
                "--add-repo",
                "https://download.docker.com/linux/fedora/docker-ce.repo",
            ),
            (
                "sudo",
                "dnf",
                "-y",
                "install",
                "docker-ce",
                "docker-ce-cli",
                "containerd.io",
                "docker-buildx-plugin",
                "docker-compose-plugin",
            ),
        )
        return DependencyPlan(
            commands=commands,
            decisions=records,
            distro=distro,
            policy="docker-official-dnf-fedora",
        )
    if distro in {"arch", "omarchy"}:
        commands = (
            ("sudo", "pacman", "-S", "--needed", "docker", "docker-compose"),
        )
        return DependencyPlan(
            commands=commands,
            decisions=records,
            distro=distro,
            policy="arch-distro-packages",
        )

    error = UnsupportedPlatformError(
        f"unsupported Linux distribution: {distro or 'unknown'}"
    )
    return DependencyPlan(
        commands=(),
        decisions=_decision_records(unsupported=True),
        supported=False,
        status="unsupported",
        distro=distro,
        policy="unsupported",
        error=error,
    )


@dataclass(frozen=True)
class DockerPreflight:
    """Read-only Docker and Compose capability result."""

    status: str
    docker_version: Version | None = None
    compose_version: Version | None = None
    error: PreflightError | None = None
    decisions: tuple[DecisionRecord, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def supported(self) -> bool:
        return self.ok

    @property
    def report(self) -> dict[str, Any]:
        def version_text(version: Version | None) -> str | None:
            return ".".join(map(str, version)) if version else None

        return {
            "status": self.status,
            "docker_version": version_text(self.docker_version),
            "compose_version": version_text(self.compose_version),
            "compose_minimum": ".".join(map(str, COMPOSE_MINIMUM)),
            "decisions": [record.as_dict() for record in self.decisions],
            "error": str(self.error) if self.error is not None else None,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report


def _failure_text(error: BaseException) -> str:
    if isinstance(error, CommandExecutionError):
        return " ".join(
            str(part)
            for part in (error, error.stderr, error.stdout)
            if part
        ).lower()
    return str(error).lower()


def docker_preflight(runner: CommandRunner | None = None) -> DockerPreflight:
    """Inspect installed Docker/Compose without mutating dependencies."""

    command_runner = runner if runner is not None else CommandRunner()
    try:
        docker_result = command_runner.run(
            ["docker", "version", "--format", "{{.Server.Version}}"]
        )
    except (CommandExecutionError, OSError) as error:
        text = _failure_text(error)
        status = "offline" if any(marker in text for marker in _OFFLINE_MARKERS) else "unavailable"
        return DockerPreflight(
            status=status,
            error=PreflightError("Docker Engine is unavailable or the daemon is offline"),
        )
    docker_version = parse_docker_version(docker_result.stdout)
    if docker_version is None:
        return DockerPreflight(
            status="unknown",
            error=PreflightError("could not determine Docker Engine version"),
        )

    try:
        compose_result = command_runner.run(["docker", "compose", "version", "--short"])
    except (CommandExecutionError, OSError):
        try:
            compose_result = command_runner.run(["docker", "compose", "version"])
        except (CommandExecutionError, OSError) as error:
            text = _failure_text(error)
            status = "offline" if any(marker in text for marker in _OFFLINE_MARKERS) else "unavailable"
            return DockerPreflight(
                status=status,
                docker_version=docker_version,
                error=PreflightError("Docker Compose is unavailable"),
            )
    compose_version = parse_compose_version(compose_result.stdout)
    if compose_version is None:
        return DockerPreflight(
            status="unknown",
            docker_version=docker_version,
            error=PreflightError("could not determine Docker Compose version"),
        )
    if compose_version < COMPOSE_MINIMUM:
        return DockerPreflight(
            status="unsupported",
            docker_version=docker_version,
            compose_version=compose_version,
            error=PreflightError(
                "Docker Compose 2.24.4 or newer is required "
                f"(found {compose_version[0]}.{compose_version[1]}.{compose_version[2]})"
            ),
        )
    return DockerPreflight(
        status="ok",
        docker_version=docker_version,
        compose_version=compose_version,
    )


inspect_docker = docker_preflight
check_docker = docker_preflight


@dataclass(frozen=True)
class ManifestInspection:
    """Non-pulling image manifest architecture result."""

    image: str
    status: str
    architectures: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    error: str | None = None

    @property
    def supported(self) -> bool:
        return self.status == "supported" and bool(self.architectures)

    @property
    def online(self) -> bool:
        return self.status != "offline"

    @property
    def report(self) -> dict[str, Any]:
        return {
            "image": self.image,
            "status": self.status,
            "supported": self.supported,
            "architectures": list(self.architectures),
            "platforms": list(self.platforms),
            "error": self.error,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report


def _platforms_from_payload(payload: Any) -> set[tuple[str, str, str | None]]:
    found: set[tuple[str, str, str | None]] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            platform = value.get("platform")
            if isinstance(platform, Mapping):
                os_name = str(platform.get("os", "")).lower()
                architecture = str(platform.get("architecture", "")).lower()
                variant = platform.get("variant")
                if os_name == "linux" and architecture:
                    found.add((os_name, architecture, str(variant) if variant else None))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return found


def _decode_manifest(stdout: Any) -> Any:
    text = normalize_stream(stdout, name="manifest output", strict=False).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Some Docker builds prefix warnings before the JSON document.  Keep
        # parsing bounded to the first object/array and never execute output.
        starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
        for index in sorted(starts):
            try:
                return json.loads(text[index:])
            except json.JSONDecodeError:
                continue
    return None


def inspect_manifest_architectures(
    image: str,
    *,
    runner: CommandRunner | Any | None = None,
    online: bool | None = None,
) -> ManifestInspection:
    """Inspect registry metadata using ``docker manifest inspect`` only."""

    if not isinstance(image, str) or not image.strip():
        raise InvalidInputError("image name is required for manifest inspection")
    image = image.strip()
    if online is False:
        return ManifestInspection(image=image, status="offline", error="registry inspection is offline")
    command_runner = runner if runner is not None else CommandRunner()
    try:
        result = command_runner.run(["docker", "manifest", "inspect", "--verbose", image])
    except (CommandExecutionError, OSError) as error:
        detail = redact_text(str(error))
        lowered = detail.lower()
        status = "offline" if any(marker in lowered for marker in _OFFLINE_MARKERS) else "unknown"
        return ManifestInspection(image=image, status=status, error=detail)

    payload = _decode_manifest(result.stdout)
    if payload is None:
        return ManifestInspection(image=image, status="unknown", error="manifest output was not valid JSON")
    platform_values = _platforms_from_payload(payload)
    if not platform_values:
        return ManifestInspection(image=image, status="unknown", error="manifest has no Linux platforms")
    platforms = tuple(
        sorted(
            f"{os_name}/{architecture}" + (f"/{variant}" if variant else "")
            for os_name, architecture, variant in platform_values
        )
    )
    architectures = tuple(sorted({architecture for _, architecture, _ in platform_values}))
    return ManifestInspection(
        image=image,
        status="supported",
        architectures=architectures,
        platforms=platforms,
    )


def run_host_doctor(
    *,
    host: HostFacts | None = None,
    runner: CommandRunner | None = None,
    image: str | None = None,
    uid: int | None = None,
    gid: int | None = None,
    timezone: str | None = None,
) -> dict[str, Any]:
    """Build a secret-free host/Docker doctor report and fail on preflight."""

    preflight = docker_preflight(runner)
    if not preflight.ok:
        raise preflight.error or PreflightError("Docker preflight failed")
    facts = host or detect_host(uid=uid, gid=gid, timezone=timezone)
    # A working runtime is sufficient to adopt an existing install on an
    # otherwise unsupported distribution.  The dependency policy is reported
    # for a later, explicitly approved install-deps flow.
    dependencies = dependency_plan(facts)
    report: dict[str, Any] = {
        "status": "ok",
        "host": {
            "uid": facts.uid,
            "gid": facts.gid,
            "timezone": facts.timezone,
            "distro_id": facts.distro_id,
            "distro_like": list(facts.distro_like),
            "arch": facts.arch,
        },
        "docker": preflight.report,
        "dependencies": dependencies.report,
    }
    if image:
        report["manifest"] = inspect_manifest_architectures(image, runner=runner).report
    return report


__all__ = [
    "COMPOSE_MINIMUM",
    "DependencyPlan",
    "DecisionRecord",
    "DockerPreflight",
    "ManifestInspection",
    "PlannedCommand",
    "PreflightError",
    "UnsupportedDistroError",
    "UnsupportedPlatformError",
    "check_docker",
    "dependency_plan",
    "docker_preflight",
    "inspect_docker",
    "inspect_manifest_architectures",
    "parse_compose_version",
    "parse_docker_version",
    "run_host_doctor",
    "validate_compose_version",
]
