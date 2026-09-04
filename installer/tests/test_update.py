import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from lumen_installer.update import (
    UpdateManifest,
    render_rollback_override,
    run_rollback,
    run_update,
)
from lumen_installer.errors import ExitCode, InvalidInputError, PartialError


class UpdateManifestTests(unittest.TestCase):
    @staticmethod
    def _compose(root, contents="services:\n  api:\n    image: registry.example/api:stable\n"):
        compose = root / "docker-compose.yml"
        compose.write_text(contents, encoding="utf-8")
        return compose

    def test_rejects_local_image_ids_for_registry_services(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            compose = root / "docker-compose.yml"
            compose.write_text(
                "services:\n  api:\n    image: registry.example/api:stable\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                UpdateManifest.from_inputs(
                    root / ".env",
                    {},
                    {"api": "registry.example/api:stable"},
                    {},
                    {"api": "fabricated-local-id"},
                    [],
                    "none",
                    [compose],
                )

    def test_rejects_unsafe_nested_symlink_in_approved_config_tree(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "config"
            config.mkdir()
            outside = root / "outside-secret"
            outside.write_text("private", encoding="utf-8")
            (config / "nested-link").symlink_to(outside)
            with self.assertRaises(ValueError):
                UpdateManifest.from_inputs(
                    root / ".env",
                    {"config": config},
                    {"api": "registry.example/api:stable"},
                    {"api": "sha256:" + "a" * 64},
                    {},
                    [],
                    "none",
                    [root / "docker-compose.yml"],
                )

    def test_from_dict_rejects_tampered_schema_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            compose = root / "docker-compose.yml"
            compose.write_text(
                "services:\n  api:\n    image: registry.example/api:stable\n",
                encoding="utf-8",
            )
            manifest = UpdateManifest.from_inputs(
                root / ".env",
                {},
                {"api": "registry.example/api:stable"},
                {"api": "sha256:" + "a" * 64},
                {},
                ["requests"],
                "none",
                [compose],
            )
            for field, value in (
                ("gpu_mode", "evil"),
                ("profiles", ["--remove-orphans"]),
                ("image_refs", {"--remove-orphans": "registry.example/api:stable"}),
                ("repo_digests", {"--remove-orphans": "sha256:" + "a" * 64}),
                ("compose_files", str(compose)),
            ):
                with self.subTest(field=field):
                    tampered = manifest.to_dict()
                    tampered[field] = value
                    with self.assertRaises(ValueError):
                        UpdateManifest.from_dict(tampered)
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
                    {"dashboard": "sha256:" + "0" * 64},
                    {"dashboard": "local-id"},
                    ["requests"],
                    False,
                    [
                        self._compose(
                            root,
                            "services:\n"
                            "  dashboard:\n"
                            "    build: .\n"
                            "    image: registry.example/dashboard:latest\n",
                        )
                    ],
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

    def test_rejects_outside_traversal_and_symlinked_approved_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "checkout"
            root.mkdir()
            (root / "config").mkdir()
            outside = Path(temp_dir) / "outside.json"
            outside.write_text("private", encoding="utf-8")
            linked = root / "config" / "linked.json"
            linked.symlink_to(outside)
            common = {
                "env_path": root / ".env",
                "runtime_paths": {"runtime": root / "config" / "runtime.json"},
                "image_refs": {"api": "registry.example/api:stable"},
                "repo_digests": {"api": "sha256:" + "a" * 64},
                "local_image_ids": {},
                "profiles": [],
                "gpu_mode": False,
                "compose_files": [root / "docker-compose.yml"],
            }
            for path in (outside, root / "config" / ".." / "outside.json", linked):
                with self.subTest(path=path):
                    candidate = dict(common)
                    candidate["runtime_paths"] = {"runtime": path}
                    with self.assertRaises(ValueError):
                        UpdateManifest.from_inputs(**candidate)

    def test_rejects_recursive_installer_state_backup_destinations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state = root / ".state" / "installer"
            common = {
                "env_path": root / ".env",
                "image_refs": {"api": "registry.example/api:stable"},
                "repo_digests": {"api": "sha256:" + "a" * 64},
                "local_image_ids": {},
                "profiles": [],
                "gpu_mode": False,
                "compose_files": [root / "docker-compose.yml"],
            }
            for candidate in (state, state / "backups", state / "backups" / "old-run"):
                with self.subTest(candidate=candidate):
                    with self.assertRaises(ValueError):
                        UpdateManifest.from_inputs(
                            runtime_paths={"runtime": candidate}, **common
                        )

    def test_rejects_operational_installer_paths_as_runtime_inputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state = root / ".state" / "installer"
            common = {
                "env_path": root / ".env",
                "image_refs": {"api": "registry.example/api:stable"},
                "repo_digests": {"api": "sha256:" + "a" * 64},
                "local_image_ids": {},
                "profiles": [],
                "gpu_mode": "none",
                "compose_files": [self._compose(root)],
            }
            for candidate in (
                state / "failed-runs",
                state / "rollback",
                state / "updates",
                state / "backups",
                state / "updates" / "run-1.json",
                state / "backups" / "run-1" / "config",
            ):
                with self.subTest(candidate=candidate):
                    with self.assertRaises(ValueError):
                        UpdateManifest.from_inputs(
                            runtime_paths={"runtime": candidate}, **common
                        )

    def test_rejects_unknown_profiles_in_inputs_and_persisted_manifests(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            compose = self._compose(root)
            common = {
                "env_path": root / ".env",
                "runtime_paths": {},
                "image_refs": {"api": "registry.example/api:stable"},
                "repo_digests": {"api": "sha256:" + "a" * 64},
                "local_image_ids": {},
                "gpu_mode": "none",
                "compose_files": [compose],
            }
            with self.assertRaises(ValueError):
                UpdateManifest.from_inputs(profiles=["evil"], **common)
            manifest = UpdateManifest.from_inputs(profiles=[], **common)
            tampered = manifest.to_dict()
            tampered["profiles"] = ["evil"]
            with self.assertRaises(ValueError):
                UpdateManifest.from_dict(tampered)

    def test_requires_existing_compose_and_valid_build_metadata_for_local_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            common = {
                "env_path": root / ".env",
                "runtime_paths": {},
                "image_refs": {"built": "local/built:local"},
                "repo_digests": {},
                "local_image_ids": {"built": "sha256:built"},
                "profiles": [],
                "gpu_mode": "none",
            }
            with self.assertRaises(ValueError):
                UpdateManifest.from_inputs(
                    compose_files=[root / "docker-compose.yml"], **common
                )
            malformed = root / "docker-compose.yml"
            malformed.write_text(
                "services:\n  built:\n    build:\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                UpdateManifest.from_inputs(compose_files=[malformed], **common)

    def test_accepts_build_only_service_local_id_without_an_image_reference(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            compose = self._compose(
                root,
                "services:\n"
                "  dashboard:\n"
                "    build: .\n",
            )
            manifest = UpdateManifest.from_inputs(
                root / ".env",
                {},
                {},
                {},
                {"dashboard": "sha256:built"},
                [],
                "none",
                [compose],
            )

            self.assertEqual({}, manifest.image_refs)
            self.assertEqual({"dashboard": "sha256:built"}, manifest.local_image_ids)
            rendered = render_rollback_override(
                manifest,
                "run-1",
                {"dashboard"},
                {"dashboard": "lumen-rollback/dashboard:run-1"},
            )
            self.assertIn("image: lumen-rollback/dashboard:run-1", rendered)

    def test_local_build_override_requires_verified_rollback_tag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            compose = self._compose(
                root,
                "services:\n"
                "  built:\n"
                "    build: .\n"
                "    image: local/built:local\n",
            )
            manifest = UpdateManifest.from_inputs(
                root / ".env",
                {},
                {"built": "local/built:local"},
                {},
                {"built": "sha256:built"},
                [],
                "none",
                [compose],
            )
            with self.assertRaises(InvalidInputError):
                render_rollback_override(manifest, "run-1", {"built"})
            with self.assertRaises(InvalidInputError):
                render_rollback_override(
                    manifest,
                    "run-1",
                    {"built"},
                    {"built": "lumen-rollback/built:wrong"},
                )

    def test_validates_immutable_digest_forms_and_requires_registry_digests(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base = {
                "env_path": root / ".env",
                "runtime_paths": {},
                "image_refs": {"api": "registry.example/api:stable"},
                "repo_digests": {"api": "registry.example/api@sha256:" + "b" * 64},
                "local_image_ids": {},
                "profiles": [],
                "gpu_mode": False,
                "compose_files": [root / "docker-compose.yml"],
            }
            manifest = UpdateManifest.from_inputs(**base)
            self.assertEqual("sha256:" + "b" * 64, manifest.repo_digests["api"])

            for invalid in (
                "registry.example/api:latest",
                "md5:" + "c" * 64,
                "sha256:" + "d" * 63,
                "registry.example/api@sha256:" + "e" * 64 + "extra",
            ):
                with self.subTest(invalid=invalid):
                    candidate = dict(base)
                    candidate["repo_digests"] = {"api": invalid}
                    with self.assertRaises(ValueError):
                        UpdateManifest.from_inputs(**candidate)

            missing = dict(base)
            missing["repo_digests"] = {}
            missing_manifest = UpdateManifest.from_inputs(**missing)
            with self.assertRaises(ValueError):
                render_rollback_override(missing_manifest, "run-7", set())

    def test_compose_accepts_rollback_override_and_removes_build(self):
        if shutil.which("docker") is None:
            self.skipTest("Docker is not installed")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base = root / "docker-compose.yml"
            base.write_text(
                "services:\n"
                "  api:\n"
                "    build:\n"
                "      context: .\n"
                "    image: registry.example/api:stable\n",
                encoding="utf-8",
            )
            manifest = UpdateManifest.from_inputs(
                root / ".env",
                {},
                {"api": "registry.example/api:stable"},
                {"api": "registry.example/api@sha256:" + "f" * 64},
                {},
                [],
                False,
                [base],
            )
            override = root / "rollback.yml"
            override.write_text(
                render_rollback_override(manifest, "run-7", set()), encoding="utf-8"
            )
            completed = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(base),
                    "-f",
                    str(override),
                    "config",
                    "--no-interpolate",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("image: registry.example/api@sha256:" + "f" * 64, completed.stdout)
            self.assertNotIn("build:", completed.stdout)


class UpdateOperationTests(unittest.TestCase):
    def _manifest(self, root):
        media = root / "media"
        downloads = root / "downloads"
        config = root / "config" / "service.conf"
        config.parent.mkdir()
        config.write_text("before", encoding="utf-8")
        (root / "docker-compose.yml").write_text(
            "services:\n"
            "  dashboard:\n"
            "    build: .\n"
            "    image: registry.example/dashboard:latest\n"
            "  api:\n"
            "    image: registry.example/api:stable\n",
            encoding="utf-8",
        )
        os.environ["ROOT_PATH"] = str(media)
        os.environ["DOWNLOADS_PATH"] = str(downloads)
        self.addCleanup(os.environ.pop, "ROOT_PATH", None)
        self.addCleanup(os.environ.pop, "DOWNLOADS_PATH", None)
        return UpdateManifest.from_inputs(
            root / ".env",
            {"config": config},
            {"dashboard": "registry.example/dashboard:latest", "api": "registry.example/api:stable"},
            {"dashboard": "sha256:" + "1" * 64, "api": "sha256:" + "2" * 64},
            {"dashboard": "local-dashboard"},
            ["requests"],
            True,
            [root / "docker-compose.yml"],
        ), config

    @staticmethod
    def _update(root, manifest, **kwargs):
        kwargs.setdefault(
            "tag_callback",
            lambda run_id: {
                "dashboard": f"lumen-rollback/dashboard:{run_id}"
            },
        )
        return run_update(root, manifest, False, True, **kwargs)

    def test_render_rollback_override_uses_registry_and_local_refs_without_pull_or_build(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, _ = self._manifest(root)
            rendered = render_rollback_override(
                manifest,
                "run-7",
                {"dashboard"},
                {"dashboard": "lumen-rollback/dashboard:run-7"},
            )
            self.assertIn("image: registry.example/api@sha256:" + "2" * 64, rendered)
            self.assertIn("image: lumen-rollback/dashboard:run-7", rendered)
            self.assertIn("pull_policy: never", rendered)
            self.assertIn("build: !reset null", rendered)

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
            with self.assertRaises(InvalidInputError):
                run_update(root, manifest, dry_run=False, confirm=False)
            self.assertFalse((root / ".state").exists())

    def test_update_rejects_every_symlinked_state_boundary_without_mutation(self):
        boundaries = (
            ".state",
            ".state/installer",
            ".state/installer/updates",
            ".state/installer/rollback",
            ".state/installer/failed-runs",
        )
        for boundary in boundaries:
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                manifest, _ = self._manifest(root)
                link = root / boundary
                link.parent.mkdir(parents=True, exist_ok=True)
                target = root.parent / f"{root.name}-outside-{boundary.replace('/', '-')}"
                target.mkdir()
                link.symlink_to(target, target_is_directory=True)

                with self.assertRaises(InvalidInputError) as raised:
                    run_update(root, manifest, dry_run=False, confirm=True)

                self.assertEqual(ExitCode.INVALID, raised.exception.exit_code)
                self.assertFalse((target / "installer").exists())
                self.assertTrue(link.is_symlink())

    def test_backup_filesystem_failure_is_stable_and_keeps_live_files_untouched(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, config = self._manifest(root)
            calls = []
            with mock.patch(
                "lumen_installer.update._copy_path",
                side_effect=OSError("backup contains a secret detail"),
            ):
                with self.assertRaises(PartialError) as raised:
                    run_update(
                        root,
                        manifest,
                        dry_run=False,
                        confirm=True,
                        pull_callback=lambda: calls.append("pull"),
                        recreate_callback=lambda: calls.append("recreate"),
                    )

            self.assertEqual(ExitCode.PARTIAL, raised.exception.exit_code)
            self.assertNotIn("secret detail", str(raised.exception))
            self.assertEqual("before", config.read_text(encoding="utf-8"))
            self.assertEqual([], calls)

    def test_update_rejects_manifest_from_a_different_checkout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "requested"
            manifest_root = Path(temp_dir) / "manifest"
            root.mkdir()
            manifest_root.mkdir()
            manifest, _ = self._manifest(manifest_root)
            with self.assertRaises(ValueError):
                run_update(root, manifest, dry_run=False, confirm=True)
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

    def test_update_records_absent_manifest_paths_and_rolls_back_new_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, _ = self._manifest(root)
            new_path = root / "config" / "created-after-update.json"
            manifest = UpdateManifest.from_inputs(
                manifest.env_path,
                {"config": root / "config" / "service.conf", "new": new_path},
                manifest.image_refs,
                manifest.repo_digests,
                manifest.local_image_ids,
                manifest.profiles,
                manifest.gpu_mode,
                manifest.compose_files,
            )
            updated = self._update(root, manifest)
            record_path = Path(updated["record"])
            record = json.loads(record_path.read_text(encoding="utf-8"))
            entries = {entry["path"]: entry for entry in record["backup_entries"]}
            absent = entries["config/created-after-update.json"]
            self.assertFalse(absent["present"])
            self.assertEqual({"kind": "absent"}, absent["inventory"])
            self.assertFalse(
                (Path(updated["backup"]) / absent["backup"]).exists()
            )

            new_path.write_text("created by failed update", encoding="utf-8")
            run_rollback(root, updated["run_id"], True)
            self.assertFalse(new_path.exists())
            failed_path = (
                root
                / ".state"
                / "installer"
                / "failed-runs"
                / updated["run_id"]
                / "config"
                / "created-after-update.json"
            )
            self.assertEqual("created by failed update", failed_path.read_text(encoding="utf-8"))

    def test_rollback_rejects_deleted_manifest_entry_before_stop_or_live_move(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, config = self._manifest(root)
            updated = self._update(root, manifest)
            record_path = Path(updated["record"])
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["backup_entries"].pop()
            record_path.write_text(json.dumps(record), encoding="utf-8")
            config.write_text("must remain live", encoding="utf-8")
            calls = []
            with self.assertRaises(InvalidInputError):
                run_rollback(
                    root,
                    updated["run_id"],
                    True,
                    lambda: calls.append("stop"),
                    lambda: calls.append("start"),
                )
            self.assertEqual([], calls)
            self.assertEqual("must remain live", config.read_text(encoding="utf-8"))

    def test_rollback_rejects_extra_backup_entry_before_stop_or_live_move(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, config = self._manifest(root)
            updated = run_update(
                root,
                manifest,
                False,
                True,
                tag_callback=lambda run_id: {
                    "dashboard": f"lumen-rollback/dashboard:{run_id}"
                },
            )
            record_path = Path(updated["record"])
            record = json.loads(record_path.read_text(encoding="utf-8"))
            backup_dir = Path(updated["backup"])
            extra = backup_dir / "unexpected"
            extra.write_text("must not be accepted", encoding="utf-8")
            record["backup_entries"].append(
                {
                    "path": "unexpected",
                    "backup": "unexpected",
                    "present": True,
                    "inventory": {"kind": "file", "file": {"sha256": "x", "size": 1}},
                }
            )
            record_path.write_text(json.dumps(record), encoding="utf-8")
            config.write_text("must remain live", encoding="utf-8")
            calls = []
            with self.assertRaises(InvalidInputError):
                run_rollback(
                    root,
                    updated["run_id"],
                    True,
                    lambda: calls.append("stop"),
                    lambda: calls.append("start"),
                )
            self.assertEqual([], calls)
            self.assertEqual("must remain live", config.read_text(encoding="utf-8"))

    def test_update_tags_before_pull_and_records_rollback_tags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, _ = self._manifest(root)
            calls = []
            result = run_update(
                root,
                manifest,
                dry_run=False,
                confirm=True,
                tag_callback=lambda run_id: calls.append(("tag", run_id))
                or {"dashboard": f"lumen-rollback/dashboard:{run_id}"},
                pull_callback=lambda run_id: calls.append(("pull", run_id)),
                recreate_callback=lambda run_id: calls.append(("recreate", run_id)),
            )
            run_id = result["run_id"]
            self.assertEqual(
                [("tag", run_id), ("pull", run_id), ("recreate", run_id)], calls
            )
            record = json.loads(Path(result["record"]).read_text(encoding="utf-8"))
            self.assertEqual(
                {"dashboard": f"lumen-rollback/dashboard:{run_id}"},
                record["local_rollback_tags"],
            )

    def test_update_lifecycle_failure_returns_partial_and_keeps_rollback_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, _ = self._manifest(root)
            result = run_update(
                root,
                manifest,
                dry_run=False,
                confirm=True,
                pull_callback=lambda: (_ for _ in ()).throw(RuntimeError("secret detail")),
            )
            self.assertEqual(4, result["exit_code"])
            self.assertEqual("failed", result["status"])
            self.assertTrue(Path(result["record"]).is_file())
            self.assertNotIn("secret detail", json.dumps(result))

    def test_update_recreate_or_health_failure_is_partial_after_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, _ = self._manifest(root)
            for failure in ("recreate", "health"):
                with self.subTest(failure=failure):
                    callback = lambda: (_ for _ in ()).throw(RuntimeError(failure))
                    result = run_update(
                        root,
                        manifest,
                        dry_run=False,
                        confirm=True,
                        recreate_callback=callback,
                    )
                    self.assertEqual(4, result["exit_code"])
                    self.assertTrue(Path(result["record"]).is_file())

    def test_rollback_requires_confirmation_and_does_not_write_or_callback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, _ = self._manifest(root)
            updated = self._update(root, manifest)
            calls = []
            with self.assertRaises(InvalidInputError):
                run_rollback(root, updated["run_id"], False, lambda: calls.append("stop"), lambda: calls.append("start"))
            self.assertEqual([], calls)
            self.assertFalse((root / ".state" / "installer" / "failed-runs").exists())

    def test_rollback_dry_run_is_read_only_even_without_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            calls = []
            result = run_rollback(
                root,
                "run-7",
                False,
                lambda: calls.append("stop"),
                lambda: calls.append("start"),
                dry_run=True,
            )
            self.assertEqual(
                {"action": "rollback", "dry_run": True, "run_id": "run-7"}, result
            )
            self.assertEqual([], calls)
            self.assertFalse((root / ".state").exists())

    def test_rollback_rejects_every_symlinked_state_boundary_without_callbacks(self):
        boundaries = (
            ".state",
            ".state/installer",
            ".state/installer/updates",
            ".state/installer/rollback",
            ".state/installer/failed-runs",
        )
        for boundary in boundaries:
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                link = root / boundary
                if link.exists() or link.is_symlink():
                    if link.is_dir() and not link.is_symlink():
                        shutil.rmtree(link)
                    else:
                        link.unlink()
                target = root.parent / f"{root.name}-rollback-outside-{boundary.replace('/', '-')}"
                target.mkdir()
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(target, target_is_directory=True)
                calls = []

                with self.assertRaises(InvalidInputError) as raised:
                    run_rollback(
                        root,
                        "run-7",
                        True,
                        lambda: calls.append("stop"),
                        lambda: calls.append("start"),
                    )

                self.assertEqual(ExitCode.INVALID, raised.exception.exit_code)
                self.assertEqual([], calls)
                self.assertFalse((target / "failed-runs").exists())

    def test_rollback_moves_only_manifest_paths_restores_backup_and_starts_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, config = self._manifest(root)
            media_file = root / "media" / "do-not-touch.mkv"
            media_file.parent.mkdir()
            media_file.write_text("media", encoding="utf-8")
            updated = self._update(root, manifest)
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

    def test_rollback_rejects_record_for_a_different_checkout_before_callbacks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first_root = Path(temp_dir) / "first"
            second_root = Path(temp_dir) / "second"
            first_root.mkdir()
            second_root.mkdir()
            manifest, _ = self._manifest(first_root)
            updated = self._update(first_root, manifest)
            source_record = Path(updated["record"])
            target_record = second_root / ".state" / "installer" / "updates" / source_record.name
            target_record.parent.mkdir(parents=True)
            shutil.copy2(source_record, target_record)
            calls = []
            with self.assertRaises(ValueError):
                run_rollback(
                    second_root,
                    updated["run_id"],
                    True,
                    lambda: calls.append("stop"),
                    lambda: calls.append("start"),
                )
            self.assertEqual([], calls)

    def test_rollback_rejects_symlink_in_backup_before_touching_live_or_media_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, config = self._manifest(root)
            media_file = root / "media" / "do-not-touch.mkv"
            download_file = root / "downloads" / "do-not-touch.part"
            media_file.parent.mkdir()
            download_file.parent.mkdir()
            media_file.write_text("media", encoding="utf-8")
            download_file.write_text("download", encoding="utf-8")
            updated = self._update(root, manifest)
            config.write_text("post-update", encoding="utf-8")
            backup_file = (
                root
                / ".state"
                / "installer"
                / "backups"
                / updated["run_id"]
                / "config"
                / "service.conf"
            )
            external = root / "outside-secret"
            external.write_text("must-not-restore", encoding="utf-8")
            backup_file.unlink()
            backup_file.symlink_to(external)
            calls = []
            with self.assertRaises(ValueError):
                run_rollback(
                    root,
                    updated["run_id"],
                    True,
                    lambda: calls.append("stop"),
                    lambda: calls.append("start"),
                )
            self.assertEqual([], calls)
            self.assertEqual("post-update", config.read_text(encoding="utf-8"))
            self.assertEqual("media", media_file.read_text(encoding="utf-8"))
            self.assertEqual("download", download_file.read_text(encoding="utf-8"))

    def test_rollback_rejects_missing_recorded_backup_before_stop_or_live_move(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, config = self._manifest(root)
            updated = self._update(root, manifest)
            backup_file = (
                root
                / ".state"
                / "installer"
                / "backups"
                / updated["run_id"]
                / "config"
                / "service.conf"
            )
            backup_file.unlink()
            config.write_text("post-update", encoding="utf-8")
            calls = []
            with self.assertRaises(InvalidInputError):
                run_rollback(
                    root,
                    updated["run_id"],
                    True,
                    lambda: calls.append("stop"),
                    lambda: calls.append("start"),
                )
            self.assertEqual([], calls)
            self.assertEqual("post-update", config.read_text(encoding="utf-8"))

    def test_rollback_rejects_tampered_unverified_local_tag_before_stop(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, _ = self._manifest(root)
            updated = self._update(root, manifest)
            record_path = Path(updated["record"])
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["local_rollback_tags"] = {
                "dashboard": "lumen-rollback/dashboard:fake"
            }
            record_path.write_text(json.dumps(record), encoding="utf-8")
            calls = []
            with self.assertRaises(InvalidInputError):
                run_rollback(
                    root,
                    updated["run_id"],
                    True,
                    lambda: calls.append("stop"),
                    lambda: calls.append("start"),
                )
            self.assertEqual([], calls)

    def test_rollback_rejects_missing_or_malformed_records_as_stable_installer_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            updates = root / ".state" / "installer" / "updates"
            updates.mkdir(parents=True)
            for contents in (None, "{not-json", json.dumps({"run_id": "wrong"})):
                with self.subTest(contents=contents):
                    record = updates / "run-7.json"
                    if contents is None:
                        record.unlink(missing_ok=True)
                    else:
                        record.write_text(contents, encoding="utf-8")
                    with self.assertRaises(InvalidInputError) as raised:
                        run_rollback(root, "run-7", True)
                    self.assertNotIn(str(root), str(raised.exception))
                    self.assertNotIn("not-json", str(raised.exception))

    def test_rollback_rejects_tampered_manifest_without_key_or_secret_leakage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            updates = root / ".state" / "installer" / "updates"
            updates.mkdir(parents=True)
            secret = "super-secret-token"
            (updates / "run-7.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-7",
                        "manifest": {
                            "env_path": str(root / ".env"),
                            "secret": secret,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(InvalidInputError) as raised:
                run_rollback(root, "run-7", True)
            self.assertNotIn(secret, str(raised.exception))
            self.assertNotIn("env_path", str(raised.exception))

    def test_rollback_rejects_symlinked_record_without_reading_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            updates = root / ".state" / "installer" / "updates"
            updates.mkdir(parents=True)
            target = root / "outside-secret-record.json"
            target.write_text('{"run_id":"run-7"}', encoding="utf-8")
            (updates / "run-7.json").symlink_to(target)
            with self.assertRaises(InvalidInputError) as raised:
                run_rollback(root, "run-7", True)
            self.assertNotIn(str(target), str(raised.exception))

    def test_env_restore_failure_keeps_post_update_env_and_recoverable_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest, config = self._manifest(root)
            env_path = Path(manifest.env_path)
            env_path.write_text("before", encoding="utf-8")
            env_path.chmod(0o600)
            media_file = root / "media" / "do-not-touch.mkv"
            download_file = root / "downloads" / "do-not-touch.part"
            media_file.parent.mkdir()
            download_file.parent.mkdir()
            media_file.write_text("media", encoding="utf-8")
            download_file.write_text("download", encoding="utf-8")
            updated = self._update(root, manifest)
            env_path.write_text("post-update", encoding="utf-8")
            env_path.chmod(0o600)
            with mock.patch(
                "lumen_installer.update.os.replace",
                side_effect=OSError("simulated atomic restore failure"),
            ):
                with self.assertRaises(OSError):
                    run_rollback(root, updated["run_id"], True)
            self.assertEqual("post-update", env_path.read_text(encoding="utf-8"))
            self.assertEqual(0o600, env_path.stat().st_mode & 0o777)
            failed_env = (
                root
                / ".state"
                / "installer"
                / "failed-runs"
                / updated["run_id"]
                / ".env"
            )
            self.assertEqual("post-update", failed_env.read_text(encoding="utf-8"))
            self.assertEqual("media", media_file.read_text(encoding="utf-8"))
            self.assertEqual("download", download_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
