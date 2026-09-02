"""Safe host storage validation and read-only stale-container discovery."""

from __future__ import annotations

import ctypes
import json
import math
import os
import re
import stat
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import InvalidInputError, PartialError


# These are the only directories the foundation phase owns.  Service adapters
# may later create service-specific state below their config mounts, but the
# media foundation never scans or creates arbitrary user directories.
MEDIA_SUBDIRECTORIES = (Path("media"), Path("media/movies"), Path("media/tv"))
DOWNLOAD_SUBDIRECTORIES: tuple[Path, ...] = ()
STORAGE_DIRECTORY_MODE = 0o775


class StorageMutationError(PartialError):
    """Storage layout mutation failed and rollback left created paths."""

    def __init__(self, message: str, partial_created_paths: Iterable[Path | str]) -> None:
        self.partial_created_paths = tuple(str(path) for path in partial_created_paths)
        # These are approved host paths, not credentials or opaque resource
        # identifiers; include them in the typed failure so operators can
        # recover an incomplete rollback without guessing what remains.
        suffix = ", ".join(self.partial_created_paths) or "<unknown>"
        super().__init__(f"{message}: {suffix}")

    @property
    def report(self) -> dict[str, Any]:
        return {
            "error": "storage mutation partially rolled back",
            "partial_created_paths": list(self.partial_created_paths),
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report


@dataclass(frozen=True, repr=False)
class StorageValidation:
    root_path: Path
    downloads_path: Path
    approved_paths: tuple[Path, ...]
    created_paths: tuple[Path, ...] = ()
    free_gib: Mapping[str, float] | None = None
    warnings: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    dry_run: bool = False

    @property
    def layout(self) -> tuple[Path, ...]:
        return self.approved_paths

    @property
    def root(self) -> Path:
        return self.root_path

    @property
    def downloads(self) -> Path:
        return self.downloads_path

    @property
    def created(self) -> tuple[Path, ...]:
        return self.created_paths

    @property
    def report(self) -> dict[str, Any]:
        return {
            "root_path": str(self.root_path),
            "downloads_path": str(self.downloads_path),
            "approved_paths": [str(path) for path in self.approved_paths],
            "created_paths": [str(path) for path in self.created_paths],
            "free_gib": dict(self.free_gib or {}),
            "warnings": list(self.warnings),
            "decisions": list(self.decisions),
            "dry_run": self.dry_run,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    def __repr__(self) -> str:
        return (
            "StorageValidation("
            f"root_path={str(self.root_path)!r}, downloads_path={str(self.downloads_path)!r}, "
            f"created_paths={len(self.created_paths)}, dry_run={self.dry_run!r})"
        )


def _as_absolute_path(value: Any, *, field_name: str) -> Path:
    if value is None or isinstance(value, (bytes, bytearray)):
        raise InvalidInputError(f"{field_name} must be explicitly supplied")
    if isinstance(value, str) and not value.strip():
        raise InvalidInputError(f"{field_name} must not be empty")
    try:
        raw = Path(value)
    except (TypeError, ValueError, OSError) as exc:
        raise InvalidInputError(f"{field_name} is invalid") from exc
    if not raw.is_absolute():
        raise InvalidInputError(f"{field_name} must be an absolute path")
    if "\x00" in str(raw):
        raise InvalidInputError(f"{field_name} is invalid")
    _reject_symlink_components(raw, field_name=field_name)
    # Keep the validated lexical path.  Resolving here would follow a
    # component that could be replaced by a symlink between the lstat pass and
    # resolution; apply-time descriptor walks below reject that replacement.
    return Path(os.path.abspath(str(raw)))


def _under(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _reject_symlink_components(path: Path, *, field_name: str) -> None:
    # Looking at each raw component catches a target that aliases a
    # safe-looking path through an existing symlink while still allowing
    # ordinary nonexistent paths.
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            if current.is_symlink():
                raise InvalidInputError(f"{field_name} must not contain symlink components")
        except OSError as exc:
            raise InvalidInputError(f"{field_name} cannot be inspected") from exc


def _validate_target_safety(root: Path, downloads: Path, repo: Path) -> None:
    if root == Path("/") or downloads == Path("/"):
        raise InvalidInputError("storage targets may not be the filesystem root")
    broad = {
        Path("/bin"),
        Path("/boot"),
        Path("/dev"),
        Path("/etc"),
        Path("/home"),
        Path("/lib"),
        Path("/media"),
        Path("/mnt"),
        Path("/opt"),
        Path("/proc"),
        Path("/root"),
        Path("/run"),
        Path("/sbin"),
        Path("/srv"),
        Path("/sys"),
        Path("/tmp"),
        Path("/usr"),
        Path("/var"),
    }
    if root in broad or downloads in broad:
        raise InvalidInputError("storage targets are too broad")
    if _under(root, repo) or _under(downloads, repo):
        raise InvalidInputError("media and downloads must be outside the repository")
    if _under(repo, root) or _under(repo, downloads):
        raise InvalidInputError("media and downloads must not contain the repository")
    if _under(root, downloads) or _under(downloads, root):
        raise InvalidInputError("media and downloads must not overlap")
    _reject_symlink_components(root, field_name="ROOT_PATH")
    _reject_symlink_components(downloads, field_name="DOWNLOADS_PATH")


def _nearest_existing(path: Path) -> Path:
    current = path
    while not current.exists():
        parent = current.parent
        if parent == current:
            break
        current = parent
    if not current.exists() or not current.is_dir():
        raise InvalidInputError("storage target has no usable parent directory")
    return current


def _probe_stat(path: Path, probe: Callable[[Path], Any] | None) -> Any:
    try:
        return probe(path) if probe is not None else path.stat()
    except (OSError, ValueError, TypeError) as exc:
        raise InvalidInputError("storage target metadata could not be read") from exc


def _stat_value(metadata: Any, name: str) -> Any:
    if isinstance(metadata, Mapping):
        return metadata.get(name)
    return getattr(metadata, name, None)


def _check_existing_or_parent(
    path: Path,
    *,
    field_name: str,
    uid: int | None,
    gid: int | None,
    stat_probe: Callable[[Path], Any] | None,
    access_probe: Callable[[str | os.PathLike[str], int], bool] | None,
    warnings: list[str],
) -> None:
    existing = path if path.exists() else _nearest_existing(path)
    metadata = _probe_stat(existing, stat_probe)
    mode = _stat_value(metadata, "st_mode")
    if mode is not None and not stat.S_ISDIR(mode):
        raise InvalidInputError(f"{field_name} is not a directory")
    if mode is not None and not (int(mode) & 0o222):
        raise InvalidInputError(f"{field_name} is not writable")
    access = access_probe or os.access
    try:
        writable = bool(access(existing, os.W_OK))
    except (OSError, ValueError, TypeError) as exc:
        raise InvalidInputError(f"{field_name} is not writable") from exc
    if not writable:
        raise InvalidInputError(f"{field_name} is not writable")
    if uid is not None or gid is not None:
        actual_uid = _stat_value(metadata, "st_uid")
        actual_gid = _stat_value(metadata, "st_gid")
        if uid is not None and actual_uid is not None and actual_uid != uid:
            raise InvalidInputError(f"{field_name} owner does not match the requested uid")
        if gid is not None and actual_gid is not None and actual_gid != gid:
            raise InvalidInputError(f"{field_name} group does not match the requested gid")
    elif path.exists() and uid is None and gid is None:
        warnings.append(f"{field_name} ownership was not explicitly requested")


def _free_gib(path: Path, probe: Callable[[Path], Any] | None) -> float:
    try:
        metadata = probe(path) if probe is not None else os.statvfs(path)
        available = float(_stat_value(metadata, "f_bavail"))
        block_size = float(_stat_value(metadata, "f_frsize") or _stat_value(metadata, "f_bsize"))
    except (OSError, TypeError, ValueError, OverflowError) as exc:
        raise InvalidInputError("free storage capacity could not be read") from exc
    if not math.isfinite(available) or not math.isfinite(block_size) or available < 0 or block_size <= 0:
        raise InvalidInputError("free storage capacity metadata is invalid")
    return available * block_size / (1024**3)


_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_RENAME_NOREPLACE = 1


def _close_fd(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


@dataclass
class _CreatedDirectory:
    path: Path
    parent_fd: int
    name: str
    device: int
    inode: int


@dataclass(frozen=True)
class _DirectoryChainEntry:
    """One lexical path component held relative to its stable parent fd."""

    parent_fd: int
    name: str
    parent_device: int
    parent_inode: int
    device: int
    inode: int


@dataclass
class _DirectoryChain:
    fd: int
    entries: tuple[_DirectoryChainEntry, ...]
    retained_fds: list[int]


@dataclass
class _StorageTarget:
    path: Path
    parent_fd: int
    name: str
    parent_device: int
    parent_inode: int
    fd: int | None
    device: int | None
    inode: int | None
    existed: bool
    layout_identities: dict[tuple[str, ...], tuple[int, int] | None] = field(default_factory=dict)
    retained_fds: list[int] = field(default_factory=list)
    parent_chain: _DirectoryChain | None = None


def _open_directory_chain(path: Path) -> _DirectoryChain:
    """Open an absolute directory and retain every path-component descriptor."""

    fd: int | None = None
    retained: list[int] = []
    entries: list[_DirectoryChainEntry] = []
    try:
        fd = os.open(os.path.sep, _DIRECTORY_FLAGS)
        retained.append(fd)
        for component in path.parts[1:]:
            parent_metadata = os.fstat(fd)
            next_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=fd)
            try:
                metadata = os.fstat(next_fd)
            except OSError:
                _close_fd(next_fd)
                raise
            if not stat.S_ISDIR(metadata.st_mode):
                _close_fd(next_fd)
                raise InvalidInputError("storage parent is not a directory")
            entries.append(
                _DirectoryChainEntry(
                    fd,
                    component,
                    parent_metadata.st_dev,
                    parent_metadata.st_ino,
                    metadata.st_dev,
                    metadata.st_ino,
                )
            )
            fd = next_fd
            retained.append(fd)
        return _DirectoryChain(fd, tuple(entries), retained)
    except InvalidInputError:
        for item in reversed(retained):
            _close_fd(item)
        raise
    except OSError as exc:
        for item in reversed(retained):
            _close_fd(item)
        raise InvalidInputError("storage parent could not be opened safely") from exc


def _assert_directory_chain(chain: _DirectoryChain, *, description: str) -> None:
    """Reject replacement of any lexical component below the stable root fd."""

    try:
        for entry in chain.entries:
            parent = os.fstat(entry.parent_fd)
            if (
                not stat.S_ISDIR(parent.st_mode)
                or parent.st_dev != entry.parent_device
                or parent.st_ino != entry.parent_inode
            ):
                raise InvalidInputError(f"{description} parent changed or is unsafe")
            current = os.stat(entry.name, dir_fd=entry.parent_fd, follow_symlinks=False)
            if (
                stat.S_ISLNK(current.st_mode)
                or not stat.S_ISDIR(current.st_mode)
                or current.st_dev != entry.device
                or current.st_ino != entry.inode
            ):
                raise InvalidInputError(f"{description} path component changed or is unsafe")
    except InvalidInputError:
        raise
    except OSError as exc:
        raise InvalidInputError(f"{description} path could not be inspected safely") from exc


def _rename_noreplace(source: str, destination: str, parent_fd: int) -> None:
    """Atomically install ``source`` as ``destination`` only when absent."""

    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except (AttributeError, OSError) as exc:
        raise InvalidInputError("atomic no-replace directory install is unavailable") from exc
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        parent_fd,
        os.fsencode(source),
        parent_fd,
        os.fsencode(destination),
        _RENAME_NOREPLACE,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), destination)


def _directory_signature(fd: int) -> tuple[int, int, int, int]:
    metadata = os.fstat(fd)
    if not stat.S_ISDIR(metadata.st_mode):
        raise InvalidInputError("storage parent is not a directory")
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_ctime_ns,
        metadata.st_mtime_ns,
    )


