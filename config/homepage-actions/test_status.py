"""Focused tests for the bounded staged status projection."""

import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import config
import status
import trakt_retention
import verified_cleanup
from clients.trakt import TraktTokenState, TraktTokenStore


OLD_DELETED_STATE = '{"deadbeef": {"status": "deleted", "torrent_hash": "deadbeef"}}'


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.old = {
            key: getattr(config, key)
            for key in (
                "DISK_GUARD_ENABLED",
                "DISK_GUARD_STATE_PATH",
                "VERIFIED_CLEANUP_ENABLED",
                "VERIFIED_CLEANUP_STATE_PATH",
                "TRAKT_RETENTION_ENABLED",
                "TRAKT_RETENTION_STATE_PATH",
                "TRAKT_CLIENT_ID",
                "TRAKT_CLIENT_SECRET",
                "TRAKT_TOKEN_PATH",
            )
        }
        config.DISK_GUARD_ENABLED = False
        config.DISK_GUARD_STATE_PATH = os.path.join(self.tempdir.name, "guard.json")
        config.VERIFIED_CLEANUP_ENABLED = False
        config.TRAKT_RETENTION_ENABLED = False
        config.VERIFIED_CLEANUP_STATE_PATH = os.path.join(self.tempdir.name, "cleanup.json")
        config.TRAKT_RETENTION_STATE_PATH = os.path.join(self.tempdir.name, "retention.json")
        config.TRAKT_CLIENT_ID = ""
        config.TRAKT_CLIENT_SECRET = ""
        config.TRAKT_TOKEN_PATH = os.path.join(self.tempdir.name, "trakt-token.json")
        self.assertTrue(verified_cleanup.stop_verified_cleanup_scheduler(timeout=2.0))
        with verified_cleanup._scheduler_status_lock:
            verified_cleanup._scheduler_status.update(
                lastCycleAt=None, lastStatus=None, lastError=None
            )
        self.assertTrue(trakt_retention.stop_trakt_retention_scheduler(timeout=2.0))
        with trakt_retention._scheduler_status_lock:
            trakt_retention._scheduler_status.update(
                lastCycleAt=None, lastStatus=None, lastError=None
            )

    def tearDown(self):
        for key, value in self.old.items():
            setattr(config, key, value)

    @staticmethod
    def _scheduler(running, last_cycle_at, last_status, last_error):
        return {
            "running": running,
            "lastCycleAt": last_cycle_at,
            "lastStatus": last_status,
            "lastError": last_error,
        }

    def test_default_status_is_staged_without_claiming_runtime_jobs(self):
        with patch.object(status, "build_storage_status", return_value={"status": "unavailable", "disks": []}):
            result = status.build_operational_status()
        self.assertEqual(result["storage"]["status"], "unavailable")
        self.assertEqual(result["pause"], {
            "status": "not_reported",
            "reason": "not_reported",
            "manual": None,
            "guard": None,
            "known": False,
        })
        self.assertEqual(result["guard"], {
            "enabled": False,
            "status": "disabled",
            "health": "disabled",
            "lastCycleAt": None,
        })
        self.assertEqual(result["verification"]["status"], "disabled")
        self.assertEqual(
            result["retention"]["scheduler"],
            {
                "running": False,
                "lastCycleAt": None,
                "lastStatus": None,
                "lastError": None,
            },
        )
        self.assertEqual(
            result["verifiedCleanup"]["scheduler"],
            {"running": False, "lastCycleAt": None, "lastStatus": None, "lastError": None},
        )

    def test_storage_reports_both_role_disks_and_failure_without_path_leak(self):
        good = {"total": 1000, "used": 400, "free": 600}

        def usage(path):
            if path == "/downloads":
                return type("Usage", (), good)()
            raise OSError("secret host path")

        class Vfs:
            f_frsize = 10
            f_bsize = 10
            f_bavail = 50
            f_bfree = 60

        with patch.object(status.shutil, "disk_usage", side_effect=usage), patch.object(status.os, "statvfs", return_value=Vfs()), patch.object(status.os, "stat", return_value=object()):
            result = status.build_storage_status()
        self.assertEqual([disk["id"] for disk in result["disks"]], ["staging", "library"])
        self.assertEqual(result["disks"][0]["availableBytes"], 500)
        self.assertEqual(result["disks"][0]["freeBytes"], 600)
        self.assertEqual(result["disks"][0]["identityStatus"], "observed")
        self.assertEqual(result["disks"][1]["status"], "unavailable")
        self.assertNotIn("secret", repr(result))

    def test_guard_reports_active_only_from_fresh_supervisor_state(self):
        config.DISK_GUARD_ENABLED = True
        with open(config.DISK_GUARD_STATE_PATH, "w", encoding="utf-8") as handle:
            import json

            json.dump({"status": "healthy", "updated_at": datetime.now(timezone.utc).isoformat()}, handle)
        active = status.build_operational_status()["guard"]
        self.assertEqual(active["status"], "active")
        self.assertEqual(active["health"], "healthy")

        with open(config.DISK_GUARD_STATE_PATH, "w", encoding="utf-8") as handle:
            json.dump({"status": "qbit-unavailable", "updated_at": datetime.now(timezone.utc).isoformat()}, handle)
        blocked = status.build_operational_status()["guard"]
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["health"], "fail_closed")

    def test_disabled_cleanup_and_retention_do_not_expose_private_state(self):
        with open(config.VERIFIED_CLEANUP_STATE_PATH, "w", encoding="utf-8") as handle:
            handle.write('{"deadbeef": {"status": "deleted", "files": [{"source": "/private/path"}]}}')
        with open(config.TRAKT_RETENTION_STATE_PATH, "w", encoding="utf-8") as handle:
            handle.write('{"items": {"one": {"status": "preserved", "reason": "playback_active", "file": {"path": "/private/path"}}}}')
        result = status.build_operational_status()
        self.assertEqual(result["verifiedCleanup"]["status"], "disabled")
        self.assertIsNone(result["verifiedCleanup"]["lastResult"])
        self.assertEqual(result["retention"]["status"], "disabled")
        self.assertEqual(result["retention"]["skips"], [])
        self.assertNotIn("private", repr(result))

    def test_enabled_state_is_bounded_and_reason_redacted(self):
        config.VERIFIED_CLEANUP_ENABLED = True
        config.TRAKT_RETENTION_ENABLED = True
        cleanup = {str(index): {"status": "verified" if index == 0 else "preserved", "reason": "/secret/path"} for index in range(30)}
        with open(config.VERIFIED_CLEANUP_STATE_PATH, "w", encoding="utf-8") as handle:
            import json

            json.dump(cleanup, handle)
        retention = {"items": {str(index): {"status": "preserved", "reason": "playback_active" if index < 25 else "/secret"} for index in range(30)}}
        with open(config.TRAKT_RETENTION_STATE_PATH, "w", encoding="utf-8") as handle:
            import json

            json.dump(retention, handle)
        result = status.build_operational_status()
        self.assertEqual(result["verifiedCleanup"]["queueCount"], 1)
        self.assertEqual(result["verifiedCleanup"]["lastResult"]["reason"], "other")
        self.assertEqual(result["retention"]["skips"], [{"reason": "other", "count": 5}, {"reason": "playback_active", "count": 25}])

    def test_retention_pending_or_failed_monitoring_rollback_is_degraded(self):
        config.TRAKT_RETENTION_ENABLED = True
        scheduler = self._scheduler(
            True, "2026-09-27T10:00:00Z", "completed", None
        )
        states = (
            {"items": {"one": {"status": "unmonitored", "reason": "delete_failed"}}},
            {
                "items": {
                    "one": {
                        "status": "preserved",
                        "reason": "unmonitor_rollback_failed",
                    }
                }
            },
        )
        for state in states:
            with self.subTest(state=state):
                with open(config.TRAKT_RETENTION_STATE_PATH, "w", encoding="utf-8") as handle:
                    json.dump(state, handle)
                with patch.object(
                    trakt_retention,
                    "get_trakt_retention_scheduler_status",
                    return_value=scheduler,
                ):
                    result = status.build_operational_status()["retention"]
                self.assertEqual(result["status"], "degraded")

    def test_trakt_health_reads_only_local_token_metadata(self):
        config.TRAKT_CLIENT_ID = "client-id"
        config.TRAKT_CLIENT_SECRET = "client-secret"
        store = TraktTokenStore(config.TRAKT_TOKEN_PATH)
        store.replace(TraktTokenState("access", "refresh", time.time() + 3600, time.time()))
        healthy = status.build_operational_status()["trakt"]
        self.assertEqual(healthy["auth"], "healthy")
        self.assertNotIn("access", repr(healthy))
        store.replace(TraktTokenState("access", "refresh", time.time() + 10, time.time()))
        self.assertEqual(status.build_operational_status()["trakt"]["auth"], "expired")

    def test_failed_cycle_overrides_old_success(self):
        config.VERIFIED_CLEANUP_ENABLED = True
        with open(config.VERIFIED_CLEANUP_STATE_PATH, "w", encoding="utf-8") as handle:
            handle.write(OLD_DELETED_STATE)
        failed_cycle = self._scheduler(
            True, "2026-09-27T10:00:00Z", "cleanup_cycle_failed", "cleanup_cycle_failed"
        )
        with patch.object(
            verified_cleanup, "get_verified_cleanup_scheduler_status", return_value=failed_cycle
        ):
            cleanup = status.build_operational_status()["verifiedCleanup"]

        self.assertEqual(cleanup["status"], "degraded")
        self.assertEqual(cleanup["scheduler"], failed_cycle)

    def test_degraded_cycle_overrides_old_success(self):
        config.VERIFIED_CLEANUP_ENABLED = True
        with open(config.VERIFIED_CLEANUP_STATE_PATH, "w", encoding="utf-8") as handle:
            handle.write(OLD_DELETED_STATE)
        degraded_cycle = self._scheduler(True, "2026-09-27T10:00:00Z", "degraded", None)
        with patch.object(
            verified_cleanup, "get_verified_cleanup_scheduler_status", return_value=degraded_cycle
        ):
            cleanup = status.build_operational_status()["verifiedCleanup"]

        self.assertEqual(cleanup["status"], "degraded")

    def test_enabled_cleanup_without_a_live_worker_reports_not_running(self):
        config.VERIFIED_CLEANUP_ENABLED = True
        with open(config.VERIFIED_CLEANUP_STATE_PATH, "w", encoding="utf-8") as handle:
            handle.write(OLD_DELETED_STATE)
        stopped_worker = self._scheduler(False, "2026-09-27T10:00:00Z", "ok", None)
        with patch.object(
            verified_cleanup, "get_verified_cleanup_scheduler_status", return_value=stopped_worker
        ):
            cleanup = status.build_operational_status()["verifiedCleanup"]

        self.assertEqual(cleanup["status"], "not_running")

    def test_malformed_cleanup_state_reports_degraded(self):
        config.VERIFIED_CLEANUP_ENABLED = True
        with open(config.VERIFIED_CLEANUP_STATE_PATH, "w", encoding="utf-8") as handle:
            handle.write("not-json")
        healthy_cycle = self._scheduler(True, "2026-09-27T10:00:00Z", "ok", None)

        with patch.object(
            verified_cleanup,
            "get_verified_cleanup_scheduler_status",
            return_value=healthy_cycle,
        ):
            cleanup = status.build_operational_status()["verifiedCleanup"]

        self.assertEqual(cleanup["status"], "degraded")

    def test_enabled_cleanup_reports_starting_before_the_first_result(self):
        config.VERIFIED_CLEANUP_ENABLED = True
        first_start = self._scheduler(True, None, None, None)
        with patch.object(
            verified_cleanup, "get_verified_cleanup_scheduler_status", return_value=first_start
        ):
            cleanup = status.build_operational_status()["verifiedCleanup"]

        self.assertEqual(cleanup["status"], "starting")

    def test_enabled_cleanup_with_a_successful_cycle_keeps_existing_states(self):
        config.VERIFIED_CLEANUP_ENABLED = True
        with open(config.VERIFIED_CLEANUP_STATE_PATH, "w", encoding="utf-8") as handle:
            handle.write(OLD_DELETED_STATE)
        healthy_cycle = self._scheduler(True, "2026-09-27T10:00:00Z", "ok", None)
        with patch.object(
            verified_cleanup, "get_verified_cleanup_scheduler_status", return_value=healthy_cycle
        ):
            cleanup = status.build_operational_status()["verifiedCleanup"]

        self.assertEqual(cleanup["status"], "ready")

    def test_durable_unresolved_outcomes_override_a_later_empty_ok_cycle(self):
        config.VERIFIED_CLEANUP_ENABLED = True
        for item_status in (
            "ambiguous_delete",
            "delete_outcome_unknown",
            "source_remains",
            "library_missing_after_delete",
            "library_changed_after_delete",
        ):
            with self.subTest(item_status=item_status):
                config.VERIFIED_CLEANUP_ENABLED = True
                records = {"missing_torrent": {"status": item_status, "torrent_hash": "a" * 40}}
                with open(config.VERIFIED_CLEANUP_STATE_PATH, "w", encoding="utf-8") as handle:
                    json.dump(records, handle)
                qbit = Mock()
                qbit.torrents.return_value = []
                cycle = verified_cleanup.run_verified_cleanup_cycle(
                    qbit=qbit, arr=object(), enabled=True
                )
                self.assertEqual(cycle, {"status": "ok", "results": []})
                snapshot = self._scheduler(True, "2026-09-27T10:00:00Z", cycle["status"], None)
                with patch.object(
                    verified_cleanup, "get_verified_cleanup_scheduler_status", return_value=snapshot
                ):
                    cleanup = status.build_operational_status()["verifiedCleanup"]
                    self.assertEqual(cleanup["status"], "degraded")
                    self.assertEqual(cleanup["lastResult"]["status"], item_status)
                    records["later_success"] = {"status": "deleted", "torrent_hash": "b" * 40}
                    with open(config.VERIFIED_CLEANUP_STATE_PATH, "w", encoding="utf-8") as handle:
                        json.dump(records, handle)
                    self.assertEqual(
                        status.build_operational_status()["verifiedCleanup"]["status"],
                        "degraded",
                    )
                    config.VERIFIED_CLEANUP_ENABLED = False
                    self.assertEqual(
                        status.build_operational_status()["verifiedCleanup"]["status"],
                        "disabled",
                    )
                    config.VERIFIED_CLEANUP_ENABLED = True
                qbit.torrents.assert_called_once_with()
                qbit.stop.assert_not_called()
                qbit.delete.assert_not_called()

    def test_scheduler_snapshot_requires_all_fields_and_fixed_codes(self):
        config.VERIFIED_CLEANUP_ENABLED = True
        with open(config.VERIFIED_CLEANUP_STATE_PATH, "w", encoding="utf-8") as handle:
            handle.write(OLD_DELETED_STATE)
        valid = self._scheduler(True, "2026-09-27T10:00:00Z", "ok", None)
        malformed = []
        for field in valid:
            missing = valid.copy()
            del missing[field]
            malformed.append((f"missing {field}", missing))
        malformed.extend([
            ("invalid timestamp", {**valid, "lastCycleAt": "not-a-timestamp"}),
            ("newline timestamp", {**valid, "lastCycleAt": "2026-09-27T10:00:00Z\n"}),
            ("invalid calendar date", {**valid, "lastCycleAt": "2026-02-30T10:00:00Z"}),
            ("unknown status", {**valid, "lastStatus": "privateidentifier"}),
            ("unknown error", {**valid, "lastError": "privateidentifier"}),
            ("wrong status type", {**valid, "lastStatus": False}),
            ("wrong error type", {**valid, "lastError": 7}),
        ])
        for label, raw in malformed:
            with self.subTest(label=label):
                with patch.object(
                    verified_cleanup, "get_verified_cleanup_scheduler_status", return_value=raw
                ):
                    cleanup = status.build_operational_status()["verifiedCleanup"]
                self.assertEqual(cleanup["status"], "degraded")
                self.assertEqual(cleanup["scheduler"], {
                    "running": False,
                    "lastCycleAt": None,
                    "lastStatus": "cleanup_cycle_failed",
                    "lastError": "cleanup_cycle_failed",
                })
                self.assertNotIn("privateidentifier", json.dumps(cleanup))

        for code in sorted(verified_cleanup._SAFE_CYCLE_STATUSES):
            with self.subTest(known_code=code):
                raw = {**valid, "lastStatus": code}
                with patch.object(
                    verified_cleanup, "get_verified_cleanup_scheduler_status", return_value=raw
                ):
                    self.assertEqual(
                        status.build_operational_status()["verifiedCleanup"]["scheduler"], raw
                    )

    def test_disabled_cleanup_stays_disabled_with_old_state(self):
        with open(config.VERIFIED_CLEANUP_STATE_PATH, "w", encoding="utf-8") as handle:
            handle.write(OLD_DELETED_STATE)
        cleanup = status.build_operational_status()["verifiedCleanup"]

        self.assertEqual(cleanup["status"], "disabled")
        self.assertEqual(
            cleanup["scheduler"],
            {"running": False, "lastCycleAt": None, "lastStatus": None, "lastError": None},
        )

    def test_scheduler_snapshot_never_carries_exception_text_or_paths(self):
        config.VERIFIED_CLEANUP_ENABLED = True
        hostile = self._scheduler(
            True,
            "Traceback (most recent call last): /root/.env",
            "qBittorrent login failed",
            "RuntimeError: connection refused for /data/media",
        )
        with patch.object(
            verified_cleanup, "get_verified_cleanup_scheduler_status", return_value=hostile
        ):
            result = status.build_operational_status()["verifiedCleanup"]

        self.assertEqual(
            result["scheduler"],
            {"running": False, "lastCycleAt": None, "lastStatus": "cleanup_cycle_failed", "lastError": "cleanup_cycle_failed"},
        )
        self.assertNotIn("/root/.env", json.dumps(result))
        self.assertNotIn("/data/media", json.dumps(result))
        self.assertNotIn("Traceback", json.dumps(result))
        self.assertEqual(result["status"], "degraded")

    def test_scheduler_snapshot_rejects_newline_codes_and_non_boolean_running(self):
        config.VERIFIED_CLEANUP_ENABLED = True
        with open(config.VERIFIED_CLEANUP_STATE_PATH, "w", encoding="utf-8") as handle:
            handle.write(OLD_DELETED_STATE)
        hostile = self._scheduler("false", "2026-09-27T10:00:00Z", "ok\n", "degraded\n")
        with patch.object(
            verified_cleanup, "get_verified_cleanup_scheduler_status", return_value=hostile
        ):
            cleanup = status.build_operational_status()["verifiedCleanup"]

        self.assertEqual(cleanup["scheduler"], {
            "running": False,
            "lastCycleAt": None,
            "lastStatus": "cleanup_cycle_failed",
            "lastError": "cleanup_cycle_failed",
        })
        self.assertEqual(cleanup["status"], "degraded")


if __name__ == "__main__":
    unittest.main()
