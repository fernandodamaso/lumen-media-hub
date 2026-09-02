"""Safe host storage validation and read-only stale-container discovery."""

from __future__ import annotations

import json
import math
import os
import re
import stat
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
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


@dataclass
class _CreatedDirectory:
    path: Path
    parent_fd: int
    name: str
    device: int
    inode: int


def _open_absolute_directory(path: Path) -> int:
    """Walk an absolute path one component at a time without symlinks."""

    fd: int | None = None
    try:
        fd = os.open(os.path.sep, _DIRECTORY_FLAGS)
        for component in path.parts[1:]:
            next_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except OSError as exc:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        raise InvalidInputError("storage parent could not be opened safely") from exc


def _created_record(
    parent_fd: int,
    name: str,
    path: Path,
) -> tuple[_CreatedDirectory | None, int | None]:
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        raise InvalidInputError("approved storage path could not be inspected") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise InvalidInputError("approved storage layout contains an unsafe existing path")
    record = _CreatedDirectory(path, parent_fd, name, metadata.st_dev, metadata.st_ino)
    try:
        child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError:
        return record, None
    try:
        child_metadata = os.fstat(child_fd)
        if (
            not stat.S_ISDIR(child_metadata.st_mode)
            or child_metadata.st_dev != record.device
            or child_metadata.st_ino != record.inode
        ):
            raise InvalidInputError("approved storage path changed during creation")
    except InvalidInputError:
        try:
            os.close(child_fd)
        except OSError:
            pass
        raise
    except OSError as exc:
        try:
            os.close(child_fd)
        except OSError:
            pass
        raise InvalidInputError("approved storage path could not be inspected") from exc
    return record, child_fd


def _close_created(created: Sequence[_CreatedDirectory]) -> None:
    for record in created:
        try:
            os.close(record.parent_fd)
        except OSError:
            pass


def _create_directory(
    path: Path,
    *,
    uid: int | None,
    gid: int | None,
    created: list[_CreatedDirectory],
    mkdir_probe: Callable[[Path, int], Any] | None = None,
    chmod_probe: Callable[[Path, int], Any] | None = None,
    chown_probe: Callable[[Path, int, int], Any] | None = None,
) -> None:
    _reject_symlink_components(path, field_name="approved storage path")
    parent_fd = _open_absolute_directory(path.parent)
    name = path.name
    made = False
    try:
        try:
            existing = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        except OSError as exc:
            raise InvalidInputError("approved storage path could not be inspected") from exc
        if existing is not None:
            if stat.S_ISLNK(existing.st_mode) or not stat.S_ISDIR(existing.st_mode):
                raise InvalidInputError("approved storage layout contains an unsafe existing path")
            return
        # A test/integration probe may create the directory before reporting
        # an error.  Mark the attempt before invoking it so that the stable
        # parent descriptor can discover and roll back that inode.
        made = True
        if mkdir_probe is None:
            os.mkdir(name, mode=STORAGE_DIRECTORY_MODE, dir_fd=parent_fd)
        else:
            mkdir_probe(path, STORAGE_DIRECTORY_MODE)
        record, child_fd = _created_record(parent_fd, name, path)
        if record is None:
            raise InvalidInputError("approved storage layout could not be created")
        created.append(record)
        parent_fd = -1
        if child_fd is None:
            raise InvalidInputError("approved storage path could not be opened safely")
        try:
            if chmod_probe is not None:
                chmod_probe(path, STORAGE_DIRECTORY_MODE)
            else:
                os.fchmod(child_fd, STORAGE_DIRECTORY_MODE)
            if uid is not None or gid is not None:
                effective_uid = uid if uid is not None else -1
                effective_gid = gid if gid is not None else -1
                if chown_probe is not None:
                    chown_probe(path, effective_uid, effective_gid)
                else:
                    os.fchown(child_fd, effective_uid, effective_gid)
        finally:
            try:
                os.close(child_fd)
            except OSError:
                pass
    except FileExistsError as exc:
        # A concurrent creator owns a directory that appeared between the
        # preflight check and mkdir; never claim or remove it during rollback.
        raise InvalidInputError("approved storage layout could not be created") from exc
    except Exception as exc:
        # A probe may model a mkdir that created its directory before
        # reporting an error.  Track that path through the stable parent
        # descriptor so rollback never follows a replacement symlink.
        if made and parent_fd >= 0:
            try:
                record, child_fd = _created_record(parent_fd, name, path)
                if child_fd is not None:
                    os.close(child_fd)
                if record is not None:
                    created.append(record)
                    parent_fd = -1
            except Exception:
                pass
        raise InvalidInputError("approved storage layout could not be created") from exc
    finally:
        if parent_fd >= 0:
            try:
                os.close(parent_fd)
            except OSError:
                pass


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
            else:
                os.rmdir(record.name, dir_fd=record.parent_fd)
            try:
                os.stat(record.name, dir_fd=record.parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                partial.append(str(path))
        except Exception:
            partial.append(str(path))
        finally:
            try:
                os.close(record.parent_fd)
            except OSError:
                pass
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

    warnings: list[str] = []
    _check_existing_or_parent(
        root,
        field_name="ROOT_PATH",
        uid=uid,
        gid=gid,
        stat_probe=stat_probe,
        access_probe=access_probe,
        warnings=warnings,
    )
    _check_existing_or_parent(
        downloads,
        field_name="DOWNLOADS_PATH",
        uid=uid,
        gid=gid,
        stat_probe=stat_probe,
        access_probe=access_probe,
        warnings=warnings,
    )
    free = {
        "root": _free_gib(_nearest_existing(root), statvfs_probe),
        "downloads": _free_gib(_nearest_existing(downloads), statvfs_probe),
    }
    if any(value < required for value in free.values()):
        raise InvalidInputError("storage does not have the required free capacity")

    approved: list[Path] = [root, downloads]
    approved.extend(root / relative for relative in MEDIA_SUBDIRECTORIES)
    approved.extend(downloads / relative for relative in DOWNLOAD_SUBDIRECTORIES)
    # A deterministic parent-before-child order prevents partial layout
    # creation from ever requiring a broad recursive mkdir.
    approved = list(dict.fromkeys(approved))
    created: list[_CreatedDirectory] = []
    if not dry_run:
        try:
            for path in approved:
                _create_directory(
                    path,
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
    _close_created(created)
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