def _directory_entry_matches(parent_fd: int, name: str, expected: tuple[int, int]) -> bool:
    """Verify a public directory through a fresh no-follow descriptor."""

    fd: int | None = None
    try:
        fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
        metadata = os.fstat(fd)
        lexical = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        return (
            stat.S_ISDIR(metadata.st_mode)
            and not stat.S_ISLNK(lexical.st_mode)
            and stat.S_ISDIR(lexical.st_mode)
            and (metadata.st_dev, metadata.st_ino) == expected
            and (lexical.st_dev, lexical.st_ino) == expected
        )
    except OSError:
        return False
    finally:
        _close_fd(fd)


def _restore_directory_entry(parent_fd: int, public_name: str, staging_name: str) -> None:
    """Move a mismatched public entry back to its private staging name."""

    try:
        os.stat(public_name, dir_fd=parent_fd, follow_symlinks=False)
        try:
            os.stat(staging_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise InvalidInputError("storage staging path unexpectedly exists")
        _rename_noreplace(public_name, staging_name, parent_fd)
        try:
            os.stat(public_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise InvalidInputError("storage target could not be restored safely")
    except InvalidInputError:
        raise
    except OSError as exc:
        raise InvalidInputError("storage target could not be restored safely") from exc


def _open_storage_target(path: Path) -> _StorageTarget:
    parent_chain = _open_directory_chain(path.parent)
    parent_fd = parent_chain.fd
    fd: int | None = None
    try:
        parent_metadata = os.fstat(parent_fd)
        if not stat.S_ISDIR(parent_metadata.st_mode):
            raise InvalidInputError("storage target parent is not a directory")
        name = path.name
        try:
            fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
        except FileNotFoundError:
            return _StorageTarget(
                path,
                parent_fd,
                name,
                parent_metadata.st_dev,
                parent_metadata.st_ino,
                None,
                None,
                None,
                False,
                retained_fds=list(parent_chain.retained_fds),
                parent_chain=parent_chain,
            )
        except OSError as exc:
            raise InvalidInputError("storage target could not be opened safely") from exc
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISDIR(metadata.st_mode):
                raise InvalidInputError("storage target is not a directory")
            return _StorageTarget(
                path,
                parent_fd,
                name,
                parent_metadata.st_dev,
                parent_metadata.st_ino,
                fd,
                metadata.st_dev,
                metadata.st_ino,
                True,
                retained_fds=[*parent_chain.retained_fds, fd],
                parent_chain=parent_chain,
            )
        except InvalidInputError:
            _close_fd(fd)
            raise
        except OSError as exc:
            _close_fd(fd)
            raise InvalidInputError("storage target metadata could not be read") from exc
    except Exception:
        _close_fd(fd)
        for item in reversed(parent_chain.retained_fds):
            _close_fd(item)
        raise


def _target_identity(target: _StorageTarget, *, description: str) -> None:
    try:
        if target.parent_chain is not None:
            _assert_directory_chain(target.parent_chain, description=description)
        parent_metadata = os.fstat(target.parent_fd)
        if (
            not stat.S_ISDIR(parent_metadata.st_mode)
            or parent_metadata.st_dev != target.parent_device
            or parent_metadata.st_ino != target.parent_inode
        ):
            raise InvalidInputError(f"{description} parent changed or is unsafe")
        try:
            metadata = os.stat(target.name, dir_fd=target.parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            metadata = None
        if target.existed:
            if (
                metadata is None
                or stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_dev != target.device
                or metadata.st_ino != target.inode
            ):
                raise InvalidInputError(f"{description} changed or is unsafe")
            if target.fd is None:
                raise InvalidInputError(f"{description} descriptor is missing")
            current = os.fstat(target.fd)
            if current.st_dev != target.device or current.st_ino != target.inode:
                raise InvalidInputError(f"{description} descriptor changed or is unsafe")
        elif metadata is not None:
            raise InvalidInputError(f"{description} appeared before creation")
    except InvalidInputError:
        raise
    except OSError as exc:
        raise InvalidInputError(f"{description} changed or could not be inspected") from exc


def _close_storage_target(target: _StorageTarget) -> None:
    seen: set[int] = set()
    for fd in reversed(target.retained_fds):
        if fd in seen:
            continue
        seen.add(fd)
        _close_fd(fd)


def _capture_layout_identities(target: _StorageTarget, relatives: Sequence[Path]) -> None:
    _target_identity(target, description="storage target")
    if not target.existed or target.fd is None:
        for relative in relatives:
            for index, _component in enumerate(relative.parts):
                target.layout_identities.setdefault(tuple(relative.parts[: index + 1]), None)
        return
    for relative in relatives:
        parent_fd = target.fd
        opened: list[int] = []
        prefix: list[str] = []
        try:
            for component in relative.parts:
                prefix.append(component)
                key = tuple(prefix)
                try:
                    metadata = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    target.layout_identities[key] = None
                    break
                except OSError as exc:
                    raise InvalidInputError("approved storage path could not be inspected") from exc
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                    raise InvalidInputError("approved storage layout contains an unsafe existing path")
                target.layout_identities[key] = (metadata.st_dev, metadata.st_ino)
                if component != relative.parts[-1]:
                    try:
                        child_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=parent_fd)
                    except OSError as exc:
                        raise InvalidInputError("approved storage path could not be opened safely") from exc
                    opened.append(child_fd)
                    parent_fd = child_fd
        finally:
            for fd in reversed(opened):
                _close_fd(fd)


def _descriptor_access(fd: int) -> bool:
    # Linux os.access does not accept a descriptor directly.  /proc/self/fd
    # refers to the already-open inode and therefore cannot be redirected by a
    # replacement of the original pathname.
    return bool(os.access(f"/proc/self/fd/{fd}", os.W_OK))


def _probe_target_metadata(
    target: _StorageTarget,
    probe: Callable[[Path], Any] | None,
) -> tuple[Any, Path]:
    _target_identity(target, description="storage target")
    probe_path = target.path if target.existed else target.path.parent
    try:
        metadata = probe(probe_path) if probe is not None else os.fstat(target.fd or target.parent_fd)
    except (OSError, ValueError, TypeError) as exc:
        raise InvalidInputError("storage target metadata could not be read") from exc
    _target_identity(target, description="storage target")
    return metadata, probe_path


def _check_storage_target(
    target: _StorageTarget,
    *,
    field_name: str,
    uid: int | None,
    gid: int | None,
    stat_probe: Callable[[Path], Any] | None,
    access_probe: Callable[[str | os.PathLike[str], int], bool] | None,
    warnings: list[str],
) -> None:
    metadata, probe_path = _probe_target_metadata(target, stat_probe)
    mode = _stat_value(metadata, "st_mode")
    if mode is not None and not stat.S_ISDIR(mode):
        raise InvalidInputError(f"{field_name} is not a directory")
    if mode is not None and not (int(mode) & 0o222):
        raise InvalidInputError(f"{field_name} is not writable")
    try:
        writable = (
            bool(access_probe(probe_path, os.W_OK))
            if access_probe is not None
            else _descriptor_access(target.fd or target.parent_fd)
        )
    except (OSError, ValueError, TypeError) as exc:
        raise InvalidInputError(f"{field_name} is not writable") from exc
    _target_identity(target, description="storage target")
    if not writable:
        raise InvalidInputError(f"{field_name} is not writable")
    if uid is not None or gid is not None:
        actual_uid = _stat_value(metadata, "st_uid")
        actual_gid = _stat_value(metadata, "st_gid")
        if uid is not None and actual_uid is not None and actual_uid != uid:
            raise InvalidInputError(f"{field_name} owner does not match the requested uid")
        if gid is not None and actual_gid is not None and actual_gid != gid:
            raise InvalidInputError(f"{field_name} group does not match the requested gid")
    elif target.existed:
        warnings.append(f"{field_name} ownership was not explicitly requested")


def _free_target_gib(target: _StorageTarget, probe: Callable[[Path], Any] | None) -> float:
    _target_identity(target, description="storage target")
    probe_path = target.path if target.existed else target.path.parent
    try:
        metadata = probe(probe_path) if probe is not None else os.statvfs(target.fd or target.parent_fd)
    except (OSError, TypeError, ValueError, OverflowError) as exc:
        raise InvalidInputError("free storage capacity could not be read") from exc
    _target_identity(target, description="storage target")
    available = _stat_value(metadata, "f_bavail")
    block = _stat_value(metadata, "f_frsize") or _stat_value(metadata, "f_bsize")
    try:
        available = float(available)
        block = float(block)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidInputError("free storage capacity metadata is invalid") from exc
    if not math.isfinite(available) or not math.isfinite(block) or available < 0 or block <= 0:
        raise InvalidInputError("free storage capacity metadata is invalid")
    return available * block / (1024**3)


def _created_record(
    parent_fd: int,
    name: str,
    path: Path,
) -> tuple[_CreatedDirectory | None, int | None]:
    try:
        # Open the child first relative to the retained parent.  A pathname
        # stat followed by open could observe one inode and adopt another.
        child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        raise InvalidInputError("approved storage path could not be opened safely") from exc
    try:
        child_metadata = os.fstat(child_fd)
        if (
            not stat.S_ISDIR(child_metadata.st_mode)
        ):
            raise InvalidInputError("approved storage layout contains an unsafe existing path")
        lexical = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            stat.S_ISLNK(lexical.st_mode)
            or not stat.S_ISDIR(lexical.st_mode)
            or lexical.st_dev != child_metadata.st_dev
            or lexical.st_ino != child_metadata.st_ino
        ):
            raise InvalidInputError("approved storage path changed during creation")
        record = _CreatedDirectory(path, parent_fd, name, child_metadata.st_dev, child_metadata.st_ino)
        return record, child_fd
    except InvalidInputError:
        _close_fd(child_fd)
        raise
    except OSError as exc:
        _close_fd(child_fd)
        raise InvalidInputError("approved storage path could not be inspected") from exc


def _create_directory_noreplace(
    path: Path,
    *,
    parent_fd: int,
    name: str,
    uid: int | None,
    gid: int | None,
    created: list[_CreatedDirectory],
) -> tuple[int, bool]:
    """Create and configure a directory before atomically installing its name."""

    temporary: str | None = None
    child_fd: int | None = None
    record: _CreatedDirectory | None = None
    parent_after_create: tuple[int, int, int, int] | None = None
    staging: str | None = None
    try:
        parent_before_create = _directory_signature(parent_fd)
        for _ in range(100):
            candidate = f".lumen-installer-{uuid.uuid4().hex}.tmp"
            try:
                os.mkdir(candidate, mode=STORAGE_DIRECTORY_MODE, dir_fd=parent_fd)
            except FileExistsError:
                continue
            temporary = candidate
            break
        if temporary is None:
            raise InvalidInputError("temporary storage directory name could not be allocated")
        parent_after_create = _directory_signature(parent_fd)
        if parent_after_create[:2] != parent_before_create[:2]:
            raise InvalidInputError("storage target parent changed during creation")

        try:
            child_fd = os.open(temporary, _DIRECTORY_FLAGS, dir_fd=parent_fd)
            parent_after_open = _directory_signature(parent_fd)
            if parent_after_create != parent_after_open:
                raise InvalidInputError("temporary storage parent changed during creation")
            metadata = os.fstat(child_fd)
            if not stat.S_ISDIR(metadata.st_mode):
                raise InvalidInputError("temporary storage directory is not a directory")
            expected = (metadata.st_dev, metadata.st_ino)
            os.fchmod(child_fd, STORAGE_DIRECTORY_MODE)
            if uid is not None or gid is not None:
                os.fchown(child_fd, uid if uid is not None else -1, gid if gid is not None else -1)
            configured = os.fstat(child_fd)
            if (configured.st_dev, configured.st_ino) != expected:
                raise InvalidInputError("temporary storage directory changed during creation")
            source = os.stat(temporary, dir_fd=parent_fd, follow_symlinks=False)
            if (
                stat.S_ISLNK(source.st_mode)
                or not stat.S_ISDIR(source.st_mode)
                or (source.st_dev, source.st_ino) != expected
            ):
                raise InvalidInputError("temporary storage directory changed before installation")
            if _directory_signature(parent_fd) != parent_after_open:
                raise InvalidInputError("temporary storage parent changed before installation")

            # Record only the inode that was opened and configured.  If a
            # rename-boundary race moves a different inode, the staged check
            # below catches it before the public target name is installed.
            record = _CreatedDirectory(path, parent_fd, temporary, expected[0], expected[1])
            created.append(record)
            staging = f".lumen-installer-stage-{uuid.uuid4().hex}.tmp"
            _rename_noreplace(temporary, staging, parent_fd)
            record.name = staging
            staged = os.stat(staging, dir_fd=parent_fd, follow_symlinks=False)
            if (
                stat.S_ISLNK(staged.st_mode)
                or not stat.S_ISDIR(staged.st_mode)
                or (staged.st_dev, staged.st_ino) != expected
            ):
                raise InvalidInputError("temporary storage directory changed during staging")
            parent_after_stage = _directory_signature(parent_fd)
            if _directory_signature(parent_fd) != parent_after_stage:
                raise InvalidInputError("temporary storage parent changed during staging")
            staged_again = os.stat(staging, dir_fd=parent_fd, follow_symlinks=False)
            if (
                stat.S_ISLNK(staged_again.st_mode)
                or not stat.S_ISDIR(staged_again.st_mode)
                or (staged_again.st_dev, staged_again.st_ino) != expected
            ):
                raise InvalidInputError("temporary storage directory changed before installation")
            if _directory_signature(parent_fd) != parent_after_stage:
                raise InvalidInputError("temporary storage parent changed before installation")
            final_source = os.stat(staging, dir_fd=parent_fd, follow_symlinks=False)
            if (
                stat.S_ISLNK(final_source.st_mode)
                or not stat.S_ISDIR(final_source.st_mode)
                or (final_source.st_dev, final_source.st_ino) != expected
            ):
                raise InvalidInputError("temporary storage directory changed before installation")
            _rename_noreplace(staging, name, parent_fd)
            # The syscall can race the final source check.  Verify the
            # destination through a fresh descriptor before claiming success;
            # if it is not our inode, move that unverified entry back to the
            # now-free staging name without deleting or following it.
            if not _directory_entry_matches(parent_fd, name, expected):
                try:
                    _restore_directory_entry(parent_fd, name, staging)
                except InvalidInputError:
                    record.name = name
                    raise
                record.name = staging
                raise InvalidInputError("approved storage path changed during installation")
            record.name = name
            return child_fd, True
        except OSError as exc:
            raise InvalidInputError("approved storage layout could not be installed safely") from exc
    except InvalidInputError:
        if child_fd is not None:
            _close_fd(child_fd)
        raise
    except OSError as exc:
        if child_fd is not None:
            _close_fd(child_fd)
        raise InvalidInputError("approved storage layout could not be installed safely") from exc


def _close_created(created: Sequence[_CreatedDirectory]) -> None:
    seen: set[int] = set()
    for record in created:
        if record.parent_fd in seen:
            continue
        seen.add(record.parent_fd)
        _close_fd(record.parent_fd)


def _create_directory_at(
    path: Path,
    *,
    parent_fd: int,
    name: str,
    expected: tuple[int, int] | None,
    uid: int | None,
    gid: int | None,
    created: list[_CreatedDirectory],
    mkdir_probe: Callable[[Path, int], Any] | None = None,
    chmod_probe: Callable[[Path, int], Any] | None = None,
    chown_probe: Callable[[Path, int, int], Any] | None = None,
) -> tuple[int, bool]:
    try:
        succeeded = False
        try:
            existing = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        except OSError as exc:
            raise InvalidInputError("approved storage path could not be inspected") from exc
        if existing is not None:
            if stat.S_ISLNK(existing.st_mode) or not stat.S_ISDIR(existing.st_mode):
                raise InvalidInputError("approved storage layout contains an unsafe existing path")
            if expected is None or (existing.st_dev, existing.st_ino) != expected:
                raise InvalidInputError("approved storage path changed during validation")
            child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
            try:
                child_metadata = os.fstat(child_fd)
                if (child_metadata.st_dev, child_metadata.st_ino) != expected:
                    raise InvalidInputError("approved storage path changed during validation")
                lexical = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if (
                    stat.S_ISLNK(lexical.st_mode)
                    or not stat.S_ISDIR(lexical.st_mode)
                    or (lexical.st_dev, lexical.st_ino) != expected
                ):
                    raise InvalidInputError("approved storage path changed during validation")
                return child_fd, False
            except Exception:
                _close_fd(child_fd)
                raise
        if expected is not None:
            raise InvalidInputError("approved storage path disappeared during validation")
        if mkdir_probe is None and chmod_probe is None and chown_probe is None:
            return _create_directory_noreplace(
                path,
                parent_fd=parent_fd,
                name=name,
                uid=uid,
                gid=gid,
                created=created,
            )
        # A probe is an injected integration boundary.  If it creates a
        # directory and then reports failure, its inode was not captured by
        # the installer and must never be reopened or adopted for rollback.
        if mkdir_probe is None:
            os.mkdir(name, mode=STORAGE_DIRECTORY_MODE, dir_fd=parent_fd)
        else:
            mkdir_probe(path, STORAGE_DIRECTORY_MODE)
        record, child_fd = _created_record(parent_fd, name, path)
        if record is None:
            raise InvalidInputError("approved storage layout could not be created")
        created.append(record)
        try:
            if chmod_probe is not None:
                chmod_probe(path, STORAGE_DIRECTORY_MODE)
            else:
                os.fchmod(child_fd, STORAGE_DIRECTORY_MODE)
            child_metadata = os.fstat(child_fd)
            if child_metadata.st_dev != record.device or child_metadata.st_ino != record.inode:
                raise InvalidInputError("approved storage path changed during creation")
            lexical = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                stat.S_ISLNK(lexical.st_mode)
                or not stat.S_ISDIR(lexical.st_mode)
                or lexical.st_dev != record.device
                or lexical.st_ino != record.inode
            ):
                raise InvalidInputError("approved storage path changed during creation")
            if uid is not None or gid is not None:
                effective_uid = uid if uid is not None else -1
                effective_gid = gid if gid is not None else -1
                if chown_probe is not None:
                    chown_probe(path, effective_uid, effective_gid)
                else:
                    os.fchown(child_fd, effective_uid, effective_gid)
                child_metadata = os.fstat(child_fd)
                if child_metadata.st_dev != record.device or child_metadata.st_ino != record.inode:
                    raise InvalidInputError("approved storage path changed during ownership update")
                lexical = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if (
                    stat.S_ISLNK(lexical.st_mode)
                    or not stat.S_ISDIR(lexical.st_mode)
                    or lexical.st_dev != record.device
                    or lexical.st_ino != record.inode
                ):
                    raise InvalidInputError("approved storage path changed during ownership update")
            succeeded = True
            return child_fd, True
        finally:
            if not succeeded:
                _close_fd(child_fd)
    except FileExistsError as exc:
        # A concurrent creator owns a directory that appeared between the
        # preflight check and mkdir; never claim or remove it during rollback.
        raise InvalidInputError("approved storage layout could not be created") from exc
    except Exception as exc:
        raise InvalidInputError("approved storage layout could not be created") from exc


