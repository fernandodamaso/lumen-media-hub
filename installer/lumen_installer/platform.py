"""Side-effect-light Linux host fact detection.

The installer keeps host discovery separate from mutation.  ``detect_host``
therefore accepts injectable readers and command functions so that callers can
test it without changing the host or invoking privileged commands.
"""

from __future__ import annotations

import os
import platform as stdlib_platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .errors import InvalidInputError


@dataclass(frozen=True)
class HostFacts:
    """Immutable facts used by later installer planning stages."""

    uid: int
    gid: int
    timezone: str
    distro_id: str
    distro_like: tuple[str, ...]
    arch: str
    euid: int
    sudo_uid: int | None
    sudo_gid: int | None
    codename: str | None = None

    def __post_init__(self) -> None:
        # Keep the nested collection immutable too; callers commonly build
        # this field from a split ID_LIKE string.
        object.__setattr__(self, "distro_like", tuple(self.distro_like))
        if self.codename is not None:
            normalized = str(self.codename).strip()
            object.__setattr__(self, "codename", normalized or None)

    @property
    def distro_codename(self) -> str | None:
        """Compatibility alias for the distribution release codename."""

        return self.codename

    @property
    def version_codename(self) -> str | None:
        """Compatibility alias matching the os-release field name."""

        return self.codename


_ARCH_ALIASES = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "x86-64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "aarch64",
}


def _positive_id(value: Any, label: str) -> int:
    candidate = str(value).strip()
    try:
        parsed = int(candidate, 10)
    except (TypeError, ValueError) as exc:
        raise InvalidInputError(f"{label} must be a nonzero integer") from exc
    if parsed <= 0 or not candidate.isdigit():
        raise InvalidInputError(f"{label} must be a nonzero integer")
    return parsed


def _optional_id(value: Any, label: str) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return _positive_id(value, label)
    except InvalidInputError:
        return None


def _read_os_release(path: str | Path) -> dict[str, str]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    return _parse_os_release(text)


