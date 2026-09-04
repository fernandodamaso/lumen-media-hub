"""Safe migration and runtime reconciliation for the Seerr request service.

The Compose service intentionally keeps the historical ``jellyseerr`` key and
container name.  This module keeps the host-side config migration equally
conservative: an adopted config is copied before ownership changes, and the
official Seerr image's numeric runtime owner is applied only after an explicit
decision.
"""

from __future__ import annotations

import json
import inspect
import os
import re
import shutil
import stat
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..errors import DriftError, InstallerError, InvalidInputError
from ..http import HttpResponse, HttpStatusError, HttpTransportError
from .base import ServiceCheckpoint, ServiceResult


SERVICE_NAME = "jellyseerr"
CONTAINER_NAME = "jellyseerr"
SEERR_IMAGE = "ghcr.io/seerr-team/seerr:latest"
SEERR_CONFIG_PATH = Path("config/jellyseerr")
SEERR_CONFIG_MOUNT = "/app/config"
SEERR_UID = 1000
SEERR_GID = 1000
SEERR_PORT = 5055
SEERR_INTERNAL_URL = "http://jellyseerr:5055"
SEERR_MINIMUM_VERSION = (2, 0, 0)

_INTEGRATIONS = ("jellyfin", "sonarr", "radarr")
_DEFAULT_INTEGRATION_PATHS = {
    "jellyfin": "/api/v1/settings/jellyfin",
    "sonarr": "/api/v1/settings/sonarr",
    "radarr": "/api/v1/settings/radarr",
}
_DEFAULT_INTEGRATION_URLS = {
    "jellyfin": "http://jellyfin:8096",
    "sonarr": "http://sonarr:8989",
    "radarr": "http://radarr:7878",
}
_DEFAULT_PORTS = {"jellyfin": 8096, "sonarr": 8989, "radarr": 7878}
_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")
_SAFE_CONFIG_DIRECTORY = "config"
_SAFE_CONFIG_NAME = "jellyseerr"
_DISALLOWED_CONFIG_COMPONENTS = frozenset({"media", "downloads"})
_DISALLOWED_CONFIG_ROOTS = tuple(
    Path(value)
    for value in (
        "/",
        "/bin",
        "/boot",
        "/dev",
        "/etc",
        "/lib",
        "/mnt",
        "/opt",
        "/proc",
        "/root",
        "/run",
        "/sbin",
        "/srv",
        "/sys",
        "/usr",
        "/var",
    )
)
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_SAFE_CHOWN = os.chown


@dataclass(frozen=True)
class _DirectoryChainEntry:
    parent_fd: int
    name: str
    device: int
    inode: int


@dataclass
class _DirectoryChain:
    fd: int
    entries: tuple[_DirectoryChainEntry, ...]
    retained_fds: list[int]


class SeerrError(InstallerError):
    """Base class for sanitized Seerr failures."""

    code = "seerr-error"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        self.code = code or type(self).code
        InstallerError.__init__(self, self.code)

    @property
    def report(self) -> dict[str, str]:
        return {"error": self.code}

    @property
    def redacted(self) -> dict[str, str]:
        return self.report


class SeerrConfigError(InvalidInputError, SeerrError):
    code = "seerr-config"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, self.code)


class SeerrCapabilityError(InvalidInputError, SeerrError):
    code = "seerr-capability"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, self.code)


class SeerrSchemaError(InvalidInputError, SeerrError):
    code = "seerr-schema"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, self.code)


class SeerrConflictError(DriftError, SeerrError):
    code = "seerr-conflict"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        DriftError.__init__(self, self.code)


SeerrOwnershipError = SeerrConflictError