def _apply_target_layout(
    target: _StorageTarget,
    relatives: Sequence[Path],
    *,
    uid: int | None,
    gid: int | None,
    created: list[_CreatedDirectory],
    mkdir_probe: Callable[[Path, int], Any] | None,
    chmod_probe: Callable[[Path, int], Any] | None,
    chown_probe: Callable[[Path, int, int], Any] | None,
) -> None:
    """Create one target and its layout using only retained descriptors."""

    _target_identity(target, description="storage target")
    if not target.existed:
        child_fd, _ = _create_directory_at(
            target.path,
            parent_fd=target.parent_fd,
            name=target.name,
            expected=None,
            uid=uid,
            gid=gid,
            created=created,
            mkdir_probe=mkdir_probe,
            chmod_probe=chmod_probe,
            chown_probe=chown_probe,
        )
        target.fd = child_fd
        target.retained_fds.append(child_fd)
        metadata = os.fstat(child_fd)
        target.device = metadata.st_dev
        target.inode = metadata.st_ino
        target.existed = True
    _target_identity(target, description="storage target")
    if target.fd is None:
        raise InvalidInputError("storage target descriptor is missing")
    for relative in relatives:
        parent_fd = target.fd
        prefix: list[str] = []
        for component in relative.parts:
            prefix.append(component)
            key = tuple(prefix)
            expected = target.layout_identities.get(key)
            child_path = target.path.joinpath(*prefix)
            child_fd, _ = _create_directory_at(
                child_path,
                parent_fd=parent_fd,
                name=component,
                expected=expected,
                uid=uid,
                gid=gid,
                created=created,
                mkdir_probe=mkdir_probe,
                chmod_probe=chmod_probe,
                chown_probe=chown_probe,
            )
            target.retained_fds.append(child_fd)
            child_metadata = os.fstat(child_fd)
            target.layout_identities[key] = (child_metadata.st_dev, child_metadata.st_ino)
            parent_fd = child_fd
        _target_identity(target, description="storage target")