def _parse_os_release(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def _normalise_arch(machine: str | None) -> str:
    value = (machine or stdlib_platform.machine()).strip().lower()
    try:
        return _ARCH_ALIASES[value]
    except KeyError as exc:
        raise InvalidInputError(f"unsupported host architecture: {value or 'unknown'}") from exc


def _normalise_timezone(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    if not candidate:
        return None
    # timedatectl may return a property assignment when invoked through a
    # generic runner.  Accept both that form and its --value output.
    if candidate.lower().startswith("timezone="):
        candidate = candidate.split("=", 1)[1].strip()
    return candidate or None


def _timezone_from_localtime(path: str | Path) -> str | None:
    localtime = Path(path)
    try:
        if not localtime.is_symlink():
            return None
        # Read the link itself first.  A test fixture or an early-boot host
        # can legitimately expose a link before its target is mounted.
        raw_target = Path(os.readlink(localtime))
        target = raw_target if raw_target.is_absolute() else localtime.parent / raw_target
        target = target.resolve(strict=False)
    except (OSError, RuntimeError):
        return None

    parts = target.parts
    # The zone name is the path below the zoneinfo directory.  Looking for the
    # final marker also supports distributions that keep zoneinfo elsewhere.
    markers = [index for index, part in enumerate(parts) if part == "zoneinfo"]
    if not markers:
        return None
    zone_parts = parts[markers[-1] + 1 :]
    if not zone_parts:
        return None
    return "/".join(zone_parts)


def _run_timedatectl(command: Callable[[], Any] | Any | None) -> str | None:
    if callable(command):
        try:
            result = command()
        except TypeError:
            # A supplied command runner may accept the argv it is expected to
            # execute rather than taking no arguments.
            try:
                result = command(
                    ["timedatectl", "show", "--property=Timezone", "--value"]
                )
            except TypeError:
                return None
        except (OSError, subprocess.SubprocessError):
            return None
        if isinstance(result, str):
            return _normalise_timezone(result)
        stdout = getattr(result, "stdout", result)
        return _normalise_timezone(stdout)

    if isinstance(command, str):
        return _normalise_timezone(command)

    if command is not None and hasattr(command, "run"):
        try:
            result = command.run(
                ["timedatectl", "show", "--property=Timezone", "--value"]
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if getattr(result, "returncode", 0) != 0:
            return None
        return _normalise_timezone(getattr(result, "stdout", result))

    try:
        result = subprocess.run(
            ["timedatectl", "show", "--property=Timezone", "--value"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return _normalise_timezone(result.stdout)


def detect_host(
    *,
    uid: int | None = None,
    gid: int | None = None,
    owner_uid: int | None = None,
    owner_gid: int | None = None,
    puid: int | None = None,
    pgid: int | None = None,
    euid: int | None = None,
    geteuid: Callable[[], int] | None = None,
    getuid: Callable[[], int] | None = None,
    getgid: Callable[[], int] | None = None,
    environment: Mapping[str, str] | None = None,
    env: Mapping[str, str] | None = None,
    timezone: str | None = None,
    localtime_path: str | Path = "/etc/localtime",
    timedatectl: Callable[[], Any] | Any | None = None,
    os_release_path: str | Path = "/etc/os-release",
    os_release: Mapping[str, str] | str | None = None,
    os_release_text: str | None = None,
    machine: str | None = None,
    codename: str | None = None,
) -> HostFacts:
    """Detect the immutable host facts needed by installer planning.

    A root process is accepted only when it was launched by ``sudo`` with a
    valid non-root owner, or when both owner IDs were explicitly supplied.
    Explicit IDs are useful for service accounts and take precedence over
    ``SUDO_UID``/``SUDO_GID``.
    """

    values = environment if environment is not None else env
    if values is None:
        values = os.environ

    effective_uid = int(euid if euid is not None else (geteuid or os.geteuid)())
    sudo_uid = _optional_id(values.get("SUDO_UID"), "SUDO_UID")
    sudo_gid = _optional_id(values.get("SUDO_GID"), "SUDO_GID")

    explicit_uid = uid if uid is not None else owner_uid
    explicit_gid = gid if gid is not None else owner_gid
    if explicit_uid is None:
        explicit_uid = puid
    if explicit_gid is None:
        explicit_gid = pgid

    if (explicit_uid is None) != (explicit_gid is None):
        raise InvalidInputError("both owner UID and GID are required")

    if explicit_uid is not None and explicit_gid is not None:
        owner = (
            _positive_id(explicit_uid, "owner UID"),
            _positive_id(explicit_gid, "owner GID"),
        )
    elif effective_uid == 0:
        if sudo_uid is None or sudo_gid is None:
            raise InvalidInputError(
                "genuine root requires explicit nonzero owner UID and GID"
            )
        owner = (sudo_uid, sudo_gid)
    else:
        owner = (
            _positive_id((getuid or os.getuid)(), "owner UID"),
            _positive_id((getgid or os.getgid)(), "owner GID"),
        )

    resolved_timezone = _normalise_timezone(timezone)
    if resolved_timezone is None:
        resolved_timezone = _timezone_from_localtime(localtime_path)
    if resolved_timezone is None:
        resolved_timezone = _run_timedatectl(timedatectl)
    if resolved_timezone is None:
        raise InvalidInputError("could not determine the host timezone")

    if os_release is None:
        release_values = _parse_os_release(os_release_text) if os_release_text is not None else _read_os_release(os_release_path)
    elif isinstance(os_release, str):
        release_values = _parse_os_release(os_release)
    else:
        release_values = {str(key): str(value) for key, value in os_release.items()}
    distro_id = release_values.get("ID", "").strip().lower()
    distro_like = tuple(
        item.lower()
        for item in release_values.get("ID_LIKE", "").split()
        if item.strip()
    )
    resolved_codename = codename
    if resolved_codename is None:
        resolved_codename = release_values.get("VERSION_CODENAME")
    if resolved_codename is None:
        resolved_codename = release_values.get("UBUNTU_CODENAME")

    return HostFacts(
        uid=owner[0],
        gid=owner[1],
        timezone=resolved_timezone,
        distro_id=distro_id,
        distro_like=distro_like,
        arch=_normalise_arch(machine),
        euid=effective_uid,
        sudo_uid=sudo_uid,
        sudo_gid=sudo_gid,
        codename=str(resolved_codename).strip() if resolved_codename else None,
    )


__all__ = ["HostFacts", "detect_host"]
