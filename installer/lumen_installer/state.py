"""Durable, secret-free state for the Linux installer.

The installer deliberately keeps its state small.  It records only choices
and identifiers owned by the installer; credentials and service configuration
remain in their existing stores.  State is written as one deterministic JSON
document and replaced atomically so an interrupted write cannot turn an
adopted install into a fresh install.
"""

from __future__ import annotations

import ctypes
import fcntl
import json
import os
import re
import stat
import time
import uuid
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .errors import InvalidInputError, PartialError


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
_RENAME_NOREPLACE = 1
_RENAME_EXCHANGE = 2
@dataclass(frozen=True)
class _StateDirectoryChainEntry:
    parent_fd: int
    name: str
    parent_device: int
    parent_inode: int
    device: int
    inode: int


@dataclass
class _StateDirectoryChain:
    fd: int
    entries: tuple[_StateDirectoryChainEntry, ...]
    retained_fds: list[int]


@dataclass(frozen=True)
class _StateHandles:
    repo_fd: int
    state_fd: int
    installer_fd: int
    repo_path: Path
    repo_chain: _StateDirectoryChain | None = None

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


def _open_directory_chain(path: Path, *, description: str) -> _StateDirectoryChain:
    """Open an absolute directory while retaining its component descriptors."""

    if not path.is_absolute():
        raise InvalidInputError(f"{description} must be an absolute path")
    retained: list[int] = []
    entries: list[_StateDirectoryChainEntry] = []
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
                raise InvalidInputError(f"{description} is not a directory")
            entries.append(
                _StateDirectoryChainEntry(
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
        return _StateDirectoryChain(fd, tuple(entries), retained)
    except InvalidInputError:
        for item in reversed(retained):
            _close_fd(item)
        raise
    except OSError as exc:
        for item in reversed(retained):
            _close_fd(item)
        raise InvalidInputError(f"{description} could not be opened safely") from exc


def _assert_state_chain(chain: _StateDirectoryChain, *, description: str) -> None:
    """Verify each lexical component still names the retained directory."""

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


def _assert_state_entry(parent_fd: int, name: str, fd: int, *, description: str) -> None:
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        expected = os.fstat(fd)
    except OSError as exc:
        raise InvalidInputError(f"{description} changed or could not be inspected") from exc
    if (
        stat.S_ISLNK(current.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or current.st_dev != expected.st_dev
        or current.st_ino != expected.st_ino
    ):
        raise InvalidInputError(f"{description} changed or is unsafe")


def _assert_state_components_identity(handles: _StateHandles) -> None:
    if handles.repo_chain is not None:
        _assert_state_chain(handles.repo_chain, description="repository root")
    _assert_state_entry(handles.repo_fd, ".state", handles.state_fd, description="installer state parent")
    _assert_state_entry(handles.state_fd, "installer", handles.installer_fd, description="installer state directory")


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


def _rename_exchange(source: str, destination: str, parent_fd: int) -> None:
    """Atomically exchange two entries in one retained directory."""

    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except (AttributeError, OSError) as exc:
        raise InvalidInputError("atomic state rollback is unavailable") from exc
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        parent_fd,
        os.fsencode(source),
        parent_fd,
        os.fsencode(destination),
        _RENAME_EXCHANGE,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), destination)


def _directory_signature(fd: int) -> tuple[int, int, int, int]:
    metadata = os.fstat(fd)
    if not stat.S_ISDIR(metadata.st_mode):
        raise InvalidInputError("installer state parent is not a directory")
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_ctime_ns,
        metadata.st_mtime_ns,
    )


def _regular_file_matches(parent_fd: int, name: str, expected: tuple[int, int]) -> bool:
    """Verify a regular state file through a fresh no-follow descriptor."""

    fd: int | None = None
    try:
        fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
        metadata = os.fstat(fd)
        lexical = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        return (
            stat.S_ISREG(metadata.st_mode)
            and not stat.S_ISLNK(lexical.st_mode)
            and stat.S_ISREG(lexical.st_mode)
            and (metadata.st_dev, metadata.st_ino) == expected
            and (lexical.st_dev, lexical.st_ino) == expected
        )
    except OSError:
        return False
    finally:
        _close_fd(fd)