def _rollback_created(
    created: Sequence[_CreatedDirectory],
    *,
    remove_probe: Callable[[Path], Any] | None = None,
) -> tuple[str, ...]:
    partial: list[str] = []
    for record in reversed(created):
        path = record.path
        try:
            try:
                metadata = os.stat(record.name, dir_fd=record.parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                partial.append(str(path))
                continue
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_dev != record.device
                or metadata.st_ino != record.inode
            ):
                partial.append(str(path))
                continue
            child_fd = os.open(record.name, _DIRECTORY_FLAGS, dir_fd=record.parent_fd)
            try:
                child_metadata = os.fstat(child_fd)
                if child_metadata.st_dev != record.device or child_metadata.st_ino != record.inode:
                    partial.append(str(path))
                    continue
                if os.listdir(child_fd):
                    partial.append(str(path))
                    continue
            finally:
                try:
                    os.close(child_fd)
                except OSError:
                    pass
            if remove_probe is not None:
                remove_probe(path)
                try:
                    os.stat(record.name, dir_fd=record.parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    partial.append(str(path))
            else:
                # Linux has no unlink-by-open-directory-fd primitive.  A
                # pathname rmdir remains vulnerable to replacement after the
                # identity check, so report the installer-owned path as a
                # partial rollback instead of deleting an uncertain inode.
                partial.append(str(path))
        except Exception:
            partial.append(str(path))
    return tuple(partial)


def validate_storage(
    root_path: str | os.PathLike[str] | None,
    downloads_path: str | os.PathLike[str] | None,
    *,
    repo_root: str | os.PathLike[str] | None = None,
    uid: int | None = None,
    gid: int | None = None,
    required_free_gib: float = 0.0,
    dry_run: bool = False,
    stat_probe: Callable[[Path], Any] | None = None,
    statvfs_probe: Callable[[Path], Any] | None = None,
    access_probe: Callable[[str | os.PathLike[str], int], bool] | None = None,
    mkdir_probe: Callable[[Path, int], Any] | None = None,
    chmod_probe: Callable[[Path, int], Any] | None = None,
    chown_probe: Callable[[Path, int, int], Any] | None = None,
    remove_probe: Callable[[Path], Any] | None = None,
    **kwargs: Any,
) -> StorageValidation:
    """Validate and, unless dry-run, create the approved media foundation.

    ``stat_probe``, ``statvfs_probe`` and ``access_probe`` are intentionally
    injectable so doctor/setup tests can exercise capacity, owner and
    writeability decisions without changing a host filesystem.
    """

    if "minimum_free_gib" in kwargs:
        required_free_gib = kwargs.pop("minimum_free_gib")
    if "min_free_gib" in kwargs:
        required_free_gib = kwargs.pop("min_free_gib")
    if "expected_uid" in kwargs:
        uid = kwargs.pop("expected_uid")
    if "expected_gid" in kwargs:
        gid = kwargs.pop("expected_gid")
    for option, target in (
        ("mkdir_fn", "mkdir_probe"),
        ("chmod_fn", "chmod_probe"),
        ("chown_fn", "chown_probe"),
        ("remove_fn", "remove_probe"),
    ):
        if option in kwargs:
            if target == "mkdir_probe":
                mkdir_probe = kwargs.pop(option)
            elif target == "chmod_probe":
                chmod_probe = kwargs.pop(option)
            elif target == "chown_probe":
                chown_probe = kwargs.pop(option)
            else:
                remove_probe = kwargs.pop(option)
    if kwargs:
        raise TypeError(f"unexpected storage validation option: {next(iter(kwargs))}")
    if repo_root is None:
        raise InvalidInputError("repository root must be explicitly supplied")
    root = _as_absolute_path(root_path, field_name="ROOT_PATH")
    downloads = _as_absolute_path(downloads_path, field_name="DOWNLOADS_PATH")
    repo = _as_absolute_path(repo_root, field_name="repository root")
    _validate_target_safety(root, downloads, repo)
    try:
        required = float(required_free_gib)
    except (TypeError, ValueError) as exc:
        raise InvalidInputError("required free storage must be numeric") from exc
    if not math.isfinite(required) or required < 0:
        raise InvalidInputError("required free storage must be nonnegative")
    if uid is not None and (type(uid) is not int or uid < 0):
        raise InvalidInputError("requested uid is invalid")
    if gid is not None and (type(gid) is not int or gid < 0):
        raise InvalidInputError("requested gid is invalid")

    approved: list[Path] = [root, downloads]
    approved.extend(root / relative for relative in MEDIA_SUBDIRECTORIES)
    approved.extend(downloads / relative for relative in DOWNLOAD_SUBDIRECTORIES)
    # A deterministic parent-before-child order prevents partial layout
    # creation from ever requiring a broad recursive mkdir.
    approved = list(dict.fromkeys(approved))
    root_target = _open_storage_target(root)
    try:
        downloads_target = _open_storage_target(downloads)
    except Exception:
        _close_storage_target(root_target)
        raise
    created: list[_CreatedDirectory] = []
    warnings: list[str] = []
    try:
        _capture_layout_identities(root_target, MEDIA_SUBDIRECTORIES)
        _capture_layout_identities(downloads_target, DOWNLOAD_SUBDIRECTORIES)
        _check_storage_target(
            root_target,
            field_name="ROOT_PATH",
            uid=uid,
            gid=gid,
            stat_probe=stat_probe,
            access_probe=access_probe,
            warnings=warnings,
        )
        _check_storage_target(
            downloads_target,
            field_name="DOWNLOADS_PATH",
            uid=uid,
            gid=gid,
            stat_probe=stat_probe,
            access_probe=access_probe,
            warnings=warnings,
        )
        free = {
            "root": _free_target_gib(root_target, statvfs_probe),
            "downloads": _free_target_gib(downloads_target, statvfs_probe),
        }
        if any(value < required for value in free.values()):
            raise InvalidInputError("storage does not have the required free capacity")
        if not dry_run:
            try:
                _apply_target_layout(
                    root_target,
                    (),
                    uid=uid,
                    gid=gid,
                    created=created,
                    mkdir_probe=mkdir_probe,
                    chmod_probe=chmod_probe,
                    chown_probe=chown_probe,
                )
                _apply_target_layout(
                    downloads_target,
                    (),
                    uid=uid,
                    gid=gid,
                    created=created,
                    mkdir_probe=mkdir_probe,
                    chmod_probe=chmod_probe,
                    chown_probe=chown_probe,
                )
                _apply_target_layout(
                    root_target,
                    MEDIA_SUBDIRECTORIES,
                    uid=uid,
                    gid=gid,
                    created=created,
                    mkdir_probe=mkdir_probe,
                    chmod_probe=chmod_probe,
                    chown_probe=chown_probe,
                )
                _apply_target_layout(
                    downloads_target,
                    DOWNLOAD_SUBDIRECTORIES,
                    uid=uid,
                    gid=gid,
                    created=created,
                    mkdir_probe=mkdir_probe,
                    chmod_probe=chmod_probe,
                    chown_probe=chown_probe,
                )
            except Exception as exc:
                partial = _rollback_created(created, remove_probe=remove_probe)
                if partial:
                    raise StorageMutationError("storage layout rollback was incomplete", partial) from exc
                if isinstance(exc, InvalidInputError):
                    raise
                raise InvalidInputError("approved storage layout could not be created") from exc
        else:
            warnings.append("dry-run: approved layout was not created")
        created_paths = tuple(record.path for record in created)
        return StorageValidation(
            root_path=root,
            downloads_path=downloads,
            approved_paths=tuple(approved),
            created_paths=created_paths,
            free_gib=free,
            warnings=tuple(warnings),
            decisions=(),
            dry_run=dry_run,
        )
    finally:
        _close_created(created)
        _close_storage_target(root_target)
        _close_storage_target(downloads_target)


# ---------------------------------------------------------------------------
# Compose worktree-rot guard

KNOWN_STACK_CONTAINER_NAMES = frozenset(
    {
        "jellyfin",
        "qbittorrent",
        "radarr",
        "sonarr",
        "prowlarr",
        "flaresolverr",
        "bazarr",
        "jellyseerr",
        "unpackerr",
        "recyclarr",
        "maintainerr",
        "homepage-actions",
        "ai-recommendations",
        "dashboard",
    }
)


@dataclass(frozen=True, repr=False)
class StaleContainer:
    _identifier: str
    name: str
    working_dir: str

    @property
    def execution_identifier(self) -> str:
        """Return the exact Docker ID for internal removal execution only."""

        return self._identifier

    @property
    def execution_argv(self) -> tuple[str, ...]:
        """Return an argv vector for internal lifecycle code."""

        return ("docker", "rm", "-f", self._identifier)

    @property
    def plan(self) -> dict[str, Any]:
        return {"name": self.name, "action": "remove-confirmed-stale-container"}

    @property
    def report(self) -> dict[str, Any]:
        return self.plan

    def __repr__(self) -> str:
        return f"StaleContainer(name={self.name!r}, working_dir_present={bool(self.working_dir)!r})"


def _container_rows(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, (str, bytes, bytearray)):
        try:
            decoded = json.loads(value)
        except (TypeError, UnicodeError, json.JSONDecodeError):
            return ()
        value = decoded
    if isinstance(value, Mapping):
        # A single docker inspect object is accepted, as is an id->object map.
        if "Config" in value or "config" in value or "Name" in value or "name" in value:
            return (value,)
        values = tuple(item for item in value.values() if isinstance(item, Mapping))
        return values
    if isinstance(value, Sequence):
        return tuple(item for item in value if isinstance(item, Mapping))
    return ()


def _labels(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    top_level = row.get("Labels", row.get("labels"))
    if isinstance(top_level, Mapping):
        return top_level
    config = row.get("Config", row.get("config"))
    if not isinstance(config, Mapping):
        return None
    labels = config.get("Labels", config.get("labels"))
    return labels if isinstance(labels, Mapping) else None


def find_stale_containers(
    inspected: Any,
    repo_root: str | os.PathLike[str],
    *,
    known_names: Iterable[str] = KNOWN_STACK_CONTAINER_NAMES,
    project_name: str | None = None,
    **kwargs: Any,
) -> tuple[StaleContainer, ...]:
    """Return removal plans for containers from a dead Compose checkout.

    This function is deliberately read-only.  It requires the exact name,
    Compose project/service labels and a working directory whose checkout no
    longer contains ``.git``; foreign/malformed metadata is skipped safely.
    """

    if "known_container_names" in kwargs:
        known_names = kwargs.pop("known_container_names")
    if "compose_project" in kwargs:
        project_name = kwargs.pop("compose_project")
    if kwargs:
        raise TypeError(f"unexpected stale-container option: {next(iter(kwargs))}")
    repo = _as_absolute_path(repo_root, field_name="repository root")
    names = frozenset(item for item in known_names if isinstance(item, str))
    if project_name is None:
        projects = None
    elif isinstance(project_name, str) and project_name:
        projects = frozenset({project_name})
    else:
        return ()
    # Running from anything other than a real checkout is not safe enough to
    # infer ownership of containers.  Git worktrees may represent .git as a
    # file, therefore existence (not is_dir()) is intentional here.
    if not (repo / ".git").exists():
        return ()
    canonical_repo = repo.resolve(strict=False)
    stale: list[StaleContainer] = []
    for row in _container_rows(inspected):
        raw_name = row.get("Name", row.get("name"))
        if not isinstance(raw_name, str):
            continue
        name = raw_name[1:] if raw_name.startswith("/") else raw_name
        if name not in names:
            continue
        labels = _labels(row)
        if labels is None:
            continue
        compose_project = labels.get("com.docker.compose.project")
        if not isinstance(compose_project, str) or not compose_project.strip():
            continue
        if projects is not None and compose_project not in projects:
            continue
        if labels.get("com.docker.compose.service") != name:
            continue
        working_dir = labels.get("com.docker.compose.project.working_dir")
        identifier = row.get("Id", row.get("ID", row.get("id")))
        if not isinstance(working_dir, str) or not working_dir.strip() or not isinstance(identifier, str) or not identifier:
            continue
        try:
            checkout = Path(working_dir).expanduser()
            if not checkout.is_absolute():
                continue
            if checkout.resolve(strict=False) == canonical_repo:
                continue
            # Existing PowerShell guard treats a checkout as live only when
            # its .git marker remains.  Resolve only for the existence check;
            # retain the original non-secret path in the removal plan.
            if checkout.exists() and (checkout / ".git").exists():
                continue
        except (OSError, RuntimeError, ValueError):
            continue
        if not re.fullmatch(r"[0-9a-fA-F]{12,64}", identifier):
            continue
        stale.append(StaleContainer(_identifier=identifier, name=name, working_dir=working_dir))
    return tuple(stale)


__all__ = [
    "DOWNLOAD_SUBDIRECTORIES",
    "KNOWN_STACK_CONTAINER_NAMES",
    "MEDIA_SUBDIRECTORIES",
    "STORAGE_DIRECTORY_MODE",
    "StaleContainer",
    "StorageMutationError",
    "StorageValidation",
    "find_stale_containers",
    "validate_storage",
]
