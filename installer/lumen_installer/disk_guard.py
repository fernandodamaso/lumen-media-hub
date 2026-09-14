"""Staged, default-off disk admission guard for the separate storage layout.

The guard is deliberately a host-side policy module.  It measures both paths
it was given, accounts for reservations before admitting queue work, and
returns a plan.  It does not discover another path, delete files, call a live
service, or mutate qBittorrent/Compose unless a caller explicitly supplies a
supervisor runner and enables it.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import time
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event, Lock
from typing import Any, Callable, Iterable, Mapping


GIB = 1024**3
DEFAULT_STAGING_PATH = Path("/home/admin/lumen-downloads")
DEFAULT_LIBRARY_PATH = Path("/run/media/admin/ARQUIVOS/media")
DEFAULT_LIBRARY_UUID = "B8A426BFA4267FCC"
DEFAULT_STAGING_RESERVE_GIB = 75
DEFAULT_LIBRARY_RESERVE_GIB = 50
DEFAULT_RESUME_MARGIN_GIB = 10
DEFAULT_MAX_INFLIGHT_GIB = 20


class DiskIdentityError(RuntimeError):
    """The requested path could not be proven to be the intended writable disk."""


def _normalise_uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().replace("-", "").upper()
    return value if value and all(char in "0123456789ABCDEF" for char in value) else None


def _absolute_path(value: Path | str) -> Path:
    path = Path(value)
    if not path.is_absolute() or path == Path("/"):
        raise DiskIdentityError("storage path must be an absolute non-root directory")
    if "\x00" in str(path):
        raise DiskIdentityError("storage path is invalid")
    return Path(os.path.abspath(str(path)))


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            if os.path.islink(current):
                return True
        except OSError as exc:
            raise DiskIdentityError("storage path identity is ambiguous") from exc
    return False


def _mount_probe(path: Path) -> Mapping[str, Any]:
    try:
        result = subprocess.run(
            [
                "findmnt",
                "--json",
                "--target",
                str(path),
                "--output",
                "TARGET,SOURCE,UUID,OPTIONS,FSTYPE",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise DiskIdentityError("mount identity could not be inspected") from exc
    if result.returncode != 0:
        raise DiskIdentityError("mount identity could not be inspected")
    try:
        payload = json.loads(result.stdout)
        filesystems = payload.get("filesystems")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DiskIdentityError("mount identity is malformed") from exc
    if not isinstance(filesystems, list) or len(filesystems) != 1 or not isinstance(filesystems[0], Mapping):
        raise DiskIdentityError("mount identity is ambiguous")
    return filesystems[0]


def _metadata(value: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in value:
            return value[name]
    return None


def _available_bytes(metadata: Any) -> int:
    available = getattr(metadata, "f_bavail", None)
    block = getattr(metadata, "f_frsize", None) or getattr(metadata, "f_bsize", None)
    if isinstance(available, bool) or isinstance(block, bool):
        raise DiskIdentityError("available capacity metadata is invalid")
    try:
        value = int(available) * int(block)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DiskIdentityError("available capacity metadata is invalid") from exc
    if available is None or block is None or value < 0:
        raise DiskIdentityError("available capacity metadata is invalid")
    return value


@dataclass(frozen=True)
class FilesystemIdentity:
    path: Path
    device: int
    mount_target: Path
    source: str
    uuid: str | None
    filesystem: str
    readonly: bool
    available_bytes: int


def measure_filesystem(
    path: Path | str,
    *,
    expected_uuid: str | None = None,
    mount_probe: Callable[[Path], Mapping[str, Any]] | None = None,
    statvfs_probe: Callable[[Path], Any] | None = None,
) -> FilesystemIdentity:
    """Measure exactly ``path`` and prove its mount identity.

    No parent, current directory, or filesystem root is substituted when a
    target is missing or a probe fails.  Tests inject both read-only probes;
    production uses ``findmnt`` and ``os.statvfs``.
    """

    target = _absolute_path(path)
    if _has_symlink_component(target):
        raise DiskIdentityError("storage path identity is ambiguous")
    try:
        lexical = os.lstat(target)
    except OSError as exc:
        raise DiskIdentityError("storage path is missing") from exc
    if stat.S_ISLNK(lexical.st_mode) or not stat.S_ISDIR(lexical.st_mode):
        raise DiskIdentityError("storage path is not a directory")
    try:
        actual = os.stat(target, follow_symlinks=False)
    except OSError as exc:
        raise DiskIdentityError("storage path identity could not be read") from exc

    probe = mount_probe or _mount_probe
    try:
        mounted = probe(target)
    except DiskIdentityError:
        raise
    except Exception as exc:
        raise DiskIdentityError("mount identity could not be inspected") from exc
    if not isinstance(mounted, Mapping):
        raise DiskIdentityError("mount identity is malformed")
    if "filesystems" in mounted:
        rows = mounted.get("filesystems")
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
            raise DiskIdentityError("mount identity is ambiguous")
        mounted = rows[0]
    mount_target_raw = _metadata(mounted, "target", "TARGET")
    source = _metadata(mounted, "source", "SOURCE")
    options_raw = _metadata(mounted, "options", "OPTIONS")
    filesystem = _metadata(mounted, "fstype", "FSTYPE")
    mount_target = Path(mount_target_raw) if isinstance(mount_target_raw, str) else None
    if (
        mount_target is None
        or not mount_target.is_absolute()
        or not isinstance(source, str)
        or not source.strip()
        or not isinstance(options_raw, str)
        or not options_raw.strip()
        or not isinstance(filesystem, str)
        or not filesystem.strip()
    ):
        raise DiskIdentityError("mount identity is incomplete")
    mount_target = Path(os.path.abspath(str(mount_target)))
    if mount_target != Path("/") and mount_target not in target.parents and mount_target != target:
        raise DiskIdentityError("mount identity target does not contain storage path")
    options = {part.strip().lower() for part in options_raw.split(",") if part.strip()}
    if "rw" not in options or "ro" in options:
        raise DiskIdentityError("storage path is read-only")
    readonly = _metadata(mounted, "read_only", "READ_ONLY")
    if readonly is not None and type(readonly) is not bool:
        raise DiskIdentityError("read-only mount metadata is invalid")
    if readonly is True:
        raise DiskIdentityError("storage path is read-only")
    if not (stat.S_IMODE(lexical.st_mode) & 0o222) or not os.access(target, os.W_OK):
        raise DiskIdentityError("storage path is not writable")
    actual_uuid = _normalise_uuid(_metadata(mounted, "uuid", "UUID"))
    configured_uuid = _normalise_uuid(expected_uuid)
    if expected_uuid is not None and (not actual_uuid or actual_uuid != configured_uuid):
        raise DiskIdentityError("storage path UUID does not match the configured disk")
    try:
        capacity = (statvfs_probe or os.statvfs)(target)
        available = _available_bytes(capacity)
    except DiskIdentityError:
        raise
    except (OSError, TypeError, ValueError, OverflowError) as exc:
        raise DiskIdentityError("available capacity could not be read") from exc
    return FilesystemIdentity(
        path=target,
        device=int(actual.st_dev),
        mount_target=mount_target,
        source=source.strip(),
        uuid=actual_uuid,
        filesystem=filesystem.strip(),
        readonly=False,
        available_bytes=available,
    )


@dataclass(frozen=True)
class DiskGuardConfig:
    staging_path: Path = DEFAULT_STAGING_PATH
    library_path: Path = DEFAULT_LIBRARY_PATH
    library_uuid: str = DEFAULT_LIBRARY_UUID
    staging_reserve_bytes: int = DEFAULT_STAGING_RESERVE_GIB * GIB
    library_reserve_bytes: int = DEFAULT_LIBRARY_RESERVE_GIB * GIB
    resume_margin_bytes: int = DEFAULT_RESUME_MARGIN_GIB * GIB
    max_inflight_bytes: int = DEFAULT_MAX_INFLIGHT_GIB * GIB
    interval_seconds: float = 5.0
    enabled: bool = False

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "DiskGuardConfig":
        values = os.environ if environ is None else environ

        def number(name: str, default: int) -> int:
            try:
                value = int(values.get(name, str(default)))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be an integer") from exc
            if value < 0:
                raise ValueError(f"{name} must not be negative")
            return value

        def seconds(name: str, default: float) -> float:
            try:
                value = float(values.get(name, str(default)))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be numeric") from exc
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            return value

        enabled = str(values.get("DISK_GUARD_ENABLED", "false")).strip().lower() in {"1", "true", "yes", "on"}
        return cls(
            staging_path=Path(values.get("DOWNLOADS_PATH", str(DEFAULT_STAGING_PATH))),
            library_path=Path(values.get("ROOT_PATH", str(DEFAULT_LIBRARY_PATH))) / "media",
            library_uuid=values.get("LIBRARY_MOUNT_UUID", DEFAULT_LIBRARY_UUID),
            staging_reserve_bytes=number("DISK_GUARD_STAGING_RESERVE_GIB", DEFAULT_STAGING_RESERVE_GIB) * GIB,
            library_reserve_bytes=number("DISK_GUARD_LIBRARY_RESERVE_GIB", DEFAULT_LIBRARY_RESERVE_GIB) * GIB,
            resume_margin_bytes=number("DISK_GUARD_RESUME_MARGIN_GIB", DEFAULT_RESUME_MARGIN_GIB) * GIB,
            max_inflight_bytes=number("DISK_GUARD_MAX_INFLIGHT_GIB", DEFAULT_MAX_INFLIGHT_GIB) * GIB,
            interval_seconds=seconds("DISK_GUARD_INTERVAL_SECONDS", 5.0),
            enabled=enabled,
        )


@dataclass(frozen=True)
class CapacitySnapshot:
    staging: FilesystemIdentity | None
    library: FilesystemIdentity | None
    reason: str = ""

    @property
    def healthy(self) -> bool:
        return self.staging is not None and self.library is not None and not self.reason


@dataclass(frozen=True)
class CapacityAccounting:
    remaining_download_bytes: int = 0
    pending_import_bytes: int = 0
    replacement_overlap_bytes: int = 0
    extraction_bytes: int = 0
    inflight_bytes: int = 0
    reclaimed_staging_bytes: int = 0

    def __post_init__(self) -> None:
        for value in (
            self.remaining_download_bytes,
            self.pending_import_bytes,
            self.replacement_overlap_bytes,
            self.extraction_bytes,
            self.inflight_bytes,
            self.reclaimed_staging_bytes,
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("capacity accounting values must be non-negative integers")


@dataclass(frozen=True)
class GuardItem:
    identifier: str
    staging_bytes: int = 0
    destination_bytes: int = 0
    replacement_overlap_bytes: int = 0
    extraction_bytes: int = 0
    inflight_bytes: int = 0
    manual_paused: bool = False
    guard_paused: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.identifier, str) or not self.identifier.strip():
            raise ValueError("queue item identifier is required")
        for value in (
            self.staging_bytes,
            self.destination_bytes,
            self.replacement_overlap_bytes,
            self.extraction_bytes,
            self.inflight_bytes,
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("queue item capacity values must be non-negative integers")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GuardItem":
        identifier = value.get("identifier", value.get("id", value.get("hash", value.get("name"))))
        reason = str(value.get("pause_reason", "")).strip().lower()
        return cls(
            str(identifier),
            staging_bytes=int(value.get("staging_bytes", value.get("remaining_bytes", 0))),
            destination_bytes=int(value.get("destination_bytes", value.get("import_bytes", 0))),
            replacement_overlap_bytes=int(value.get("replacement_overlap_bytes", value.get("overlap_bytes", 0))),
            extraction_bytes=int(value.get("extraction_bytes", value.get("extraction_allowance_bytes", 0))),
            inflight_bytes=int(value.get("inflight_bytes", 0)),
            manual_paused=bool(value.get("manual_paused", value.get("user_paused", False))) or reason in {"manual", "user"},
            guard_paused=bool(value.get("guard_paused", False)) or reason == "guard_capacity",
        )


@dataclass(frozen=True)
class AdmissionPlan:
    admitted: tuple[GuardItem, ...] = ()
    guard_paused: tuple[GuardItem, ...] = ()
    manual_paused: tuple[GuardItem, ...] = ()
    reason: str = ""
    snapshot: CapacitySnapshot | None = None

    @property
    def paused(self) -> tuple[GuardItem, ...]:
        return self.guard_paused + self.manual_paused


def _item_cost(item: GuardItem) -> tuple[int, int, int]:
    # Replacement overlap is charged to both disks: a replacement can have
    # both the old destination and new copy alive until verification commits.
    return (
        item.staging_bytes + item.extraction_bytes + item.replacement_overlap_bytes,
        item.destination_bytes + item.replacement_overlap_bytes,
        item.inflight_bytes,
    )


class DiskGuard:
    def __init__(
        self,
        config: DiskGuardConfig | None = None,
        *,
        measure: Callable[..., FilesystemIdentity] = measure_filesystem,
    ) -> None:
        self.config = config or DiskGuardConfig()
        self._measure = measure

    def snapshot(self) -> CapacitySnapshot:
        staging = library = None
        errors: list[str] = []
        try:
            staging = self._measure(self.config.staging_path)
        except Exception as exc:
            errors.append(f"staging:{exc}")
        try:
            library = self._measure(self.config.library_path, expected_uuid=self.config.library_uuid)
        except Exception as exc:
            errors.append(f"library:{exc}")
        return CapacitySnapshot(staging, library, "; ".join(errors))

    def plan(
        self,
        items: Iterable[GuardItem | Mapping[str, Any]],
        snapshot: CapacitySnapshot | None = None,
        *,
        accounting: CapacityAccounting | None = None,
        resume: bool = False,
    ) -> AdmissionPlan:
        snapshot = snapshot or self.snapshot()
        queue = tuple(item if isinstance(item, GuardItem) else GuardItem.from_mapping(item) for item in items)
        if not snapshot.healthy:
            return AdmissionPlan(
                manual_paused=tuple(item for item in queue if item.manual_paused),
                guard_paused=tuple(item for item in queue if not item.manual_paused),
                reason=snapshot.reason or "storage-identity-unhealthy",
                snapshot=snapshot,
            )
        account = accounting or CapacityAccounting()
        staging_used = (
            account.remaining_download_bytes
            + account.extraction_bytes
            + account.replacement_overlap_bytes
            + account.inflight_bytes
        )
        library_used = account.pending_import_bytes + account.replacement_overlap_bytes
        inflight_used = account.inflight_bytes
        staging_available = snapshot.staging.available_bytes + account.reclaimed_staging_bytes
        library_available = snapshot.library.available_bytes
        staging_floor = self.config.staging_reserve_bytes + (self.config.resume_margin_bytes if resume else 0)
        library_floor = self.config.library_reserve_bytes + (self.config.resume_margin_bytes if resume else 0)
        admitted: list[GuardItem] = []
        guard_paused: list[GuardItem] = []
        manual_paused: list[GuardItem] = []
        for item in queue:
            if item.manual_paused:
                manual_paused.append(item)
                continue
            if item.guard_paused and not resume:
                guard_paused.append(item)
                continue
            try:
                staging_cost, library_cost, inflight_cost = _item_cost(item)
                fits = (
                    staging_used + staging_cost <= staging_available - staging_floor
                    and library_used + library_cost <= library_available - library_floor
                    and inflight_used + inflight_cost <= self.config.max_inflight_bytes
                )
            except (TypeError, ValueError, OverflowError):
                fits = False
            if fits:
                admitted.append(item)
                staging_used += staging_cost
                library_used += library_cost
                inflight_used += inflight_cost
            else:
                guard_paused.append(item)
        return AdmissionPlan(
            admitted=tuple(admitted),
            guard_paused=tuple(guard_paused),
            manual_paused=tuple(manual_paused),
            reason="healthy",
            snapshot=snapshot,
        )

    def resume_guard_paused(
        self,
        items: Iterable[GuardItem | Mapping[str, Any]],
        snapshot: CapacitySnapshot | None = None,
        *,
        accounting: CapacityAccounting | None = None,
    ) -> AdmissionPlan:
        return self.plan(items, snapshot, accounting=accounting, resume=True)


def verified_reclaim(accounting: CapacityAccounting, *, freed_bytes: int, verified: bool) -> CapacityAccounting:
    """Credit only bytes already freed by an independently verified operation."""

    if verified is not True or isinstance(freed_bytes, bool) or not isinstance(freed_bytes, int) or freed_bytes < 0:
        raise ValueError("only verified non-negative reclaimed bytes may be credited")
    return replace(accounting, reclaimed_staging_bytes=accounting.reclaimed_staging_bytes + freed_bytes)


class CapacityReservationBook:
    """Serialize admission reservations so concurrent workers cannot oversubscribe."""

    def __init__(self, guard: DiskGuard | None = None, accounting: CapacityAccounting | None = None) -> None:
        self.guard = guard or DiskGuard()
        self.accounting = accounting or CapacityAccounting()
        self._lock = Lock()
        self._reserved: dict[str, GuardItem] = {}

    @staticmethod
    def _add(accounting: CapacityAccounting, item: GuardItem) -> CapacityAccounting:
        return replace(
            accounting,
            remaining_download_bytes=accounting.remaining_download_bytes + item.staging_bytes,
            pending_import_bytes=accounting.pending_import_bytes + item.destination_bytes,
            replacement_overlap_bytes=accounting.replacement_overlap_bytes + item.replacement_overlap_bytes,
            extraction_bytes=accounting.extraction_bytes + item.extraction_bytes,
            inflight_bytes=accounting.inflight_bytes + item.inflight_bytes,
        )

    @staticmethod
    def _remove(accounting: CapacityAccounting, item: GuardItem) -> CapacityAccounting:
        return replace(
            accounting,
            remaining_download_bytes=accounting.remaining_download_bytes - item.staging_bytes,
            pending_import_bytes=accounting.pending_import_bytes - item.destination_bytes,
            replacement_overlap_bytes=accounting.replacement_overlap_bytes - item.replacement_overlap_bytes,
            extraction_bytes=accounting.extraction_bytes - item.extraction_bytes,
            inflight_bytes=accounting.inflight_bytes - item.inflight_bytes,
        )

    def reserve(self, item: GuardItem | Mapping[str, Any], snapshot: CapacitySnapshot) -> bool:
        candidate = item if isinstance(item, GuardItem) else GuardItem.from_mapping(item)
        with self._lock:
            if candidate.identifier in self._reserved:
                return False
            plan = self.guard.plan([candidate], snapshot, accounting=self.accounting)
            if candidate not in plan.admitted:
                return False
            self.accounting = self._add(self.accounting, candidate)
            self._reserved[candidate.identifier] = candidate
            return True

    def release(self, identifier: str) -> bool:
        with self._lock:
            candidate = self._reserved.pop(identifier, None)
            if candidate is None:
                return False
            self.accounting = self._remove(self.accounting, candidate)
            return True


def actual_reclaimed_bytes(before: FilesystemIdentity, after: FilesystemIdentity) -> int:
    if before.path != after.path or before.device != after.device or before.source != after.source or before.uuid != after.uuid:
        raise DiskIdentityError("capacity samples have different filesystem identities")
    return max(0, after.available_bytes - before.available_bytes)


@dataclass(frozen=True)
class SupervisorResult:
    status: str
    actions: tuple[str, ...] = ()
    reason: str = ""
    plan: AdmissionPlan | None = None


class GuardSupervisor:
    """Small injectable supervisor seam; disabled configuration is inert."""

    def __init__(
        self,
        config: DiskGuardConfig,
        snapshot_provider: Callable[[], CapacitySnapshot],
        qbit_health: Callable[[], bool],
        runner: Any,
        *,
        guard: DiskGuard | None = None,
    ) -> None:
        self.config = config
        self._snapshot_provider = snapshot_provider
        self._qbit_health = qbit_health
        self._runner = runner
        self._guard = guard or DiskGuard(config)
        self._container_stopped = False
        self._writers_suspended = False

    def mark_container_stopped(self) -> None:
        self._container_stopped = True

    def cycle(
        self,
        items: Iterable[GuardItem | Mapping[str, Any]],
        *,
        accounting: CapacityAccounting | None = None,
        resume: bool = False,
    ) -> SupervisorResult:
        if not self.config.enabled:
            return SupervisorResult("disabled")
        actions: list[str] = []
        try:
            snapshot = self._snapshot_provider()
            if not isinstance(snapshot, CapacitySnapshot):
                raise RuntimeError("invalid guard snapshot")
        except Exception as exc:
            self._runner.stop_downloader()
            self._runner.suspend_writers()
            self._writers_suspended = True
            return SupervisorResult(
                "guard-failed", ("stop_downloader", "suspend_writers"), str(exc)
            )
        if not snapshot.healthy:
            self._runner.stop_downloader()
            actions.append("stop_downloader")
            if not self._writers_suspended:
                self._runner.suspend_writers()
                self._writers_suspended = True
                actions.append("suspend_writers")
            # A filesystem failure must stop admission immediately, but the
            # qBittorrent health failure still owns the container stop path.
            try:
                qbit_healthy = self._qbit_health() is True
            except Exception:
                qbit_healthy = False
            if not qbit_healthy:
                self._runner.stop_container("qbittorrent")
                self._container_stopped = True
                actions.append("stop_container:qbittorrent")
            return SupervisorResult(
                "destination-unavailable" if snapshot.library is None else "guard-failed",
                tuple(actions),
                snapshot.reason,
            )
        try:
            healthy = self._qbit_health() is True
        except Exception as exc:
            healthy = False
            reason = str(exc)
        else:
            reason = ""
        if not healthy:
            self._runner.stop_container("qbittorrent")
            self._container_stopped = True
            actions.append("stop_container:qbittorrent")
            if not self._writers_suspended:
                self._runner.suspend_writers()
                self._writers_suspended = True
                actions.append("suspend_writers")
            return SupervisorResult("qbit-unavailable", tuple(actions), reason)
        if self._container_stopped:
            self._runner.start_container("qbittorrent")
            self._container_stopped = False
            actions.append("start_container:qbittorrent")
        if self._writers_suspended:
            self._runner.resume_writers()
            self._writers_suspended = False
            actions.append("resume_writers")
        plan = self._guard.plan(items, snapshot, accounting=accounting, resume=resume)
        return SupervisorResult("healthy", tuple(actions), plan=plan)

    def run_forever(
        self,
        items_provider: Callable[[], Iterable[GuardItem | Mapping[str, Any]]],
        *,
        stop_event: Event | None = None,
        sleep: Callable[[float], Any] = time.sleep,
    ) -> None:
        stop_event = stop_event or Event()
        while not stop_event.is_set():
            try:
                self.cycle(items_provider())
            except Exception:
                # A queue/controller fault must fail closed like a guard fault;
                # never leave the downloader running on stale admission data.
                try:
                    self._runner.stop_downloader()
                except Exception:
                    pass
                return
            sleep(self.config.interval_seconds)


__all__ = [
    "AdmissionPlan",
    "CapacityAccounting",
    "CapacityReservationBook",
    "CapacitySnapshot",
    "DEFAULT_LIBRARY_PATH",
    "DEFAULT_LIBRARY_UUID",
    "DEFAULT_STAGING_PATH",
    "DiskGuard",
    "DiskGuardConfig",
    "DiskIdentityError",
    "FilesystemIdentity",
    "GIB",
    "GuardItem",
    "GuardSupervisor",
    "SupervisorResult",
    "actual_reclaimed_bytes",
    "measure_filesystem",
    "verified_reclaim",
]