def _directory_entry_matches(parent_fd: int, name: str, expected: tuple[int, int]) -> bool:
    """Verify a state directory through a fresh no-follow descriptor."""

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


def _restore_state_entry(parent_fd: int, public_name: str, staging_name: str) -> None:
    """Preserve a mismatched public inode by moving it to the temp name."""

    try:
        os.stat(public_name, dir_fd=parent_fd, follow_symlinks=False)
        try:
            os.stat(staging_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise InvalidInputError("installer state staging path unexpectedly exists")
        _rename_noreplace(public_name, staging_name, parent_fd)
        try:
            os.stat(public_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise InvalidInputError("installer state could not be restored safely")
    except InvalidInputError:
        raise
    except OSError as exc:
        raise InvalidInputError("installer state could not be restored safely") from exc


def _create_state_backup(parent_fd: int, expected: tuple[int, int]) -> tuple[str, tuple[int, int]]:
    """Create a same-directory hard-link restore artifact before replacement."""

    for _ in range(100):
        name = f".state-backup-{uuid.uuid4().hex}.tmp"
        try:
            os.link(
                STATE_FILE_NAME,
                name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            continue
        except OSError as exc:
            raise InvalidInputError("installer state backup could not be created safely") from exc
        if not _regular_file_matches(parent_fd, name, expected):
            raise InvalidInputError("installer state backup changed during creation")
        return name, expected
    raise InvalidInputError("installer state backup name could not be allocated")


def _restore_state_from_backup(parent_fd: int, backup: str, backup_identity: tuple[int, int]) -> None:
    if not _regular_file_matches(parent_fd, backup, backup_identity):
        raise InvalidInputError("installer state backup changed during rollback")
    try:
        os.link(
            backup,
            STATE_FILE_NAME,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise InvalidInputError("installer state could not be restored safely") from exc
    if not _regular_file_matches(parent_fd, STATE_FILE_NAME, backup_identity):
        raise InvalidInputError("installer state could not be restored safely")


def _restore_state_after_replace(
    parent_fd: int,
    temporary: str,
    backup: str | None,
    backup_identity: tuple[int, int] | None,
) -> None:
    """Restore the old state from its prevalidated same-directory artifact."""

    # Exchange the mismatched public inode with the prevalidated backup in one
    # syscall. The external inode is preserved at the private backup name and
    # the prior state becomes public without creating another temp file.
    if backup is None or backup_identity is None:
        _restore_state_entry(parent_fd, STATE_FILE_NAME, temporary)
        return
    if not _regular_file_matches(parent_fd, backup, backup_identity):
        raise InvalidInputError("installer state backup changed during rollback")
    try:
        _rename_exchange(STATE_FILE_NAME, backup, parent_fd)
    except (InvalidInputError, OSError):
        # A failure may have happened before the exchange syscall, leaving the
        # external inode public. Quarantine it under a fresh private name and
        # restore the prevalidated artifact directly. If the exchange did
        # complete before reporting failure, the identity check avoids a
        # second mutation.
        if _regular_file_matches(parent_fd, STATE_FILE_NAME, backup_identity):
            return
        quarantine = f".state-recovery-{uuid.uuid4().hex}.tmp"
        try:
            _restore_state_entry(parent_fd, STATE_FILE_NAME, quarantine)
            _restore_state_from_backup(parent_fd, backup, backup_identity)
        except (InvalidInputError, OSError) as recovery_error:
            raise PartialError(
                "installer state rollback incomplete: state.json may still reference unverified content"
            ) from recovery_error
        return
    if not _regular_file_matches(parent_fd, STATE_FILE_NAME, backup_identity):
        raise InvalidInputError("installer state could not be restored safely")


def _create_directory_noreplace(parent_fd: int, name: str, *, mode: int, description: str) -> int:
    """Prepare a directory under a private name, then install it atomically."""

    temporary: str | None = None
    staging: str | None = None
    child_fd: int | None = None
    expected: tuple[int, int] | None = None
    parent_after_create: tuple[int, int, int, int] | None = None
    try:
        parent_before_create = _directory_signature(parent_fd)
        for _ in range(100):
            candidate = f".{name}-{uuid.uuid4().hex}.tmp"
            try:
                os.mkdir(candidate, mode=mode, dir_fd=parent_fd)
            except FileExistsError:
                continue
            temporary = candidate
            break
        if temporary is None:
            raise InvalidInputError(f"temporary {description} name could not be allocated")
        parent_after_create = _directory_signature(parent_fd)
        if parent_after_create[:2] != parent_before_create[:2]:
            raise InvalidInputError(f"{description} parent changed during creation")

        child_fd = os.open(temporary, _DIRECTORY_FLAGS, dir_fd=parent_fd)
        parent_after_open = _directory_signature(parent_fd)
        if parent_after_open != parent_after_create:
            raise InvalidInputError(f"temporary {description} parent changed during creation")
        metadata = os.fstat(child_fd)
        if not stat.S_ISDIR(metadata.st_mode):
            raise InvalidInputError(f"temporary {description} is not a directory")
        expected = (metadata.st_dev, metadata.st_ino)
        os.fchmod(child_fd, mode)
        configured = os.fstat(child_fd)
        if (configured.st_dev, configured.st_ino) != expected:
            raise InvalidInputError(f"temporary {description} changed during creation")
        source = os.stat(temporary, dir_fd=parent_fd, follow_symlinks=False)
        if (
            stat.S_ISLNK(source.st_mode)
            or not stat.S_ISDIR(source.st_mode)
            or (source.st_dev, source.st_ino) != expected
        ):
            raise InvalidInputError(f"temporary {description} changed before installation")
        if _directory_signature(parent_fd) != parent_after_open:
            raise InvalidInputError(f"{description} parent changed before installation")

        # Stage first so a source swap at the rename boundary cannot put an
        # unverified inode at the public .state path.
        staging = f".{name}-stage-{uuid.uuid4().hex}.tmp"
        _rename_noreplace(temporary, staging, parent_fd)
        # Capture the post-rename parent identity before any pathname read so
        # a failure in the first staging stat still identifies the private
        # candidate for diagnostics; it is never pathname-deleted on failure.
        parent_after_stage = _directory_signature(parent_fd)
        try:
            lexical = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            lexical = None
        # The name still does not exist; validate the staged entry instead.
        staged = os.stat(staging, dir_fd=parent_fd, follow_symlinks=False)
        if (
            stat.S_ISLNK(staged.st_mode)
            or not stat.S_ISDIR(staged.st_mode)
            or (staged.st_dev, staged.st_ino) != expected
        ):
            raise InvalidInputError(f"temporary {description} changed during staging")
        if lexical is not None:
            raise InvalidInputError(f"{description} appeared during installation")
        if _directory_signature(parent_fd) != parent_after_stage:
            raise InvalidInputError(f"{description} parent changed during staging")
        staged_again = os.stat(staging, dir_fd=parent_fd, follow_symlinks=False)
        if (
            stat.S_ISLNK(staged_again.st_mode)
            or not stat.S_ISDIR(staged_again.st_mode)
            or (staged_again.st_dev, staged_again.st_ino) != expected
        ):
            raise InvalidInputError(f"temporary {description} changed before installation")
        if _directory_signature(parent_fd) != parent_after_stage:
            raise InvalidInputError(f"{description} parent changed before installation")
        final_source = os.stat(staging, dir_fd=parent_fd, follow_symlinks=False)
        if (
            stat.S_ISLNK(final_source.st_mode)
            or not stat.S_ISDIR(final_source.st_mode)
            or (final_source.st_dev, final_source.st_ino) != expected
        ):
            raise InvalidInputError(f"temporary {description} changed before installation")
        _rename_noreplace(staging, name, parent_fd)
        if not _directory_entry_matches(parent_fd, name, expected):
            try:
                _restore_state_entry(parent_fd, name, staging)
            except InvalidInputError:
                raise
            raise InvalidInputError(f"{description} changed during installation")
        return child_fd
    except InvalidInputError:
        _close_fd(child_fd)
        raise
    except OSError as exc:
        _close_fd(child_fd)
        raise InvalidInputError(f"{description} could not be installed safely") from exc


def _open_directory_child(
    parent_fd: int,
    name: str,
    *,
    create: bool,
    mode: int,
    correct_mode: bool = True,
    description: str,
) -> int | None:
    try:
        fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            return None
        return _create_directory_noreplace(parent_fd, name, mode=mode, description=description)
    except OSError as exc:
        raise InvalidInputError(f"{description} could not be opened safely") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISDIR(metadata.st_mode):
            raise InvalidInputError(f"{description} is not a directory")
        lexical = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            stat.S_ISLNK(lexical.st_mode)
            or not stat.S_ISDIR(lexical.st_mode)
            or lexical.st_dev != metadata.st_dev
            or lexical.st_ino != metadata.st_ino
        ):
            raise InvalidInputError(f"{description} changed during creation")
        if correct_mode and stat.S_IMODE(metadata.st_mode) != mode:
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
    repo_chain: _StateDirectoryChain | None = None
    state_fd: int | None = None
    installer_fd: int | None = None
    repo_creation_locked = False
    try:
        repo_chain = _open_directory_chain(repo, description="repository root")
        repo_fd = repo_chain.fd
        if create:
            try:
                # Directory creation has no returned fd.  Serialize the
                # no-replace install across processes using the stable repo
                # directory, so a concurrent creator is not mistaken for an
                # attacker-provided replacement.
                fcntl.flock(repo_fd, fcntl.LOCK_EX)
                repo_creation_locked = True
            except OSError as exc:
                raise InvalidInputError("installer state creation lock could not be acquired") from exc
        state_fd = _open_directory_child(
            repo_fd,
            ".state",
            create=create,
            mode=0o700,
            correct_mode=correct_modes,
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
            correct_mode=correct_modes,
            description="installer state directory",
        )
        if installer_fd is None:
            yield None
            return
        if correct_modes:
            _restrict_existing_lock(installer_fd)
        handles = _StateHandles(repo_fd, state_fd, installer_fd, repo, repo_chain)
        _assert_state_components_identity(handles)
        yield handles
    finally:
        _close_fd(installer_fd)
        _close_fd(state_fd)
        if repo_chain is None:
            _close_fd(repo_fd)
        else:
            if repo_creation_locked:
                try:
                    fcntl.flock(repo_fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            for item in reversed(repo_chain.retained_fds):
                _close_fd(item)


def _assert_state_identity(path: Path, fd: int, *, description: str) -> None:
    try:
        current = os.stat(path, follow_symlinks=False)
        expected = os.fstat(fd)
    except OSError as exc:
        raise InvalidInputError(f"{description} changed or could not be inspected") from exc
    if not stat.S_ISDIR(current.st_mode) or current.st_dev != expected.st_dev or current.st_ino != expected.st_ino:
        raise InvalidInputError(f"{description} changed or is unsafe")


def _open_state_file(installer_fd: int, *, correct_mode: bool = True) -> int | None:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        lexical = os.stat(STATE_FILE_NAME, dir_fd=installer_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise InvalidInputError("installer state file could not be inspected safely") from exc
    if stat.S_ISLNK(lexical.st_mode) or not stat.S_ISREG(lexical.st_mode):
        raise InvalidInputError("installer state file is not regular")
    try:
        fd = os.open(STATE_FILE_NAME, flags, dir_fd=installer_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise InvalidInputError("installer state file could not be opened safely") from exc
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino) != (lexical.st_dev, lexical.st_ino)
        ):
            raise InvalidInputError("installer state file is not regular")
        current = os.stat(STATE_FILE_NAME, dir_fd=installer_fd, follow_symlinks=False)
        if (
            stat.S_ISLNK(current.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino)
        ):
            raise InvalidInputError("installer state file changed during opening")
        if correct_mode and stat.S_IMODE(metadata.st_mode) != 0o600:
            os.fchmod(fd, 0o600)
    except InvalidInputError:
        _close_fd(fd)
        raise
    except OSError as exc:
        _close_fd(fd)
        raise InvalidInputError("installer state file permissions could not be restricted") from exc
    return fd


def _read_state(handles: _StateHandles, *, correct_mode: bool = True) -> str | None:
    _assert_state_components_identity(handles)
    fd = _open_state_file(handles.installer_fd, correct_mode=correct_mode)
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


def _create_temp_state_file(installer_fd: int) -> tuple[int, str, tuple[int, int]]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for _ in range(100):
        name = f".state-{uuid.uuid4().hex}.tmp"
        try:
            fd = os.open(name, flags, 0o600, dir_fd=installer_fd)
        except FileExistsError:
            continue
        except OSError as exc:
            raise InvalidInputError("temporary installer state file could not be created") from exc
        expected: tuple[int, int] | None = None
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise InvalidInputError("temporary installer state file is not regular")
            expected = (metadata.st_dev, metadata.st_ino)
        except InvalidInputError:
            _close_fd(fd)
            raise
        except OSError as exc:
            _close_fd(fd)
            raise InvalidInputError("temporary installer state file metadata could not be read") from exc
        try:
            os.fchmod(fd, 0o600)
        except OSError as exc:
            _close_fd(fd)
            # Preserve the established fchmod failure boundary used by the
            # installer tests.  The private candidate remains because a
            # pathname unlink could race a replacement inode.
            raise exc
        return fd, name, expected
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
            _assert_state_components_identity(handles)
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
        correct_modes: bool = True,
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
        with _state_components(repo, create=False, correct_modes=correct_modes) as handles:
            if handles is None:
                return cls(repo_root=repo)
            _assert_state_identity(handles.state_path, handles.state_fd, description="installer state parent")
            _assert_state_identity(handles.installer_path, handles.installer_fd, description="installer state directory")
            raw = _read_state(handles, correct_mode=correct_modes)
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
        with _state_components(parent_root, create=True, correct_modes=True) as handles:
            if handles is None:
                raise InvalidInputError("installer state directory could not be opened")
            _save_state_to_handles(self, path, handles)
        return path

    persist = save


def _save_state_to_handles(state: InstallerState, path: Path, handles: _StateHandles) -> None:
    """Persist using already-open, identity-checked state descriptors."""

    parent = path.parent
    if not path.is_absolute() or parent.name != "installer" or parent.parent.name != ".state":
        raise InvalidInputError("installer state must stay below .state/installer")
    payload = json.dumps(state.as_dict(), ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    _assert_state_components_identity(handles)
    _assert_state_identity(handles.state_path, handles.state_fd, description="installer state parent")
    _assert_state_identity(handles.installer_path, handles.installer_fd, description="installer state directory")
    _assert_state_components_identity(handles)
    existing_fd = _open_state_file(handles.installer_fd)
    previous_identity: tuple[int, int] | None = None
    if existing_fd is not None:
        try:
            metadata = os.fstat(existing_fd)
            previous_identity = (metadata.st_dev, metadata.st_ino)
            if not _regular_file_matches(handles.installer_fd, STATE_FILE_NAME, previous_identity):
                raise InvalidInputError("installer state file changed before save")
        except InvalidInputError:
            _close_fd(existing_fd)
            raise
        except OSError as exc:
            _close_fd(existing_fd)
            raise InvalidInputError("installer state file could not be inspected before save") from exc
    _close_fd(existing_fd)
    backup: str | None = None
    backup_identity: tuple[int, int] | None = None
    fd: int | None = None
    temporary: str | None = None
    temporary_identity: tuple[int, int] | None = None
    replace_failed = False
    pre_rename_fsync_failed = False
    temporary_create_failed = False
    try:
        if previous_identity is not None:
            backup, backup_identity = _create_state_backup(handles.installer_fd, previous_identity)
        try:
            fd, temporary, temporary_identity = _create_temp_state_file(handles.installer_fd)
        except OSError:
            # Preserve the established raw OSError boundary for the
            # temporary inode's fchmod failure.  All other setup errors are
            # typed by _create_temp_state_file itself.
            temporary_create_failed = True
            raise
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            fd = -1
            stream.write(payload)
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except OSError:
                pre_rename_fsync_failed = True
                raise
            written = os.fstat(stream.fileno())
            if (written.st_dev, written.st_ino) != temporary_identity:
                raise InvalidInputError("temporary installer state file changed while writing")
        # The mode is applied to the open temporary inode before it can
        # become visible as state.json.  No destination chmod is needed or
        # allowed after the atomic rename.
        try:
            os.fsync(handles.installer_fd)
        except OSError:
            pre_rename_fsync_failed = True
            raise
        _assert_state_identity(handles.state_path, handles.state_fd, description="installer state parent")
        _assert_state_identity(handles.installer_path, handles.installer_fd, description="installer state directory")
        if not _regular_file_matches(handles.installer_fd, temporary, temporary_identity):
            raise InvalidInputError("temporary installer state file changed before installation")
        if previous_identity is None:
            try:
                os.stat(STATE_FILE_NAME, dir_fd=handles.installer_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise InvalidInputError("installer state appeared before installation")
        elif not _regular_file_matches(handles.installer_fd, STATE_FILE_NAME, previous_identity):
            raise InvalidInputError("installer state changed before installation")
        if backup is not None and backup_identity is not None:
            if not _regular_file_matches(handles.installer_fd, backup, backup_identity):
                raise InvalidInputError("installer state backup changed before installation")
        try:
            os.replace(
                temporary,
                STATE_FILE_NAME,
                src_dir_fd=handles.installer_fd,
                dst_dir_fd=handles.installer_fd,
            )
        except OSError:
            replace_failed = True
            raise
        if not _regular_file_matches(handles.installer_fd, STATE_FILE_NAME, temporary_identity):
            _restore_state_after_replace(
                handles.installer_fd,
                temporary,
                backup,
                backup_identity,
            )
            raise InvalidInputError("installer state changed during installation")
        # The post-rename directory sync is best effort, matching dotenv's
        # atomic-write contract.  The state is already installed and must not
        # be reported as failed here.
        try:
            os.fsync(handles.installer_fd)
        except OSError:
            pass
        _assert_state_identity(handles.state_path, handles.state_fd, description="installer state parent")
        _assert_state_identity(handles.installer_path, handles.installer_fd, description="installer state directory")
    except InvalidInputError:
        raise
    except OSError as exc:
        if replace_failed or pre_rename_fsync_failed or temporary_create_failed:
            raise
        raise InvalidInputError("installer state could not be installed safely") from exc
    finally:
        _close_fd(fd)


_CANDIDATE_NAME_PATTERNS = (
    re.compile(r"\.state-[A-Za-z0-9][A-Za-z0-9-]*\.tmp\Z"),
    re.compile(r"\.state-stage-[A-Za-z0-9][A-Za-z0-9-]*\.tmp\Z"),
    re.compile(r"\.state-backup-[A-Za-z0-9][A-Za-z0-9-]*\.tmp\Z"),
    re.compile(r"\.state-recovery-[A-Za-z0-9][A-Za-z0-9-]*\.tmp\Z"),
)


def _is_candidate_name(name: str) -> bool:
    return any(pattern.fullmatch(name) for pattern in _CANDIDATE_NAME_PATTERNS)


def diagnose_state_candidates(
    repo_root: str | os.PathLike[str],
    *,
    now: float | None = None,
    minimum_age_seconds: float = 3600.0,
    cleanup: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    """Report private state candidates without mutating the checkout.

    Candidate cleanup is intentionally guidance-only.  Linux has no atomic
    no-follow removal operation that can prove a pathname still names the
    scanned inode at the removal syscall, so even explicit confirmation does
    not enable deletion here.
    """

    if cleanup and not confirm:
        raise InvalidInputError("candidate cleanup requires explicit confirmation")
    try:
        timestamp = time.time() if now is None else float(now)
        minimum_age = float(minimum_age_seconds)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidInputError("candidate age threshold is invalid") from exc
    if not all(value >= 0 and value != float("inf") for value in (timestamp, minimum_age)):
        raise InvalidInputError("candidate age threshold is invalid")
    root = _lexical_absolute(Path(repo_root).expanduser())
    if not root.is_absolute():
        raise InvalidInputError("repository root must be an absolute path")
    candidates: list[dict[str, Any]] = []
    with _state_components(root, create=False, correct_modes=False) as handles:
        if handles is not None:
            try:
                names = sorted(name for name in os.listdir(handles.installer_fd) if _is_candidate_name(name))
            except OSError as exc:
                raise InvalidInputError("installer state candidates could not be listed safely") from exc
            for name in names:
                finding: dict[str, Any] = {
                    "path": str(handles.installer_path / name),
                    "kind": "unknown",
                    "age_seconds": None,
                    "age_eligible": False,
                    "identity_verified": False,
                }
                fd: int | None = None
                try:
                    lexical = os.stat(name, dir_fd=handles.installer_fd, follow_symlinks=False)
                    if stat.S_ISLNK(lexical.st_mode):
                        finding["kind"] = "symlink"
                    elif stat.S_ISDIR(lexical.st_mode):
                        finding["kind"] = "directory"
                    elif stat.S_ISREG(lexical.st_mode):
                        finding["kind"] = "file"
                    else:
                        finding["kind"] = "other"
                    age = max(0.0, timestamp - float(lexical.st_mtime))
                    finding["age_seconds"] = age
                    if finding["kind"] not in {"file", "directory"}:
                        candidates.append(finding)
                        continue
                    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
                    if stat.S_ISDIR(lexical.st_mode):
                        flags |= getattr(os, "O_DIRECTORY", 0)
                    fd = os.open(name, flags, dir_fd=handles.installer_fd)
                    captured = os.fstat(fd)
                    if not (stat.S_ISREG(captured.st_mode) or stat.S_ISDIR(captured.st_mode)):
                        finding["kind"] = "other"
                        candidates.append(finding)
                        continue
                    current = os.stat(name, dir_fd=handles.installer_fd, follow_symlinks=False)
                    finding["identity_verified"] = (
                        not stat.S_ISLNK(current.st_mode)
                        and current.st_dev == captured.st_dev
                        and current.st_ino == captured.st_ino
                        and current.st_dev == lexical.st_dev
                        and current.st_ino == lexical.st_ino
                    )
                    finding["age_eligible"] = (
                        bool(finding["identity_verified"])
                        and age >= minimum_age
                        and finding["kind"] in {"file", "directory"}
                    )
                    finding["device"] = captured.st_dev
                    finding["inode"] = captured.st_ino
                except OSError:
                    # Keep the matching private name visible, but never claim
                    # age or identity eligibility after an unsafe inspection.
                    pass
                finally:
                    _close_fd(fd)
                candidates.append(finding)
    cleanup_report = {
        "requested": bool(cleanup),
        "confirmed": bool(confirm),
        "requires_confirmation": True,
        "performed": False,
        "guidance": (
            "Review each candidate's age and verified device/inode before any manual cleanup; "
            "automatic cleanup is disabled because no atomic no-follow removal primitive is available."
        ),
    }
    return {"candidates": candidates, "cleanup": cleanup_report}


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
        with _state_lock(self._state.repo_root) as handles:
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
            _save_state_to_handles(candidate, candidate.path, handles)
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
    "diagnose_state_candidates",
    "state_directory",
    "state_path",
]
