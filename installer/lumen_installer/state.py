"""Durable, secret-free state for the Linux installer.

The installer deliberately keeps its state small.  It records only choices
and identifiers owned by the installer; credentials and service configuration
remain in their existing stores.  State is written as one deterministic JSON
document and replaced atomically so an interrupted write cannot turn an
adopted install into a fresh install.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import uuid
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .errors import InvalidInputError


STATE_SCHEMA_VERSION = 1
STATE_DIR_NAME = ".state/installer"
STATE_FILE_NAME = "state.json"
STATE_LOCK_NAME = "state.lock"
KNOWN_PROFILES = frozenset({"subtitles", "requests", "maintenance", "indexer-tools", "ai"})
KNOWN_GPU_MODES = frozenset({"none", "auto", "nvidia", "vaapi"})
DEFAULT_STAGES = (
    "host",
    "environment",
    "network",
    "storage",
    "preflight",
    "compose",
)

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,254}$")
_SECRET_FIELD = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|client[_-]?secret|oauth|cookie|credential)",
    re.IGNORECASE,
)


def state_directory(repo_root: str | os.PathLike[str]) -> Path:
    """Return the installer state directory for an absolute checkout path."""

    root = Path(repo_root).expanduser()
    if not root.is_absolute():
        raise InvalidInputError("repository root must be an absolute path")
    return Path(os.path.abspath(str(root))) / STATE_DIR_NAME


def state_path(repo_root: str | os.PathLike[str]) -> Path:
    return state_directory(repo_root) / STATE_FILE_NAME


def _lexical_absolute(path: Path) -> Path:
    """Normalize ``..`` without resolving symlink components."""

    return Path(os.path.abspath(str(path)))


_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


@dataclass(frozen=True)
class _StateHandles:
    repo_fd: int
    state_fd: int
    installer_fd: int
    repo_path: Path

    @property
    def state_path(self) -> Path:
        return self.repo_path / ".state"

    @property
    def installer_path(self) -> Path:
        return self.state_path / "installer"


def _close_fd(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def _open_absolute_directory(path: Path, *, description: str) -> int:
    """Walk an absolute path one component at a time without symlinks."""

    if not path.is_absolute():
        raise InvalidInputError(f"{description} must be an absolute path")
    try:
        fd = os.open(os.path.sep, _DIRECTORY_FLAGS)
        for component in path.parts[1:]:
            next_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=fd)
            _close_fd(fd)
            fd = next_fd
        return fd
    except OSError as exc:
        if "fd" in locals():
            _close_fd(fd)
        raise InvalidInputError(f"{description} could not be opened safely") from exc


def _open_directory_child(
    parent_fd: int,
    name: str,
    *,
    create: bool,
    mode: int,
    description: str,
) -> int | None:
    try:
        fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            return None
        try:
            os.mkdir(name, mode=mode, dir_fd=parent_fd)
        except FileExistsError:
            pass
        except OSError as exc:
            raise InvalidInputError(f"{description} could not be created") from exc
        try:
            fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
        except OSError as exc:
            raise InvalidInputError(f"{description} could not be opened safely") from exc
    except OSError as exc:
        raise InvalidInputError(f"{description} could not be opened safely") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISDIR(metadata.st_mode):
            raise InvalidInputError(f"{description} is not a directory")
        if stat.S_IMODE(metadata.st_mode) != mode:
            os.fchmod(fd, mode)
    except InvalidInputError:
        _close_fd(fd)
        raise
    except OSError as exc:
        _close_fd(fd)
        raise InvalidInputError(f"{description} permissions could not be restricted") from exc
    return fd


def _restrict_existing_lock(installer_fd: int) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(STATE_LOCK_NAME, flags, dir_fd=installer_fd)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise InvalidInputError("installer state lock could not be opened safely") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise InvalidInputError("installer state lock is not regular")
        os.fchmod(fd, 0o600)
    except InvalidInputError:
        raise
    except OSError as exc:
        raise InvalidInputError("installer state lock permissions could not be restricted") from exc
    finally:
        _close_fd(fd)


@contextmanager
def _state_components(repo: Path, *, create: bool, correct_modes: bool):
    """Open state components by descriptor and reject symlink replacement."""

    repo = _lexical_absolute(repo)
    repo_fd: int | None = None
    state_fd: int | None = None
    installer_fd: int | None = None
    try:
        repo_fd = _open_absolute_directory(repo, description="repository root")
        state_fd = _open_directory_child(
            repo_fd,
            ".state",
            create=create,
            mode=0o700,
            description="installer state parent",
        )
        if state_fd is None:
            yield None
            return
        installer_fd = _open_directory_child(
            state_fd,
            "installer",
            create=create,
            mode=0o700,
            description="installer state directory",
        )
        if installer_fd is None:
            yield None
            return
        if correct_modes:
            _restrict_existing_lock(installer_fd)
        yield _StateHandles(repo_fd, state_fd, installer_fd, repo)
    finally:
        _close_fd(installer_fd)
        _close_fd(state_fd)
        _close_fd(repo_fd)


def _assert_state_identity(path: Path, fd: int, *, description: str) -> None:
    try:
        current = os.stat(path, follow_symlinks=False)
        expected = os.fstat(fd)
    except OSError as exc:
        raise InvalidInputError(f"{description} changed or could not be inspected") from exc
    if not stat.S_ISDIR(current.st_mode) or current.st_dev != expected.st_dev or current.st_ino != expected.st_ino:
        raise InvalidInputError(f"{description} changed or is unsafe")


def _ensure_repo_and_state_paths(repo: Path, *, create: bool, correct_modes: bool) -> Path:
    """Validate state components through descriptor-relative operations."""

    with _state_components(repo, create=create, correct_modes=correct_modes) as handles:
        return (handles.installer_path if handles is not None else _lexical_absolute(repo) / STATE_DIR_NAME)


def _open_state_file(installer_fd: int) -> int | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(STATE_FILE_NAME, flags, dir_fd=installer_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise InvalidInputError("installer state file could not be opened safely") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise InvalidInputError("installer state file is not regular")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            os.fchmod(fd, 0o600)
    except InvalidInputError:
        _close_fd(fd)
        raise
    except OSError as exc:
        _close_fd(fd)
        raise InvalidInputError("installer state file permissions could not be restricted") from exc
    return fd


def _read_state(handles: _StateHandles) -> str | None:
    fd = _open_state_file(handles.installer_fd)
    if fd is None:
        return None
    try:
        stream = os.fdopen(fd, "r", encoding="utf-8")
        fd = -1
        with stream:
            return stream.read()
    except (OSError, UnicodeError) as exc:
        raise InvalidInputError("installer state is corrupt or unreadable") from exc
    finally:
        _close_fd(fd)


def _create_temp_state_file(installer_fd: int) -> tuple[int, str]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for _ in range(100):
        name = f".state-{uuid.uuid4().hex}.tmp"
        try:
            fd = os.open(name, flags, 0o600, dir_fd=installer_fd)
        except FileExistsError:
            continue
        except OSError as exc:
            raise InvalidInputError("temporary installer state file could not be created") from exc
        try:
            os.fchmod(fd, 0o600)
        except OSError as exc:
            _close_fd(fd)
            try:
                os.unlink(name, dir_fd=installer_fd)
            except OSError:
                pass
            raise exc
        return fd, name
    raise InvalidInputError("temporary installer state file name could not be allocated")


@contextmanager
def _state_lock(repo: Path):
    """Take an advisory process lock on the installer state directory."""

    with _state_components(repo, create=True, correct_modes=True) as handles:
        if handles is None:
            raise InvalidInputError("installer state directory could not be opened")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(STATE_LOCK_NAME, flags, 0o600, dir_fd=handles.installer_fd)
        except OSError as exc:
            raise InvalidInputError("installer state lock could not be opened") from exc
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise InvalidInputError("installer state lock is not regular")
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            _assert_state_identity(handles.installer_path, handles.installer_fd, description="installer state directory")
            try:
                lock_stat = os.stat(STATE_LOCK_NAME, dir_fd=handles.installer_fd, follow_symlinks=False)
            except OSError as exc:
                raise InvalidInputError("installer state lock changed or could not be inspected") from exc
            if lock_stat.st_dev != metadata.st_dev or lock_stat.st_ino != metadata.st_ino:
                raise InvalidInputError("installer state lock changed or is unsafe")
            yield handles
        except OSError as exc:
            raise InvalidInputError("installer state lock could not be acquired") from exc
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            _close_fd(fd)


def _normalise_path_target(target: str | os.PathLike[str]) -> tuple[Path | None, Path]:
    path = _lexical_absolute(Path(target).expanduser())
    if path.name == STATE_FILE_NAME and path.suffix == ".json":
        return path.parent.parent.parent if path.parent.name == "installer" else None, path
    if path.name == "installer" and path.parent.name == ".state":
        return path.parent.parent, path / STATE_FILE_NAME
    return path, state_path(path)


def _validate_identifier(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or not _SAFE_IDENTIFIER.fullmatch(value):
        raise InvalidInputError(f"invalid installer state {field_name}")
    if _SECRET_FIELD.search(value):
        raise InvalidInputError(f"secret-like installer state {field_name} is not permitted")
    return value


def _normalise_profiles(profiles: Any) -> tuple[str, ...]:
    if profiles is None:
        raise InvalidInputError("installer state profiles must be a list")
    if isinstance(profiles, (str, bytes)) or not isinstance(profiles, Sequence):
        raise InvalidInputError("installer state profiles must be a list")
    values = [_validate_identifier(item, field_name="profile") for item in profiles]
    if len(values) != len(set(values)) or any(item not in KNOWN_PROFILES for item in values):
        raise InvalidInputError("installer state contains invalid or duplicate profiles")
    return tuple(sorted(values))


def _normalise_owned_resources(value: Any) -> dict[str, str] | tuple[str, ...]:
    if value is None:
        raise InvalidInputError("installer state owned resources must be a list or object")
    if isinstance(value, Mapping):
        result: dict[str, str] = {}
        for key, item in value.items():
            name = _validate_identifier(key, field_name="resource name")
            identifier = _validate_identifier(item, field_name="resource identifier")
            if name in result:
                raise InvalidInputError("duplicate installer state resource")
            result[name] = identifier
        return dict(sorted(result.items()))
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidInputError("installer state owned resources must be a list or object")
    values = tuple(_validate_identifier(item, field_name="resource identifier") for item in value)
    if len(values) != len(set(values)):
        raise InvalidInputError("installer state contains duplicate resources")
    return tuple(sorted(values))


def _normalise_stages(value: Any) -> tuple[str, ...]:
    if value is None:
        raise InvalidInputError("installer state completed stages must be a list")
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidInputError("installer state completed stages must be a list")
    values = tuple(_validate_identifier(item, field_name="stage") for item in value)
    if len(values) != len(set(values)):
        raise InvalidInputError("installer state contains duplicate completed stages")
    return values


def _normalise_stage_registry(value: Sequence[str] | None) -> tuple[str, ...]:
    registry = DEFAULT_STAGES if value is None else value
    if isinstance(registry, (str, bytes)) or not isinstance(registry, Sequence) or not registry:
        raise InvalidInputError("installer stage registry must be a non-empty ordered list")
    stages = tuple(_validate_identifier(stage, field_name="allowed stage") for stage in registry)
    if len(stages) != len(set(stages)):
        raise InvalidInputError("allowed installer stages contain duplicates")
    return stages


def _decode_state(
    raw: str,
    *,
    repo_root: Path,
    allowed_stages: Sequence[str] | None,
) -> "InstallerState":
    try:
        decoded = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidInputError("installer state is corrupt or unreadable") from exc
    return InstallerState.from_dict(decoded, repo_root=repo_root, allowed_stages=allowed_stages)


@dataclass(frozen=True, repr=False)
class InstallerState:
    """Schema-versioned installer choices and owned-resource identifiers."""

    repo_root: Path | None = field(default=None, compare=False, repr=False)
    profiles: tuple[str, ...] = ()
    gpu_mode: str = "none"
    owned_resources: Mapping[str, str] | Sequence[str] = field(default_factory=dict)
    completed_stages: tuple[str, ...] = ()
    schema_version: int = STATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != STATE_SCHEMA_VERSION:
            raise InvalidInputError("unsupported installer state schema")
        if self.repo_root is not None:
            root = Path(self.repo_root).expanduser()
            if not root.is_absolute():
                raise InvalidInputError("repository root must be an absolute path")
            if root.name == "installer" and root.parent.name == ".state":
                root = root.parent.parent
            object.__setattr__(self, "repo_root", _lexical_absolute(root))
        object.__setattr__(self, "profiles", _normalise_profiles(self.profiles))
        mode = self.gpu_mode
        if not isinstance(mode, str) or mode not in KNOWN_GPU_MODES:
            raise InvalidInputError("invalid installer GPU mode")
        object.__setattr__(self, "gpu_mode", mode)
        object.__setattr__(self, "owned_resources", _normalise_owned_resources(self.owned_resources))
        object.__setattr__(self, "completed_stages", _normalise_stages(self.completed_stages))

    @property
    def owned_resource_identifiers(self) -> Mapping[str, str] | Sequence[str]:
        """Compatibility spelling used by later lifecycle code."""

        return self.owned_resources

    @property
    def owned_resource_ids(self) -> Mapping[str, str] | Sequence[str]:
        return self.owned_resources

    @property
    def selected_profiles(self) -> tuple[str, ...]:
        return self.profiles

    @property
    def gpu(self) -> str:
        return self.gpu_mode

    @property
    def path(self) -> Path:
        if self.repo_root is None:
            raise InvalidInputError("installer state has no repository root")
        return state_path(self.repo_root)

    def as_dict(self) -> dict[str, Any]:
        resources: Any
        if isinstance(self.owned_resources, Mapping):
            resources = dict(sorted(self.owned_resources.items()))
        else:
            resources = list(self.owned_resources)
        return {
            "completed_stages": list(self.completed_stages),
            "gpu_mode": self.gpu_mode,
            "owned_resources": resources,
            "profiles": list(self.profiles),
            "schema_version": STATE_SCHEMA_VERSION,
        }

    @property
    def report(self) -> dict[str, Any]:
        resources = self.owned_resources
        return {
            "completed_stages": list(self.completed_stages),
            "gpu_mode": self.gpu_mode,
            "owned_resources": {
                "count": len(resources),
                "kind": "mapping" if isinstance(resources, Mapping) else "list",
            },
            "profiles": list(self.profiles),
            "schema_version": STATE_SCHEMA_VERSION,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    def __repr__(self) -> str:
        return (
            "InstallerState("
            f"profiles={self.profiles!r}, gpu_mode={self.gpu_mode!r}, "
            f"owned_resources_count={len(self.owned_resources)}, "
            f"completed_stages={self.completed_stages!r})"
        )

    @classmethod
    def from_dict(
        cls,
        value: Any,
        *,
        repo_root: Path | None = None,
        allowed_stages: Sequence[str] | None = None,
    ) -> "InstallerState":
        if not isinstance(value, Mapping):
            raise InvalidInputError("installer state must be a JSON object")
        required = {"schema_version", "profiles", "gpu_mode", "owned_resources", "completed_stages"}
        if set(value) != required:
            raise InvalidInputError("installer state has an invalid schema")
        schema = value.get("schema_version")
        if type(schema) is not int or schema != STATE_SCHEMA_VERSION:
            raise InvalidInputError("unsupported installer state schema")
        if type(value.get("profiles")) is not list:
            raise InvalidInputError("installer state profiles must be a list")
        if not isinstance(value.get("gpu_mode"), str):
            raise InvalidInputError("installer state GPU mode must be a string")
        resources = value.get("owned_resources")
        if not isinstance(resources, (Mapping, list)):
            raise InvalidInputError("installer state owned resources must be a list or object")
        completed = value.get("completed_stages")
        if type(completed) is not list:
            raise InvalidInputError("installer state completed stages must be a list")
        allowed = _normalise_stage_registry(allowed_stages)
        if any(stage not in allowed for stage in completed):
            raise InvalidInputError("installer state contains an unknown completed stage")
        if tuple(completed) != allowed[: len(completed)]:
            raise InvalidInputError("installer stages are out of order")
        return cls(
            repo_root=repo_root,
            schema_version=schema,
            profiles=value.get("profiles"),
            gpu_mode=value.get("gpu_mode"),
            owned_resources=resources,
            completed_stages=completed,
        )

    @classmethod
    def load(
        cls,
        target: str | os.PathLike[str],
        *,
        allowed_stages: Sequence[str] | None = None,
    ) -> "InstallerState":
        repo, path = _normalise_path_target(target)
        if repo is None:
            if path.parent.name != "installer" or path.parent.parent.name != ".state":
                raise InvalidInputError("installer state must stay below .state/installer")
            repo = path.parent.parent.parent
        repo = Path(repo).expanduser()
        if not repo.is_absolute():
            raise InvalidInputError("repository root must be an absolute path")
        repo = _lexical_absolute(repo)
        with _state_components(repo, create=False, correct_modes=True) as handles:
            if handles is None:
                return cls(repo_root=repo)
            _assert_state_identity(handles.state_path, handles.state_fd, description="installer state parent")
            _assert_state_identity(handles.installer_path, handles.installer_fd, description="installer state directory")
            raw = _read_state(handles)
        if raw is None:
            return cls(repo_root=repo)
        return _decode_state(raw, repo_root=repo, allowed_stages=allowed_stages)

    @classmethod
    def new(cls, repo_root: str | os.PathLike[str], **kwargs: Any) -> "InstallerState":
        return cls(repo_root=Path(repo_root), **kwargs)

    def save(self, target: str | os.PathLike[str] | None = None) -> Path:
        path = self.path if target is None else _normalise_path_target(target)[1]
        if not path.is_absolute():
            raise InvalidInputError("installer state path must be absolute")
        parent = path.parent
        if parent.name != "installer" or parent.parent.name != ".state":
            raise InvalidInputError("installer state must stay below .state/installer")
        parent_root = parent.parent.parent
        payload = json.dumps(self.as_dict(), ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        with _state_components(parent_root, create=True, correct_modes=True) as handles:
            if handles is None:
                raise InvalidInputError("installer state directory could not be opened")
            _assert_state_identity(handles.state_path, handles.state_fd, description="installer state parent")
            _assert_state_identity(handles.installer_path, handles.installer_fd, description="installer state directory")
            existing_fd = _open_state_file(handles.installer_fd)
            _close_fd(existing_fd)
            fd, temporary = _create_temp_state_file(handles.installer_fd)
            replaced = False
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                    fd = -1
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                # The mode is applied to the open temporary inode before it
                # can become visible as state.json.  No destination chmod is
                # needed or allowed after the atomic rename.
                os.fsync(handles.installer_fd)
                _assert_state_identity(handles.state_path, handles.state_fd, description="installer state parent")
                _assert_state_identity(handles.installer_path, handles.installer_fd, description="installer state directory")
                os.replace(
                    temporary,
                    STATE_FILE_NAME,
                    src_dir_fd=handles.installer_fd,
                    dst_dir_fd=handles.installer_fd,
                )
                replaced = True
                # The post-rename directory sync is best effort, matching
                # dotenv's atomic-write contract.  The state is already
                # installed and must not be reported as failed here.
                try:
                    os.fsync(handles.installer_fd)
                except OSError:
                    pass
                _assert_state_identity(handles.state_path, handles.state_fd, description="installer state parent")
                _assert_state_identity(handles.installer_path, handles.installer_fd, description="installer state directory")
            finally:
                _close_fd(fd)
                if not replaced:
                    try:
                        os.unlink(temporary, dir_fd=handles.installer_fd)
                    except FileNotFoundError:
                        pass
                    except OSError:
                        # Cleanup is descriptor-relative and therefore cannot
                        # remove a replacement outside this state directory.
                        pass
        return path

    persist = save


class StageJournal:
    """Ordered, resumable stage journal backed by :class:`InstallerState`."""

    def __init__(
        self,
        state_or_target: InstallerState | str | os.PathLike[str],
        stages: Sequence[str] | None = None,
        *,
        stage_order: Sequence[str] | None = None,
    ) -> None:
        if stages is not None and stage_order is not None:
            raise TypeError("provide only one stage ordering")
        selected = (
            DEFAULT_STAGES
            if stages is None and stage_order is None
            else (stages if stages is not None else stage_order)
        )
        if isinstance(selected, (str, bytes)) or not selected:
            raise InvalidInputError("stage journal requires an ordered stage list")
        self.stages = tuple(_validate_identifier(item, field_name="stage") for item in selected)
        if len(self.stages) != len(set(self.stages)):
            raise InvalidInputError("stage journal has duplicate stage names")
        self._state = (
            state_or_target
            if isinstance(state_or_target, InstallerState)
            else InstallerState.load(state_or_target, allowed_stages=self.stages)
        )
        completed = self._state.completed_stages
        if any(item not in self.stages for item in completed):
            raise InvalidInputError("installer state contains an unknown completed stage")
        if completed != self.stages[: len(completed)]:
            raise InvalidInputError("installer stages are out of order")

    @property
    def state(self) -> InstallerState:
        return self._state

    @property
    def completed(self) -> tuple[str, ...]:
        return self._state.completed_stages

    @property
    def completed_stages(self) -> tuple[str, ...]:
        return self.completed

    @property
    def pending(self) -> tuple[str, ...]:
        return self.stages[len(self.completed) :]

    def is_complete(self, stage: str) -> bool:
        if stage not in self.stages:
            raise InvalidInputError("unknown installer stage")
        return stage in self.completed

    def complete(self, stage: str) -> bool:
        if stage not in self.stages:
            raise InvalidInputError("unknown installer stage")
        if self._state.repo_root is None:
            raise InvalidInputError("stage journal has no repository root")
        with _state_lock(self._state.repo_root):
            with _state_components(self._state.repo_root, create=False, correct_modes=True) as handles:
                if handles is None:
                    current = self._state
                else:
                    raw = _read_state(handles)
                    current = (
                        self._state
                        if raw is None
                        else _decode_state(raw, repo_root=self._state.repo_root, allowed_stages=self.stages)
                    )
            completed = current.completed_stages
            if any(item not in self.stages for item in completed):
                raise InvalidInputError("installer state contains an unknown completed stage")
            if completed != self.stages[: len(completed)]:
                raise InvalidInputError("installer stages are out of order")
            if stage in completed:
                self._state = current
                return False
            expected = self.stages[len(completed)]
            if stage != expected:
                raise InvalidInputError("installer stages must be completed in order")
            candidate = replace(current, completed_stages=completed + (stage,))
            candidate.save()
            self._state = candidate
            return True

    mark_complete = complete

    def resume(self) -> tuple[str, ...]:
        return self.pending

    @property
    def next_stage(self) -> str | None:
        return self.pending[0] if self.pending else None


__all__ = [
    "DEFAULT_STAGES",
    "InstallerState",
    "KNOWN_GPU_MODES",
    "KNOWN_PROFILES",
    "STATE_DIR_NAME",
    "STATE_FILE_NAME",
    "STATE_LOCK_NAME",
    "StageJournal",
    "state_directory",
    "state_path",
]
