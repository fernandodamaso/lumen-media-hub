import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path


INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.disk_guard import (  # noqa: E402
    GIB,
    CapacityAccounting,
    CapacitySnapshot,
    CapacityReservationBook,
    DiskGuard,
    DiskGuardConfig,
    DiskIdentityError,
    FilesystemIdentity,
    GuardItem,
    GuardSupervisor,
    measure_filesystem,
    actual_reclaimed_bytes,
    verified_reclaim,
)


def identity(path, *, uuid="STAGING-UUID", available=200 * GIB, readonly=False):
    return FilesystemIdentity(
        path=Path(path),
        device=7,
        mount_target=Path(path).parent,
        source="/dev/fake",
        uuid=uuid,
        filesystem="ext4",
        readonly=readonly,
        available_bytes=available,
    )


class FilesystemIdentityTests(unittest.TestCase):
    def test_missing_target_fails_without_falling_back_to_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing"
            calls = []

            def statvfs(path):
                calls.append(Path(path))
                return type("Stat", (), {"f_bavail": 100, "f_frsize": 4096})()

            with self.assertRaises(DiskIdentityError):
                measure_filesystem(
                    missing,
                    statvfs_probe=statvfs,
                    mount_probe=lambda _path: {"target": str(Path(temporary)), "source": "/dev/fake", "options": "rw", "fstype": "ext4"},
                )
            self.assertEqual(calls, [])

    def test_wrong_uuid_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "library"
            target.mkdir()
            with self.assertRaisesRegex(DiskIdentityError, "UUID"):
                measure_filesystem(
                    target,
                    expected_uuid="B8A426BFA4267FCC",
                    mount_probe=lambda _path: {"target": str(Path(temporary)), "source": "/dev/fake", "uuid": "WRONG", "options": "rw", "fstype": "ntfs"},
                )

    def test_ambiguous_mount_rows_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "library"
            target.mkdir()
            with self.assertRaisesRegex(DiskIdentityError, "ambiguous"):
                measure_filesystem(
                    target,
                    mount_probe=lambda _path: {"filesystems": [{"target": str(Path(temporary))}, {"target": "/"}]},
                )

    def test_read_only_mount_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "library"
            target.mkdir()
            with self.assertRaisesRegex(DiskIdentityError, "read-only"):
                measure_filesystem(
                    target,
                    mount_probe=lambda _path: {"target": str(Path(temporary)), "source": "/dev/fake", "uuid": "B8A426BFA4267FCC", "options": "ro", "fstype": "ntfs"},
                )

    def test_capacity_probe_error_does_not_measure_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "library"
            target.mkdir()
            calls = []

            def statvfs(path):
                calls.append(Path(path))
                raise OSError("unavailable")

            with self.assertRaises(DiskIdentityError):
                measure_filesystem(
                    target,
                    statvfs_probe=statvfs,
                    mount_probe=lambda _path: {"target": str(Path(temporary)), "source": "/dev/fake", "options": "rw", "fstype": "ext4"},
                )
            self.assertEqual(calls, [target])


class GuardPlanningTests(unittest.TestCase):
    def setUp(self):
        self.config = DiskGuardConfig(
            staging_path=Path("/home/admin/lumen-downloads"),
            library_path=Path("/run/media/admin/ARQUIVOS/media"),
            library_uuid="B8A426BFA4267FCC",
            staging_reserve_bytes=75 * GIB,
            library_reserve_bytes=50 * GIB,
            resume_margin_bytes=10 * GIB,
            max_inflight_bytes=20 * GIB,
        )
        self.snapshot = CapacitySnapshot(
            staging=identity(self.config.staging_path, available=100 * GIB),
            library=identity(self.config.library_path, uuid="B8A426BFA4267FCC", available=100 * GIB),
        )

    def test_admits_fitting_queue_subset_in_order_without_deadlock(self):
        guard = DiskGuard(self.config)
        items = [
            GuardItem("too-large", staging_bytes=30 * GIB),
            GuardItem("fits", staging_bytes=5 * GIB),
            GuardItem("also-fits", staging_bytes=5 * GIB),
        ]
        plan = guard.plan(items, self.snapshot)
        self.assertEqual([item.identifier for item in plan.admitted], ["fits", "also-fits"])
        self.assertEqual([item.identifier for item in plan.guard_paused], ["too-large"])

    def test_accounts_import_overlap_extraction_and_bounded_inflight(self):
        guard = DiskGuard(self.config)
        accounting = CapacityAccounting(
            remaining_download_bytes=10 * GIB,
            pending_import_bytes=20 * GIB,
            replacement_overlap_bytes=10 * GIB,
            extraction_bytes=5 * GIB,
            inflight_bytes=5 * GIB,
        )
        item = GuardItem(
            "next",
            staging_bytes=4 * GIB,
            destination_bytes=4 * GIB,
            replacement_overlap_bytes=2 * GIB,
            extraction_bytes=2 * GIB,
            inflight_bytes=2 * GIB,
        )
        plan = guard.plan([item], self.snapshot, accounting=accounting)
        self.assertEqual(plan.admitted, ())
        self.assertEqual(plan.guard_paused[0].identifier, "next")

    def test_manual_pause_is_never_resumed_by_guard(self):
        guard = DiskGuard(self.config)
        manual = GuardItem("manual", staging_bytes=1 * GIB, manual_paused=True)
        paused = GuardItem("guard", staging_bytes=1 * GIB, guard_paused=True)
        plan = guard.plan([manual, paused], self.snapshot, resume=True)
        self.assertEqual([item.identifier for item in plan.manual_paused], ["manual"])
        self.assertEqual([item.identifier for item in plan.admitted], ["guard"])

    def test_guard_pause_needs_ten_gib_resume_margin(self):
        guard = DiskGuard(self.config)
        snapshot = CapacitySnapshot(
            staging=identity(self.config.staging_path, available=84 * GIB),
            library=identity(self.config.library_path, uuid="B8A426BFA4267FCC", available=100 * GIB),
        )
        item = GuardItem("guard", staging_bytes=1 * GIB, guard_paused=True)
        plan = guard.plan([item], snapshot, resume=True)
        self.assertEqual(plan.admitted, ())
        self.assertEqual(plan.guard_paused, (item,))

    def test_verified_reclaim_is_accounted_as_actual_capacity(self):
        accounting = CapacityAccounting()
        updated = verified_reclaim(accounting, freed_bytes=12 * GIB, verified=True)
        self.assertEqual(updated.reclaimed_staging_bytes, 12 * GIB)
        with self.assertRaises(ValueError):
            verified_reclaim(accounting, freed_bytes=1, verified=False)

    def test_actual_reclaimed_capacity_uses_same_disk_identity(self):
        before = identity("/downloads", available=20 * GIB)
        after = identity("/downloads", available=32 * GIB)
        self.assertEqual(actual_reclaimed_bytes(before, after), 12 * GIB)
        with self.assertRaises(DiskIdentityError):
            actual_reclaimed_bytes(before, identity("/other", available=32 * GIB))

    def test_concurrent_reservations_are_serialized(self):
        book = CapacityReservationBook(DiskGuard(self.config))
        items = [GuardItem(f"item-{index}", staging_bytes=15 * GIB) for index in range(2)]
        results = []
        threads = [threading.Thread(target=lambda item=item: results.append(book.reserve(item, self.snapshot))) for item in items]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [False, True])
        self.assertTrue(book.release("item-0") or book.release("item-1"))