@dataclass(frozen=True, repr=False)
class OwnershipInspection:
    """Numeric ownership facts for one exact config directory."""

    path: Path
    exists: bool
    uid: int | None = None
    gid: int | None = None
    entries: int = 0
    mismatched_entries: int = 0

    @property
    def matches_runtime_owner(self) -> bool:
        return self.exists and self.mismatched_entries == 0

    @property
    def adopted(self) -> bool:
        return self.exists

    @property
    def report(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "exists": self.exists,
            "uid": self.uid,
            "gid": self.gid,
            "entries": self.entries,
            "mismatched_entries": self.mismatched_entries,
            "matches_runtime_owner": self.matches_runtime_owner,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    def __repr__(self) -> str:
        return (
            f"OwnershipInspection(path={str(self.path)!r}, exists={self.exists!r}, "
            f"uid={self.uid!r}, gid={self.gid!r}, mismatched_entries={self.mismatched_entries!r})"
        )


@dataclass(frozen=True, repr=False)
class SeerrConfigResult:
    """Secret-free result of the exact config migration boundary."""

    status: str
    path: Path
    ownership: OwnershipInspection
    actions: tuple[str, ...] = ()
    backup_path: Path | None = None
    requires_confirmation: bool = False
    dry_run: bool = False
    error: SeerrError | None = field(default=None, repr=False, compare=False)

    @property
    def report(self) -> dict[str, Any]:
        return {
            "service": SERVICE_NAME,
            "status": self.status,
            "path": str(self.path),
            "ownership": self.ownership.report,
            "actions": list(self.actions),
            "backup_path": str(self.backup_path) if self.backup_path is not None else None,
            "requires_confirmation": self.requires_confirmation,
            "dry_run": self.dry_run,
            "error": self.error.code if self.error is not None else None,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    @property
    def steps(self) -> tuple[str, ...]:
        return self.actions

    def __repr__(self) -> str:
        return (
            f"SeerrConfigResult(status={self.status!r}, path={str(self.path)!r}, "
            f"actions={self.actions!r}, dry_run={self.dry_run!r})"
        )


@dataclass(frozen=True, repr=False)
class SeerrCapability:
    """Non-sensitive runtime capability facts returned by the status probe."""

    version: str
    integrations: tuple[str, ...] = _INTEGRATIONS
    supported: bool = True

    @property
    def report(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "integrations": list(self.integrations),
            "supported": self.supported,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    def __repr__(self) -> str:
        return f"SeerrCapability(version={self.version!r}, integrations={self.integrations!r}, supported={self.supported!r})"


@dataclass(frozen=True)
class SeerrResult(ServiceResult):
    """Operation result with a stable Seerr-specific representation."""

    supported: bool | None = field(default=None, repr=False, compare=False)

    @property
    def report(self) -> dict[str, Any]:
        report = super().report
        if self.supported is not None:
            report["supported"] = self.supported
        return report

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    def __repr__(self) -> str:
        return (
            f"SeerrResult(service={self.service!r}, status={self.status!r}, "
            f"actions={self.actions!r}, dry_run={self.dry_run!r})"
        )


def _absolute_directory_path(value: str | os.PathLike[str], *, name: str) -> Path:
    try:
        path = Path(value)
    except (TypeError, ValueError, OSError) as exc:
        raise SeerrConfigError() from exc
    if not path.is_absolute() or "\x00" in str(path):
        raise SeerrConfigError()
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            if current.is_symlink():
                raise SeerrConfigError()
        except OSError:
            raise SeerrConfigError() from None
    return Path(os.path.abspath(str(path)))


def _under(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _validate_safe_config_root(path: Path) -> None:
    if path in (Path("/"), Path("/home")) or any(
        _under(path, root) for root in _DISALLOWED_CONFIG_ROOTS if root != Path("/")
    ):
        raise SeerrConfigError()
    if any(component.casefold() in _DISALLOWED_CONFIG_COMPONENTS for component in path.parts):
        raise SeerrConfigError()


def _seerr_config_path(
    value: str | os.PathLike[str],
    *,
    repo_root: str | os.PathLike[str] | None = None,
    config_root: str | os.PathLike[str] | None = None,
) -> Path:
    """Require the one repository-owned path mounted into the Seerr image."""

    path = _absolute_directory_path(value, name="Seerr config")
    if path.name != _SAFE_CONFIG_NAME or path.parent.name != _SAFE_CONFIG_DIRECTORY:
        raise SeerrConfigError()
    derived_root = path.parent.parent
    _validate_safe_config_root(derived_root)
    if repo_root is not None:
        expected_root = _absolute_directory_path(repo_root, name="repository root")
        _validate_safe_config_root(expected_root)
        if derived_root != expected_root:
            raise SeerrConfigError()
    if config_root is not None:
        expected_config = _absolute_directory_path(config_root, name="Seerr config root")
        if expected_config.name != _SAFE_CONFIG_DIRECTORY or path != expected_config / _SAFE_CONFIG_NAME:
            raise SeerrConfigError()
    return path


def _safe_backup_path(value: str | os.PathLike[str]) -> Path:
    path = _absolute_directory_path(value, name="Seerr config backup")
    if path in (Path("/"), Path("/home")) or any(
        _under(path, root) for root in _DISALLOWED_CONFIG_ROOTS if root != Path("/")
    ):
        raise SeerrConfigError()
    if any(component.casefold() in _DISALLOWED_CONFIG_COMPONENTS for component in path.parts):
        raise SeerrConfigError()
    return path


def _validate_backup_location(source: Path, destination: Path) -> None:
    if destination == source or source in destination.parents:
        raise SeerrConfigError()
    if destination.exists():
        raise SeerrConfigError()


def _close_fd(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def _open_directory_chain(path: Path, *, create: bool) -> _DirectoryChain:
    """Open every path component with no-follow descriptors held throughout."""

    retained: list[int] = []
    entries: list[_DirectoryChainEntry] = []
    try:
        fd = os.open(os.path.sep, _DIRECTORY_FLAGS)
        retained.append(fd)
        for component in path.parts[1:]:
            parent_metadata = os.fstat(fd)
            try:
                next_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(component, mode=0o700, dir_fd=fd)
                next_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=fd)
            metadata = os.fstat(next_fd)
            if not stat.S_ISDIR(metadata.st_mode):
                _close_fd(next_fd)
                raise SeerrConfigError()
            entries.append(
                _DirectoryChainEntry(
                    parent_fd=fd,
                    name=component,
                    device=metadata.st_dev,
                    inode=metadata.st_ino,
                )
            )
            fd = next_fd
            retained.append(fd)
        return _DirectoryChain(fd=fd, entries=tuple(entries), retained_fds=retained)
    except SeerrConfigError:
        for item in reversed(retained):
            _close_fd(item)
        raise
    except OSError:
        for item in reversed(retained):
            _close_fd(item)
        raise SeerrConfigError() from None


def _assert_directory_chain(chain: _DirectoryChain) -> None:
    try:
        for entry in chain.entries:
            parent = os.fstat(entry.parent_fd)
            current = os.stat(entry.name, dir_fd=entry.parent_fd, follow_symlinks=False)
            if (
                not stat.S_ISDIR(parent.st_mode)
                or stat.S_ISLNK(current.st_mode)
                or not stat.S_ISDIR(current.st_mode)
                or current.st_dev != entry.device
                or current.st_ino != entry.inode
            ):
                raise SeerrConfigError()
    except SeerrConfigError:
        raise
    except OSError:
        raise SeerrConfigError() from None


def _open_config_directory(path: Path, *, create: bool) -> tuple[_DirectoryChain, int, tuple[int, int]]:
    chain = _open_directory_chain(path.parent, create=create)
    try:
        try:
            fd = os.open(path.name, _DIRECTORY_FLAGS, dir_fd=chain.fd)
        except FileNotFoundError:
            if not create:
                raise
            os.mkdir(path.name, mode=0o700, dir_fd=chain.fd)
            fd = os.open(path.name, _DIRECTORY_FLAGS, dir_fd=chain.fd)
        metadata = os.fstat(fd)
        lexical = os.stat(path.name, dir_fd=chain.fd, follow_symlinks=False)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(lexical.st_mode)
            or not stat.S_ISDIR(lexical.st_mode)
            or metadata.st_dev != lexical.st_dev
            or metadata.st_ino != lexical.st_ino
        ):
            _close_fd(fd)
            raise SeerrConfigError()
        return chain, fd, (metadata.st_dev, metadata.st_ino)
    except SeerrConfigError:
        for item in reversed(chain.retained_fds):
            _close_fd(item)
        raise
    except FileNotFoundError:
        for item in reversed(chain.retained_fds):
            _close_fd(item)
        raise SeerrConfigError() from None
    except OSError:
        for item in reversed(chain.retained_fds):
            _close_fd(item)
        raise SeerrConfigError() from None


def _assert_config_directory_identity(
    chain: _DirectoryChain,
    config_fd: int,
    config_path: Path,
    expected: tuple[int, int],
) -> None:
    _assert_directory_chain(chain)
    try:
        current = os.stat(config_path.name, dir_fd=chain.fd, follow_symlinks=False)
        descriptor = os.fstat(config_fd)
        if (
            stat.S_ISLNK(current.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or (current.st_dev, current.st_ino) != expected
            or (descriptor.st_dev, descriptor.st_ino) != expected
        ):
            raise SeerrConfigError()
    except SeerrConfigError:
        raise
    except OSError:
        raise SeerrConfigError() from None


def _chown_with_callback(
    callback: Callable[..., Any],
    path: Path,
    uid: int,
    gid: int,
    *,
    dir_fd: int | None = None,
    fd: int | None = None,
) -> None:
    """Use descriptor-relative ownership in production while retaining test seams."""

    if callback is _SAFE_CHOWN:
        try:
            if fd is not None:
                os.fchown(fd, uid, gid)
            else:
                os.chown(path.name, uid, gid, dir_fd=dir_fd, follow_symlinks=False)
        except OSError:
            raise SeerrConfigError() from None
        return
    try:
        parameters = tuple(inspect.signature(callback).parameters.values())
    except (TypeError, ValueError):
        parameters = ()
    accepts_dir_fd = any(item.kind is inspect.Parameter.VAR_KEYWORD for item in parameters) or "dir_fd" in {
        item.name for item in parameters
    }
    kwargs: dict[str, Any] = {"follow_symlinks": False}
    if accepts_dir_fd and dir_fd is not None:
        kwargs["dir_fd"] = dir_fd
    try:
        callback(path, uid, gid, **kwargs)
    except OSError:
        raise SeerrConfigError() from None


def _directory_snapshot(fd: int) -> dict[str, tuple[int, int, int]]:
    try:
        names = tuple(os.listdir(fd))
        return {
            name: (
                stat.S_IFMT(metadata.st_mode),
                metadata.st_dev,
                metadata.st_ino,
            )
            for name in names
            for metadata in (os.stat(name, dir_fd=fd, follow_symlinks=False),)
        }
    except OSError:
        raise SeerrConfigError() from None


def _assert_directory_snapshot(fd: int, expected: Mapping[str, tuple[int, int, int]]) -> None:
    current = _directory_snapshot(fd)
    if current != dict(expected):
        raise SeerrConfigError()


def inspect_config_ownership(
    config_path: str | os.PathLike[str],
    *,
    runtime_uid: int = SEERR_UID,
    runtime_gid: int = SEERR_GID,
    repo_root: str | os.PathLike[str] | None = None,
    config_root: str | os.PathLike[str] | None = None,
) -> OwnershipInspection:
    """Inspect an exact config directory without following symlinks."""

    path = _seerr_config_path(config_path, repo_root=repo_root, config_root=config_root)
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return OwnershipInspection(path=path, exists=False)
    except OSError:
        raise SeerrConfigError() from None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise SeerrConfigError()

    entries = 0
    mismatched = 0
    first_uid = int(metadata.st_uid)
    first_gid = int(metadata.st_gid)
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            current_metadata = os.lstat(current)
        except OSError:
            raise SeerrConfigError() from None
        if stat.S_ISLNK(current_metadata.st_mode):
            continue
        entries += 1
        if current_metadata.st_uid != runtime_uid or current_metadata.st_gid != runtime_gid:
            mismatched += 1
        if stat.S_ISDIR(current_metadata.st_mode):
            try:
                children = tuple(current.iterdir())
            except OSError:
                raise SeerrConfigError() from None
            stack.extend(children)
    return OwnershipInspection(
        path=path,
        exists=True,
        uid=first_uid,
        gid=first_gid,
        entries=entries,
        mismatched_entries=mismatched,
    )


def backup_config(
    config_path: str | os.PathLike[str],
    backup_path: str | os.PathLike[str],
    *,
    repo_root: str | os.PathLike[str] | None = None,
    config_root: str | os.PathLike[str] | None = None,
) -> Path:
    """Copy one exact config tree without overwriting an existing backup."""

    source = _seerr_config_path(config_path, repo_root=repo_root, config_root=config_root)
    destination = _safe_backup_path(backup_path)
    _validate_backup_location(source, destination)
    try:
        metadata = os.lstat(source)
    except (FileNotFoundError, OSError):
        raise SeerrConfigError() from None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise SeerrConfigError()
    try:
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(destination.parent, 0o700)
        shutil.copytree(source, destination, symlinks=True, copy_function=shutil.copy2)
    except (OSError, shutil.Error):
        raise SeerrConfigError() from None
    return destination


def _recursive_chown(
    config_path: Path,
    uid: int,
    gid: int,
    *,
    chown: Callable[..., Any] = _SAFE_CHOWN,
) -> None:
    chain, root_fd, root_identity = _open_config_directory(config_path, create=False)
    retained_fds = [*chain.retained_fds, root_fd]
    stack: list[tuple[Path, int, dict[str, tuple[int, int, int]]]] = [
        (config_path, root_fd, _directory_snapshot(root_fd))
    ]
    try:
        _chown_with_callback(chown, config_path, uid, gid, fd=root_fd)
        _assert_config_directory_identity(chain, root_fd, config_path, root_identity)
        while stack:
            current_path, current_fd, expected_entries = stack.pop()
            _assert_directory_snapshot(current_fd, expected_entries)
            try:
                names = tuple(os.listdir(current_fd))
            except OSError:
                raise SeerrConfigError() from None
            for name in names:
                child_path = current_path / name
                try:
                    lexical = os.stat(name, dir_fd=current_fd, follow_symlinks=False)
                except OSError:
                    raise SeerrConfigError() from None
                if stat.S_ISLNK(lexical.st_mode):
                    _chown_with_callback(
                        chown,
                        child_path,
                        uid,
                        gid,
                        dir_fd=current_fd,
                    )
                    continue
                if stat.S_ISDIR(lexical.st_mode):
                    try:
                        child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=current_fd)
                        opened = os.fstat(child_fd)
                    except OSError:
                        raise SeerrConfigError() from None
                    if (
                        not stat.S_ISDIR(opened.st_mode)
                        or (opened.st_dev, opened.st_ino) != (lexical.st_dev, lexical.st_ino)
                    ):
                        _close_fd(child_fd)
                        raise SeerrConfigError()
                    retained_fds.append(child_fd)
                    child_entries = _directory_snapshot(child_fd)
                    _chown_with_callback(
                        chown,
                        child_path,
                        uid,
                        gid,
                        fd=child_fd,
                    )
                    _assert_directory_snapshot(child_fd, child_entries)
                    stack.append((child_path, child_fd, child_entries))
                    continue
                try:
                    child_fd = os.open(
                        name,
                        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=current_fd,
                    )
                    opened = os.fstat(child_fd)
                except OSError:
                    raise SeerrConfigError() from None
                try:
                    if (opened.st_dev, opened.st_ino) != (lexical.st_dev, lexical.st_ino):
                        raise SeerrConfigError()
                    _chown_with_callback(
                        chown,
                        child_path,
                        uid,
                        gid,
                        fd=child_fd,
                    )
                finally:
                    _close_fd(child_fd)
            _assert_config_directory_identity(chain, root_fd, config_path, root_identity)
    finally:
        for fd in reversed(retained_fds):
            _close_fd(fd)


def prepare_seerr_config(
    config_path: str | os.PathLike[str],
    *,
    backup_path: str | os.PathLike[str] | None = None,
    confirm: bool = False,
    dry_run: bool = False,
    runtime_uid: int = SEERR_UID,
    runtime_gid: int = SEERR_GID,
    repo_root: str | os.PathLike[str] | None = None,
    config_root: str | os.PathLike[str] | None = None,
    backup: Callable[[str | os.PathLike[str], str | os.PathLike[str]], Path] | None = None,
    chown: Callable[..., Any] | None = None,
) -> SeerrConfigResult:
    """Prepare a fresh/adopted config with backup-first ownership policy."""

    if type(confirm) is not bool or type(dry_run) is not bool:
        raise InvalidInputError("Seerr confirmation and dry-run values must be booleans")
    if runtime_uid != SEERR_UID or runtime_gid != SEERR_GID:
        raise SeerrConfigError()
    uid = SEERR_UID
    gid = SEERR_GID
    selected_backup_fn = backup or backup_config
    selected_chown = chown or os.chown
    path = _seerr_config_path(config_path, repo_root=repo_root, config_root=config_root)
    selected_backup = (
        _safe_backup_path(backup_path)
        if backup_path is not None
        else None
    )
    ownership = inspect_config_ownership(
        path,
        runtime_uid=SEERR_UID,
        runtime_gid=SEERR_GID,
        repo_root=repo_root,
        config_root=config_root,
    )

    if not ownership.exists:
        actions = ["inspect-ownership", "create-config-directory", "set-runtime-owner"]
        if dry_run:
            return SeerrConfigResult(
                status="dry-run",
                path=path,
                ownership=ownership,
                actions=tuple(actions),
                dry_run=True,
            )
        try:
            chain, config_fd, _identity = _open_config_directory(path, create=True)
            try:
                os.fchmod(config_fd, 0o700)
                if selected_chown is _SAFE_CHOWN:
                    os.fchown(config_fd, SEERR_UID, SEERR_GID)
                else:
                    _chown_with_callback(selected_chown, path, SEERR_UID, SEERR_GID)
                _assert_config_directory_identity(chain, config_fd, path, _identity)
            finally:
                _close_fd(config_fd)
                for fd in reversed(chain.retained_fds):
                    _close_fd(fd)
        except FileExistsError:
            raise SeerrConfigError() from None
        except OSError:
            raise SeerrConfigError() from None
        return SeerrConfigResult(
            status="ok",
            path=path,
            ownership=inspect_config_ownership(path, runtime_uid=SEERR_UID, runtime_gid=SEERR_GID),
            actions=tuple(actions),
        )

    if selected_backup is None:
        raise SeerrConfigError()
    _validate_backup_location(path, selected_backup)
    mismatched = not ownership.matches_runtime_owner
    actions = ["inspect-ownership"]
    if dry_run:
        actions.append("backup-config-unverified")
        if mismatched:
            actions.append("await-ownership-confirmation")
        else:
            actions.append("reuse-config")
        return SeerrConfigResult(
            status="dry-run",
            path=path,
            ownership=ownership,
            actions=tuple(actions),
            backup_path=selected_backup,
            requires_confirmation=mismatched,
            dry_run=True,
        )

    # The backup is deliberately taken for every adopted run, including a
    # no-op ownership match.  It is the recoverable snapshot for any later
    # Seerr start/update operation and always precedes a chown.
    selected_backup_fn(path, selected_backup)
    actions.append("backup-config")
    if not mismatched:
        actions.append("reuse-config")
        return SeerrConfigResult(
            status="ok",
            path=path,
            ownership=ownership,
            actions=tuple(actions),
            backup_path=selected_backup,
        )
    if not confirm:
        actions.append("await-ownership-confirmation")
        return SeerrConfigResult(
            status="drift",
            path=path,
            ownership=ownership,
            actions=tuple(actions),
            backup_path=selected_backup,
            requires_confirmation=True,
            error=SeerrConflictError(),
        )
    _recursive_chown(path, uid, gid, chown=selected_chown)
    actions.append("chown-config-recursive")
    return SeerrConfigResult(
        status="ok",
        path=path,
        ownership=inspect_config_ownership(path, runtime_uid=uid, runtime_gid=gid),
        actions=tuple(actions),
        backup_path=selected_backup,
    )


prepare_config = prepare_seerr_config


def _base_url(value: Any, *, service: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"{service} URL is required")
    candidate = value.strip().rstrip("/")
    try:
        parsed = urllib.parse.urlsplit(candidate)
        _ = parsed.port
    except (TypeError, ValueError):
        raise InvalidInputError(f"{service} URL is invalid") from None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise InvalidInputError(f"{service} URL is invalid")
    return candidate


def seerr_service_urls() -> dict[str, str]:
    """Return the Compose-DNS URLs used by supported Seerr integrations."""

    return dict(_DEFAULT_INTEGRATION_URLS)


def _version(value: str) -> tuple[int, int, int] | None:
    match = _VERSION_RE.fullmatch(value.strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def _json(response: Any) -> Any:
    if isinstance(response, Mapping) and not isinstance(response, HttpResponse):
        if "body" not in response:
            return response
        body = response["body"]
        if isinstance(body, (Mapping, list)):
            return body
        try:
            return json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
        except (TypeError, UnicodeError, ValueError, json.JSONDecodeError):
            raise SeerrSchemaError() from None
    decoder = getattr(response, "json", None)
    if not callable(decoder):
        raise SeerrSchemaError() from None
    try:
        return decoder()
    except Exception:
        raise SeerrSchemaError() from None


class SeerrAdapter:
    """Capability-gated Seerr integration reconciler."""

    service = SERVICE_NAME

    def __init__(
        self,
        base_url: str,
        transport: Any,
        *,
        api_key: str | None = None,
        jellyfin_url: str = _DEFAULT_INTEGRATION_URLS["jellyfin"],
        jellyfin_api_key: str | None = None,
        sonarr_url: str = _DEFAULT_INTEGRATION_URLS["sonarr"],
        sonarr_api_key: str | None = None,
        radarr_url: str = _DEFAULT_INTEGRATION_URLS["radarr"],
        radarr_api_key: str | None = None,
    ) -> None:
        if transport is None or not callable(getattr(transport, "request", None)):
            raise InvalidInputError("Seerr transport is required")
        self.base_url = _base_url(base_url, service="Seerr")
        if api_key is not None and (not isinstance(api_key, str) or not api_key.strip()):
            raise InvalidInputError("Seerr API key is invalid")
        self._transport = transport
        self._api_key = api_key.strip() if isinstance(api_key, str) else None
        self._integration_urls = {
            "jellyfin": _base_url(jellyfin_url, service="Jellyfin"),
            "sonarr": _base_url(sonarr_url, service="Sonarr"),
            "radarr": _base_url(radarr_url, service="Radarr"),
        }
        self._integration_keys = {
            "jellyfin": jellyfin_api_key,
            "sonarr": sonarr_api_key,
            "radarr": radarr_api_key,
        }
        for service, key in self._integration_keys.items():
            if key is not None and (not isinstance(key, str) or not key.strip()):
                raise InvalidInputError(f"{service} API key is invalid")
        self._capability: SeerrCapability | None = None

    def __repr__(self) -> str:
        return "SeerrAdapter(configured=True)"

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, *, body: Any = None) -> Any:
        url = self._url(path)
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["X-Api-Key"] = self._api_key
        kwargs: dict[str, Any] = {"headers": headers}
        if body is not None:
            kwargs["json_body"] = body
        try:
            response = self._transport.request(method, url, **kwargs)
        except HttpTransportError:
            raise
        except Exception:
            raise SeerrError(code="seerr-transport") from None
        status = getattr(response, "status", None)
        if status is None and isinstance(response, Mapping):
            status = response.get("status", 200)
        try:
            status = int(200 if status is None else status)
        except (TypeError, ValueError):
            raise SeerrSchemaError() from None
        if not 200 <= status < 300:
            raise HttpStatusError(method=method, url=url, status=status)
        return response

    @staticmethod
    def _supported_integrations(payload: Mapping[str, Any]) -> tuple[str, ...]:
        raw = payload.get("capabilities", payload.get("integrations", payload.get("features")))
        if raw is None:
            return _INTEGRATIONS
        if isinstance(raw, Mapping):
            if set(raw) != set(_INTEGRATIONS) or any(type(raw[name]) is not bool for name in _INTEGRATIONS):
                raise SeerrCapabilityError() from None
            if not all(raw[name] for name in _INTEGRATIONS):
                raise SeerrCapabilityError() from None
            return _INTEGRATIONS
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
            values = tuple(raw)
            if (
                len(values) != len(_INTEGRATIONS)
                or any(not isinstance(value, str) for value in values)
                or set(values) != set(_INTEGRATIONS)
            ):
                raise SeerrCapabilityError() from None
            return _INTEGRATIONS
        raise SeerrSchemaError() from None

    def probe_capability(self) -> SeerrCapability:
        payload = _json(self._request("GET", "/api/v1/status"))
        if not isinstance(payload, Mapping):
            raise SeerrCapabilityError() from None
        version = payload.get("version")
        if not isinstance(version, str) or not version.strip():
            raise SeerrCapabilityError() from None
        parsed_version = _version(version)
        if parsed_version is None or parsed_version < SEERR_MINIMUM_VERSION:
            raise SeerrCapabilityError() from None
        integrations = self._supported_integrations(payload)
        if not integrations:
            raise SeerrCapabilityError() from None
        self._capability = SeerrCapability(version=version.strip(), integrations=integrations)
        return self._capability

    capability = probe_capability

    @staticmethod
    def _settings_payload(
        current: Mapping[str, Any],
        service: str,
        url: str,
        api_key: str,
    ) -> dict[str, Any]:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname
        if not host:
            raise InvalidInputError(f"{service} URL is invalid")
        port = parsed.port or _DEFAULT_PORTS[service]
        payload = dict(current)
        payload.update(
            {
                "hostname": host,
                "port": port,
                "useSsl": parsed.scheme.casefold() == "https",
                "apiKey": api_key,
            }
        )
        if parsed.path and parsed.path != "/":
            payload["urlBase"] = parsed.path.rstrip("/")
        return payload

    def configure_integrations(
        self,
        *,
        jellyfin_url: str | None = None,
        jellyfin_api_key: str | None = None,
        sonarr_url: str | None = None,
        sonarr_api_key: str | None = None,
        radarr_url: str | None = None,
        radarr_api_key: str | None = None,
        dry_run: bool = False,
    ) -> ServiceResult:
        keys = {
            "jellyfin": jellyfin_api_key if jellyfin_api_key is not None else self._integration_keys["jellyfin"],
            "sonarr": sonarr_api_key if sonarr_api_key is not None else self._integration_keys["sonarr"],
            "radarr": radarr_api_key if radarr_api_key is not None else self._integration_keys["radarr"],
        }
        urls = {
            "jellyfin": _base_url(jellyfin_url, service="Jellyfin") if jellyfin_url is not None else self._integration_urls["jellyfin"],
            "sonarr": _base_url(sonarr_url, service="Sonarr") if sonarr_url is not None else self._integration_urls["sonarr"],
            "radarr": _base_url(radarr_url, service="Radarr") if radarr_url is not None else self._integration_urls["radarr"],
        }
        actions = tuple(["probe-capability", *[f"configure-{name}" for name in _INTEGRATIONS]])
        if dry_run:
            return SeerrResult(
                service=self.service,
                status="dry-run",
                actions=actions,
                dry_run=True,
            )
        for service, key in keys.items():
            if not isinstance(key, str) or not key.strip():
                raise InvalidInputError(f"{service} API key is required")
        try:
            capability = self.probe_capability()
        except SeerrCapabilityError as error:
            return SeerrResult(
                service=self.service,
                status="unsupported",
                actions=("probe-capability",),
                supported=False,
                error=error,
            )
        except (SeerrSchemaError, HttpTransportError, SeerrError) as error:
            return SeerrResult(
                service=self.service,
                status="partial",
                actions=("probe-capability",),
                error=error,
            )

        completed: list[str] = ["probe-capability"]
        try:
            for service in _INTEGRATIONS:
                if service not in capability.integrations:
                    completed.append(f"skip-{service}-unsupported")
                    continue
                current = _json(self._request("GET", _DEFAULT_INTEGRATION_PATHS[service]))
                if not isinstance(current, Mapping):
                    raise SeerrSchemaError() from None
                desired = self._settings_payload(current, service, urls[service], keys[service])
                if dict(current) == desired:
                    completed.append(f"reuse-{service}")
                    continue
                self._request("PUT", _DEFAULT_INTEGRATION_PATHS[service], body=desired)
                completed.append(f"update-{service}")
        except (SeerrSchemaError, HttpTransportError, SeerrError) as error:
            return SeerrResult(
                service=self.service,
                status="partial",
                actions=tuple(completed),
                error=error,
            )
        return SeerrResult(
            service=self.service,
            status="ok",
            actions=tuple(completed),
            supported=True,
        )

    configure = configure_integrations


def configure_seerr(
    base_url: str | None = None,
    transport: Any | None = None,
    *,
    adapter: SeerrAdapter | None = None,
    api_key: str | None = None,
    **kwargs: Any,
) -> ServiceResult:
    """Functional facade for callers that do not retain an adapter."""

    if adapter is None:
        adapter_options = kwargs.pop("adapter_kwargs", {})
        if not isinstance(adapter_options, Mapping):
            raise InvalidInputError("Seerr adapter options must be a mapping")
        if base_url is None or transport is None:
            raise InvalidInputError("Seerr URL and transport are required")
        adapter_options = dict(adapter_options)
        if api_key is not None:
            adapter_options["api_key"] = api_key
        adapter = SeerrAdapter(base_url, transport, **adapter_options)
    return adapter.configure_integrations(**kwargs)


__all__ = [
    "CONTAINER_NAME",
    "OwnershipInspection",
    "SEERR_CONFIG_MOUNT",
    "SEERR_CONFIG_PATH",
    "SEERR_GID",
    "SEERR_IMAGE",
    "SEERR_INTERNAL_URL",
    "SEERR_MINIMUM_VERSION",
    "SEERR_PORT",
    "SEERR_UID",
    "SERVICE_NAME",
    "SeerrAdapter",
    "SeerrCapability",
    "SeerrCapabilityError",
    "SeerrConfigError",
    "SeerrConfigResult",
    "SeerrConflictError",
    "SeerrError",
    "SeerrOwnershipError",
    "SeerrResult",
    "SeerrSchemaError",
    "backup_config",
    "configure_seerr",
    "inspect_config_ownership",
    "prepare_config",
    "prepare_seerr_config",
    "seerr_service_urls",
]
