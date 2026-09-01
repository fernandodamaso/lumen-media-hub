"""Durable, secret-free state for the Linux installer.

The installer deliberately keeps its state small.  It records only choices
and identifiers owned by the installer; credentials and service configuration
remain in their existing stores.  State is written as one deterministic JSON
document and replaced atomically so an interrupted write cannot turn an
adopted install into a fresh install.
"""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .errors import InvalidInputError


STATE_SCHEMA_VERSION = 1
STATE_DIR_NAME = ".state/installer"
STATE_FILE_NAME = "state.json"
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
    return root.resolve(strict=False) / STATE_DIR_NAME


def state_path(repo_root: str | os.PathLike[str]) -> Path:
    return state_directory(repo_root) / STATE_FILE_NAME


def _normalise_path_target(target: str | os.PathLike[str]) -> tuple[Path | None, Path]:
    path = Path(target).expanduser()
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
        return ()
    if isinstance(profiles, (str, bytes)) or not isinstance(profiles, Sequence):
        raise InvalidInputError("installer state profiles must be a list")
    values = [_validate_identifier(item, field_name="profile") for item in profiles]
    if len(values) != len(set(values)) or any(item not in KNOWN_PROFILES for item in values):
        raise InvalidInputError("installer state contains invalid or duplicate profiles")
    return tuple(sorted(values))


def _normalise_owned_resources(value: Any) -> dict[str, str] | tuple[str, ...]:
    if value is None:
        return {}
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
        return ()
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
            object.__setattr__(self, "repo_root", root.resolve(strict=False))
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
        return self.as_dict()

    @property
    def redacted(self) -> dict[str, Any]:
        return self.as_dict()

    def __repr__(self) -> str:
        return (
            "InstallerState("
            f"profiles={self.profiles!r}, gpu_mode={self.gpu_mode!r}, "
            f"owned_resources_count={len(self.owned_resources)}, "
            f"completed_stages={self.completed_stages!r})"
        )

    @classmethod
    def from_dict(cls, value: Any, *, repo_root: Path | None = None) -> "InstallerState":
        if not isinstance(value, Mapping):
            raise InvalidInputError("installer state must be a JSON object")
        common = {"schema_version", "profiles", "gpu_mode", "completed_stages"}
        resource_keys = {"owned_resources", "owned_resource_ids"}
        if set(value) - common - resource_keys or not (set(value) & resource_keys):
            raise InvalidInputError("installer state has an invalid schema")
        if len(set(value) & resource_keys) != 1:
            raise InvalidInputError("installer state has duplicate resource fields")
        schema = value.get("schema_version")
        if type(schema) is not int or schema != STATE_SCHEMA_VERSION:
            raise InvalidInputError("unsupported installer state schema")
        return cls(
            repo_root=repo_root,
            schema_version=schema,
            profiles=value.get("profiles"),
            gpu_mode=value.get("gpu_mode"),
            owned_resources=value.get("owned_resources", value.get("owned_resource_ids")),
            completed_stages=value.get("completed_stages"),
        )

    @classmethod
    def load(cls, target: str | os.PathLike[str]) -> "InstallerState":
        repo, path = _normalise_path_target(target)
        if repo is None:
            if path.parent.name != "installer" or path.parent.parent.name != ".state":
                raise InvalidInputError("installer state must stay below .state/installer")
            repo = path.parent.parent.parent
        repo = Path(repo).expanduser()
        if not repo.is_absolute():
            raise InvalidInputError("repository root must be an absolute path")
        repo = repo.resolve(strict=False)
        directory = state_directory(repo)
        if directory.is_symlink() or path.is_symlink():
            raise InvalidInputError("installer state path must not be a symlink")
        if directory.exists() and not directory.is_dir():
            raise InvalidInputError("installer state directory is not a directory")
        if directory.parent.exists() and not directory.parent.is_dir():
            raise InvalidInputError("installer state parent is not a directory")
        if not path.exists():
            return cls(repo_root=repo)
        try:
            raw = path.read_text(encoding="utf-8")
            decoded = json.loads(raw)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise InvalidInputError("installer state is corrupt or unreadable") from exc
        return cls.from_dict(decoded, repo_root=repo)

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
        if parent_root.is_symlink() or parent.parent.is_symlink() or parent.is_symlink():
            raise InvalidInputError("installer state path must not be a symlink")
        if not parent_root.exists() or not parent_root.is_dir():
            raise InvalidInputError("installer state parent is not a directory")
        state_parent = parent.parent
        if state_parent.is_symlink():
            raise InvalidInputError("installer state path must not be a symlink")
        try:
            state_parent.mkdir(mode=0o700, exist_ok=True)
            parent.mkdir(mode=0o700, exist_ok=True)
        except OSError as exc:
            raise InvalidInputError("installer state directory could not be created") from exc
        if not state_parent.is_dir():
            raise InvalidInputError("installer state parent is not a directory")
        os.chmod(state_parent, 0o700)
        os.chmod(parent, 0o700)
        payload = json.dumps(self.as_dict(), ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        fd, temporary = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=str(parent))
        temporary_path = Path(temporary)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, path)
            try:
                directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
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
                    os.close(directory_fd)
            os.chmod(path, 0o600)
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
        self._state = (
            state_or_target
            if isinstance(state_or_target, InstallerState)
            else InstallerState.load(state_or_target)
        )
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
        if stage in self.completed:
            return False
        expected = self.stages[len(self.completed)]
        if stage != expected:
            raise InvalidInputError("installer stages must be completed in order")
        candidate = replace(self._state, completed_stages=self.completed + (stage,))
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
    "StageJournal",
    "state_directory",
    "state_path",
]