class SupervisorTests(unittest.TestCase):
    class Runner:
        def __init__(self):
            self.calls = []

        def stop_downloader(self):
            self.calls.append("stop_downloader")

        def stop_container(self, name):
            self.calls.append(("stop_container", name))

        def start_container(self, name):
            self.calls.append(("start_container", name))

        def suspend_writers(self):
            self.calls.append("suspend_writers")

        def resume_writers(self):
            self.calls.append("resume_writers")

    def setUp(self):
        self.config = DiskGuardConfig(enabled=True)
        self.good = CapacitySnapshot(
            staging=identity(self.config.staging_path),
            library=identity(self.config.library_path, uuid=self.config.library_uuid),
        )

    def test_guard_crash_stops_downloader_and_does_not_escape(self):
        runner = self.Runner()
        supervisor = GuardSupervisor(self.config, lambda: (_ for _ in ()).throw(RuntimeError("boom")), lambda: True, runner)
        result = supervisor.cycle([])
        self.assertEqual(result.status, "guard-failed")
        self.assertIn("stop_downloader", runner.calls)

    def test_qbit_api_failure_stops_container(self):
        runner = self.Runner()
        supervisor = GuardSupervisor(self.config, lambda: self.good, lambda: False, runner)
        result = supervisor.cycle([])
        self.assertEqual(result.status, "qbit-unavailable")
        self.assertIn(("stop_container", "qbittorrent"), runner.calls)

    def test_missing_destination_suspends_writers(self):
        runner = self.Runner()
        bad = CapacitySnapshot(staging=self.good.staging, library=None, reason="library-missing")
        supervisor = GuardSupervisor(self.config, lambda: bad, lambda: True, runner)
        result = supervisor.cycle([])
        self.assertEqual(result.status, "destination-unavailable")
        self.assertIn("suspend_writers", runner.calls)

    def test_restart_requires_healthy_guard_and_api(self):
        runner = self.Runner()
        supervisor = GuardSupervisor(self.config, lambda: self.good, lambda: True, runner)
        supervisor.mark_container_stopped()
        result = supervisor.cycle([])
        self.assertEqual(result.status, "healthy")
        self.assertIn(("start_container", "qbittorrent"), runner.calls)

    def test_default_off_does_not_probe_or_mutate(self):
        runner = self.Runner()
        supervisor = GuardSupervisor(DiskGuardConfig(), lambda: (_ for _ in ()).throw(AssertionError()), lambda: (_ for _ in ()).throw(AssertionError()), runner)
        self.assertEqual(supervisor.cycle([]).status, "disabled")
        self.assertEqual(runner.calls, [])

    def test_item_provider_failure_stops_downloader_and_returns(self):
        runner = self.Runner()
        supervisor = GuardSupervisor(self.config, lambda: self.good, lambda: True, runner)

        def broken_provider():
            raise RuntimeError("queue controller failed")

        supervisor.run_forever(broken_provider, sleep=lambda _seconds: None)
        self.assertEqual(runner.calls, ["stop_downloader"])


if __name__ == "__main__":
    unittest.main()
