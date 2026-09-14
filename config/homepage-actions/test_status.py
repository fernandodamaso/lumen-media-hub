"""Focused tests for the bounded staged status projection."""

import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import config
import status
from clients.trakt import TraktTokenState, TraktTokenStore


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

    def tearDown(self):
        for key, value in self.old.items():
            setattr(config, key, value)

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
        self.assertEqual(result["retention"]["scheduler"], {"enabled": False, "running": False})

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


if __name__ == "__main__":
    unittest.main()
