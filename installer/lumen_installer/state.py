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
import tempfile
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


def _lstat(path: Path, *, description: str) -> os.stat_result | None:
    try:
        result = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise InvalidInputError(f"{description} could not be inspected") from exc
    if stat.S_ISLNK(result.st_mode):
        raise InvalidInputError(f"{description} must not be a symlink")
    return result


def _ensure_repo_and_state_paths(repo: Path, *, create: bool, correct_modes: bool) -> Path:
    """Validate repo-relative state components without following symlinks."""

    repo = _lexical_absolute(repo)
    repo_stat = _lstat(repo, description="repository root")
    if repo_stat is None or not stat.S_ISDIR(repo_stat.st_mode):
        raise InvalidInputError("repository root must be an existing directory")
    state_parent = repo / ".state"
    installer_dir = state_parent / "installer"
    for directory, description in ((state_parent, "installer state parent"), (installer_dir, "installer state directory")):
        metadata = _lstat(directory, description=description)
        if metadata is None:
            if not create:
                continue
            try:
                directory.mkdir(mode=0o700)
            except FileExistsError:
                # Another journal thread may have created this component
                # between lstat and mkdir.  Re-lstat below decides whether it
                # is the expected directory or an unsafe replacement.
                pass
            except OSError as exc:
                raise InvalidInputError(f"{description} could not be created") from exc
            metadata = _lstat(directory, description=description)
        if metadata is None or not stat.S_ISDIR(metadata.st_mode):
            raise InvalidInputError(f"{description} is not a directory")
        if correct_modes and stat.S_IMODE(metadata.st_mode) != 0o700:
            try:
                os.chmod(directory, 0o700)
            except OSError as exc:
                raise InvalidInputError(f"{description} permissions could not be restricted") from exc
    lock_path = installer_dir / STATE_LOCK_NAME
    lock_metadata = _lstat(lock_path, description="installer state lock")
    if lock_metadata is not None:
        if not stat.S_ISREG(lock_metadata.st_mode):
            raise InvalidInputError("installer state lock is not regular")
        if correct_modes and stat.S_IMODE(lock_metadata.st_mode) != 0o600:
            try:
                os.chmod(lock_path, 0o600)
            except OSError as exc:
                raise InvalidInputError("installer state lock permissions could not be restricted") from exc
    return installer_dir


def _validate_state_file(path: Path, *, correct_mode: bool) -> None:
    metadata = _lstat(path, description="installer state file")
    if metadata is None:
        return
    if not stat.S_ISREG(metadata.st_mode):
        raise InvalidInputError("installer state file is not regular")
    if correct_mode and stat.S_IMODE(metadata.st_mode) != 0o600:
        try:
            os.chmod(path, 0o600)
        except OSError as exc:
            raise InvalidInputError("installer state file permissions could not be restricted") from exc


@contextmanager
def _state_lock(repo: Path):
    """Take an advisory process lock on the installer state directory."""

    directory = _ensure_repo_and_state_paths(repo, create=True, correct_modes=True)
    lock_path = directory / STATE_LOCK_NAME
    _lstat(lock_path, description="installer state lock")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise InvalidInputError("installer state lock could not be opened") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise InvalidInputError("installer state lock is not regular")
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    except OSError as exc:
        raise InvalidInputError("installer state lock could not be acquired") from exc
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            # The state mutation (if any) has already committed.  A close
            # failure must not make StageJournal report a failed completion.
            pass


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
        if allowed_stages is not None:
            allowed = tuple(_validate_identifier(stage, field_name="allowed stage") for stage in allowed_stages)
            if len(allowed) != len(set(allowed)):
                raise InvalidInputError("allowed installer stages contain duplicates")
            if any(stage not in allowed for stage in completed):
                raise InvalidInputError("installer state contains an unknown completed stage")
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
        directory = _ensure_repo_and_state_paths(repo, create=False, correct_modes=True)
        _validate_state_file(path, correct_mode=True)
        if not path.exists():
            return cls(repo_root=repo)
        try:
            raw = path.read_text(encoding="utf-8")
            decoded = json.loads(raw)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise InvalidInputError("installer state is corrupt or unreadable") from exc
        return cls.from_dict(decoded, repo_root=repo, allowed_stages=allowed_stages)

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
        parent = _ensure_repo_and_state_paths(parent_root, create=True, correct_modes=True)
        path = parent / STATE_FILE_NAME
        _validate_state_file(path, correct_mode=True)
        payload = json.dumps(self.as_dict(), ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        fd, temporary = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=str(parent))
        temporary_path = Path(temporary)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            # Set the path mode before replacement.  There is intentionally no
            # fallible chmod of the destination after os.replace: a failure
            # must never report an error after the new state is installed.
            os.chmod(temporary_path, 0o600)
            # A pre-rename parent sync is allowed to fail: in that case the
            # old state name is still present and the caller receives the
            # failure without losing it.  The post-rename sync below is
            # best-effort, matching dotenv's atomic-write contract.
            directory_fd = os.open(str(parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            os.replace(temporary_path, path)
            try:
                directory_fd = os.open(str(parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            except OSError:
                directory_fd = None
            if directory_fd is not None:
                try:
                    os.fsync(directory_fd)
                except OSError:
                    # The rename already happened.  Do not claim persistence
                    # failed after the new state became durable enough to read.
                    pass
                finally:
                    try:
                        os.close(directory_fd)
                    except OSError:
                        # The destination has already been replaced; closing
                        # the best-effort fsync descriptor must not turn a
                        # successful state commit into a reported failure.
                        pass
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
            raise
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
            state_file = state_path(self._state.repo_root)
            persisted_exists = _lstat(state_file, description="installer state file") is not None
            current = InstallerState.load(self._state.repo_root, allowed_stages=self.stages)
            if not persisted_exists:
                current = self._state
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
