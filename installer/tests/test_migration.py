import json
import sys
import tempfile
import unittest
import contextlib
import io
from pathlib import Path
from types import SimpleNamespace


INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.disk_guard import DEFAULT_LIBRARY_UUID, GIB
from lumen_installer.migration import main, run_dry_run


class MigrationDryRunTests(unittest.TestCase):
    def _mount_probe(self, mapping):
        def probe(path):
            return {
                "target": str(path),
                "source": mapping[path][0],
                "uuid": mapping[path][1],
                "options": "rw",
                "fstype": mapping[path][2],
            }

        return probe

    def _statvfs_probe(self, available):
        return lambda _path: SimpleNamespace(f_bavail=available // 4096, f_frsize=4096)

    def _payload(self, source, destination):
        return {
            "inventory_complete": True,
            "storage": {"library_uuid": DEFAULT_LIBRARY_UUID},
            "files": [
                {
                    "id": "torrent-a/movie.mkv",
                    "source": str(source),
                    "destination": str(destination),
                    "selected": True,
                    "registered": True,
                    "verified_cleanup": True,
                    "torrent": {"hash": "A" * 40, "registered": True},
                    "arr": {"service": "sonarr", "id": 7},
                    "metadata": {"source_device": 101, "destination_device": 202},
                }
            ],
            "queue": [
                {
                    "id": "torrent-a",
                    "runtime_minutes": 45,
                    "media_type": "episode_file",
                    "imported": True,
                    "verified": True,
                    "partial_pack": False,
                    "source_registered": True,
                }
            ],
            "retention": {"status": "disabled", "reason": "disabled"},
            "services": {"radarr_api": "healthy", "trakt_oauth": "disabled", "history_complete": True},
            "flags": {
                "verified_cleanup_enabled": False,
                "disk_guard_enabled": False,
                "retention_enabled": False,
            },
        }

    def test_manifest_is_deterministic_and_cross_disk_copy_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            library = root / "library"
            staging.mkdir()
            library.mkdir()
            source = staging / "torrent-a" / "movie.mkv"
            destination = library / "tv" / "movie.mkv"
            source.parent.mkdir()
            destination.parent.mkdir()
            source.write_bytes(b"stable source")
            source.write_bytes(source.read_bytes())
            probes = self._mount_probe(
                {
                    staging: ("/dev/main", None, "btrfs"),
                    library: ("/dev/library", DEFAULT_LIBRARY_UUID, "ntfs"),
                }
            )
            first = run_dry_run(
                self._payload(source, destination),
                source_path=staging,
                library_path=library,
                mount_probe=probes,
                statvfs_probe=self._statvfs_probe(200 * GIB),
            )
            second = run_dry_run(
                self._payload(source, destination),
                source_path=staging,
                library_path=library,
                mount_probe=probes,
                statvfs_probe=self._statvfs_probe(200 * GIB),
            )

            self.assertEqual(first.status, "ready")
            self.assertEqual(first.manifest, second.manifest)
            item = first.manifest["files"][0]
            self.assertEqual(item["transition"], "copy_verify_commit_then_delete")
            self.assertTrue(item["hardlink"]["cross_filesystem"])
            self.assertFalse(item["hardlink"]["possible"])
            self.assertFalse(item["hardlink"]["claimed"])
            self.assertEqual(item["transitions"]["copy"], "planned_after_freeze")
            self.assertEqual(
                item["transitions"]["delete_source"],
                "blocked_until_verified_cleanup_revalidation",
            )
            self.assertEqual(first.manifest["storage"]["capacity"]["staging_reserve_bytes"], 75 * GIB)
            self.assertEqual(first.manifest["storage"]["capacity"]["library_reserve_bytes"], 50 * GIB)
            self.assertEqual(first.manifest["storage"]["capacity"]["resume_margin_bytes"], 10 * GIB)
            self.assertFalse(first.manifest["mutation"]["performed"])
            self.assertFalse(destination.exists())

    def test_conflicts_orphans_and_temporary_names_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            library = root / "library"
            staging.mkdir()
            library.mkdir()
            source = staging / "registered.mkv"
            destination = library / "registered.mkv"
            source.write_bytes(b"source")
            destination.write_bytes(b"different")
            temp_source = staging / ".lumen-copy-temp.mkv"
            temp_source.write_bytes(b"temporary")
            payload = self._payload(source, destination)
            payload["inventory_complete"] = True
            payload["files"].append(
                {
                    "id": "temp",
                    "source": str(temp_source),
                    "destination": str(library / "temp.mkv"),
                    "selected": True,
                    "registered": True,
                    "verified_cleanup": True,
                    "torrent": {"hash": "B" * 40, "api_key": "never-print"},
                    "arr": {"service": "radarr", "id": 8},
                }
            )
            payload["files"][0]["registered"] = False
            payload["orphan_staging_paths"] = [str(source), str(temp_source)]
            payload["services"] = {"radarr_api": "degraded", "trakt_oauth": "missing", "history_complete": False}
            probes = self._mount_probe(
                {
                    staging: ("/dev/main", None, "btrfs"),
                    library: ("/dev/library", DEFAULT_LIBRARY_UUID, "ntfs"),
                }
            )
            result = run_dry_run(
                payload,
                source_path=staging,
                library_path=library,
                mount_probe=probes,
                statvfs_probe=self._statvfs_probe(200 * GIB),
            )

            self.assertEqual(result.status, "blocked")
            self.assertIn("radarr_api_degraded", result.blockers)
            self.assertIn("trakt_oauth_missing", result.blockers)
            self.assertIn("incomplete_history", result.blockers)
            self.assertIn("file:torrent-a/movie.mkv:destination_collision", result.blockers)
            self.assertIn("file:torrent-a/movie.mkv:orphan_or_unregistered_staging", result.blockers)
            self.assertEqual(result.manifest["counts"]["temporary_files_excluded"], 1)
            self.assertNotIn(str(temp_source), result.manifest["inventory"]["orphan_staging_paths"])
            self.assertNotIn("never-print", json.dumps(result.manifest, sort_keys=True))
            self.assertEqual(result.manifest["mutation"]["moves"], 0)
            self.assertEqual(result.manifest["mutation"]["deletes"], 0)
            self.assertEqual(
                result.manifest["contracts"]["verified_cleanup"]["failure_recovery"],
                "preserve_ambiguous_delete",
            )
            self.assertEqual(
                result.manifest["contracts"]["retention"]["restart_recovery"],
                "preserve_pending_unmonitor_intent",
            )
            self.assertEqual(
                result.manifest["contracts"]["disk_guard"]["failure_recovery"],
                "pause_and_stop_writer_on_guard_failure",
            )
            self.assertEqual(source.read_bytes(), b"source")
            self.assertEqual(destination.read_bytes(), b"different")

    def test_low_space_and_identity_failure_never_fall_back_to_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            library = root / "library"
            staging.mkdir()
            library.mkdir()
            source = staging / "movie.mkv"
            source.write_bytes(b"large enough")
            payload = self._payload(source, library / "movie.mkv")
            payload["services"] = {"radarr_api": "healthy", "trakt_oauth": "disabled", "history_complete": True}
            probes = self._mount_probe(
                {
                    staging: ("/dev/main", None, "btrfs"),
                    library: ("/dev/library", DEFAULT_LIBRARY_UUID, "ntfs"),
                }
            )
            result = run_dry_run(
                payload,
                source_path=staging,
                library_path=library,
                mount_probe=probes,
                statvfs_probe=self._statvfs_probe(70 * GIB),
            )
            capacity = result.manifest["storage"]["capacity"]
            self.assertEqual(capacity["staging_available_bytes"], 70 * GIB)
            self.assertEqual(capacity["library_available_bytes"], 70 * GIB)
            self.assertEqual(capacity["resume_floor"]["staging_bytes"], 85 * GIB)
            self.assertIn("unaffordable_capacity", result.manifest["files"][0]["preservation_reasons"])

            missing = root / "missing"
            failed = run_dry_run(
                payload,
                source_path=missing,
                library_path=library,
                mount_probe=probes,
                statvfs_probe=self._statvfs_probe(200 * GIB),
            )
            self.assertTrue(any(item.startswith("staging_identity:") for item in failed.blockers))
            self.assertIsNone(failed.manifest["storage"]["staging"]["available_bytes"])

    def test_cli_requires_explicit_dry_run_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            library = root / "library"
            staging.mkdir()
            library.mkdir()
            source = staging / "movie.mkv"
            source.write_bytes(b"fixture")
            fixture = root / "fixture.json"
            fixture.write_text(json.dumps(self._payload(source, library / "movie.mkv")), encoding="utf-8")
            manifest = root / "manifest.json"
            with contextlib.redirect_stdout(io.StringIO()):
                result = main(
                    [
                        "--fixture",
                        str(fixture),
                        "--staging-path",
                        str(staging),
                        "--library-path",
                        str(library),
                        "--manifest",
                        str(manifest),
                        "--dry-run",
                    ]
                )
            self.assertEqual(result, 4)
            self.assertTrue(manifest.is_file())
            document = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(document["schema_version"], 1)
            self.assertFalse(document["mutation"]["performed"])


if __name__ == "__main__":
    unittest.main()
