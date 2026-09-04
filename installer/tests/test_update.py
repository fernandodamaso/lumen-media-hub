import json
import os
import tempfile
import unittest
from pathlib import Path

from lumen_installer.update import (
    UpdateManifest,
    render_rollback_override,
    run_rollback,
    run_update,
)


class UpdateManifestTests(unittest.TestCase):
    def test_rejects_paths_under_media_or_downloads_and_serializes_only_approved_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "media"
            downloads = root / "downloads"
            approved = root / "config" / "runtime.json"
            approved.parent.mkdir()
            os.environ["ROOT_PATH"] = str(media)
            os.environ["DOWNLOADS_PATH"] = str(downloads)
            try:
                manifest = UpdateManifest.from_inputs(
                    root / ".env",
                    {"runtime": approved},
                    {"dashboard": "registry.example/dashboard:latest"},
                    {"dashboard": "abc123"},
                    {"dashboard": "local-id"},
                    ["requests"],
                    False,
                    [root / "docker-compose.yml"],
                )
                serialized = manifest.to_dict()
                serialized_paths = json.dumps(serialized)
                self.assertIn(str(approved.resolve()), serialized_paths)
                self.assertNotIn(str(media), serialized_paths)
                self.assertNotIn(str(downloads), serialized_paths)

                for field, value in (
                    ("env_path", media / ".env"),
                    ("runtime_paths", {"runtime": downloads / "runtime.json"}),
                    ("compose_files", [media / "docker-compose.yml"]),
                ):
                    inputs = {
                        "env_path": root / ".env",
                        "runtime_paths": {"runtime": approved},
                        "image_refs": {},
                        "repo_digests": {},
                        "local_image_ids": {},
                        "profiles": [],
                        "gpu_mode": False,
                        "compose_files": [root / "docker-compose.yml"],
                    }
                    inputs[field] = value
                    with self.subTest(field=field):
                        with self.assertRaises(ValueError):
                            UpdateManifest.from_inputs(**inputs)
            finally:
                os.environ.pop("ROOT_PATH", None)
                os.environ.pop("DOWNLOADS_PATH", None)


class UpdateOperationTests(unittest.TestCase):
    def _manifest(self, root):
        media = root / "media"
        downloads = root / "downloads"
        config = root / "config" / "service.conf"
        config.parent.mkdir()
        config.write_text("before", encoding="utf-8")
        os.environ["ROOT_PATH"] = str(media)
        os.environ["DOWNLOADS_PATH"] = str(downloads)
        self.addCleanup(os.environ.pop, "ROOT_PATH", None)
        self.addCleanup(os.environ.pop, "DOWNLOADS_PATH", None)
        return UpdateManifest.from_inputs(
            root / ".env",
            {"config": config},
            {"dashboard": "registry.example/dashboard:latest", "api": "registry.example/api:stable"},
            {"dashboard": "digest-dashboard", "api": "sha256:digest-api"},
            {"dashboard": "local-dashboard"},
            ["requests"],
            True,
            [root / "docker-compose.yml"],
        ), config

    def test_render_rollback_override_uses_registry_and_local_refs_without_pull_or_build(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, _ = self._manifest(root)
            rendered = render_rollback_override(manifest, "run-7", {"dashboard"})
            self.assertIn("image: registry.example/api@sha256:digest-api", rendered)
            self.assertIn("image: lumen-rollback/dashboard:run-7", rendered)
            self.assertIn("pull_policy: never", rendered)
            self.assertIn("build: null", rendered)

    def test_dry_run_does_not_write_or_invoke_callbacks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, _ = self._manifest(root)
            calls = []
            result = run_update(
                root,
                manifest,
                dry_run=True,
                confirm=False,
                pull_callback=lambda: calls.append("pull"),
                recreate_callback=lambda: calls.append("recreate"),
            )
            self.assertTrue(result["dry_run"])
            self.assertEqual([], calls)
            self.assertFalse((root / ".state").exists())

    def test_update_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, _ = self._manifest(root)
            with self.assertRaises(PermissionError):
                run_update(root, manifest, dry_run=False, confirm=False)
            self.assertFalse((root / ".state").exists())

    def test_update_records_manifest_and_runs_pull_before_recreate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, config = self._manifest(root)
            calls = []
            result = run_update(
                root,
                manifest,
                dry_run=False,
                confirm=True,
                pull_callback=lambda: calls.append("pull"),
                recreate_callback=lambda: calls.append("recreate"),
            )
            self.assertEqual(["pull", "recreate"], calls)
            recorded = root / ".state" / "installer" / "updates" / f"{result['run_id']}.json"
            self.assertTrue(recorded.is_file())
            self.assertEqual(manifest.to_dict(), json.loads(recorded.read_text(encoding="utf-8"))["manifest"])
            self.assertTrue((root / ".state" / "installer" / "backups" / result["run_id"] / "config" / "service.conf").is_file())
            self.assertEqual("before", config.read_text(encoding="utf-8"))

    def test_rollback_requires_confirmation_and_does_not_write_or_callback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, _ = self._manifest(root)
            updated = run_update(root, manifest, False, True)
            calls = []
            with self.assertRaises(PermissionError):
                run_rollback(root, updated["run_id"], False, lambda: calls.append("stop"), lambda: calls.append("start"))
            self.assertEqual([], calls)
            self.assertFalse((root / ".state" / "installer" / "failed-runs").exists())

    def test_rollback_moves_only_manifest_paths_restores_backup_and_starts_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, config = self._manifest(root)
            media_file = root / "media" / "do-not-touch.mkv"
            media_file.parent.mkdir()
            media_file.write_text("media", encoding="utf-8")
            updated = run_update(root, manifest, False, True)
            config.write_text("failed update", encoding="utf-8")
            calls = []
            result = run_rollback(
                root,
                updated["run_id"],
                True,
                lambda: calls.append("stop"),
                lambda: calls.append("start"),
            )
            self.assertEqual(["stop", "start"], calls)
            self.assertEqual("before", config.read_text(encoding="utf-8"))
            self.assertEqual("media", media_file.read_text(encoding="utf-8"))
            failed = root / ".state" / "installer" / "failed-runs" / updated["run_id"] / "config" / "service.conf"
            self.assertEqual("failed update", failed.read_text(encoding="utf-8"))
            self.assertEqual(updated["run_id"], result["run_id"])
            self.assertTrue(Path(result["override"]).is_file())


if __name__ == "__main__":
    unittest.main()
