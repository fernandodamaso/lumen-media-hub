import json
import importlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from lumen_installer.compose import ComposeOptions
from lumen_installer.compose import validate_storage_mounts
from lumen_installer.commands import CommandResult
from lumen_installer import cli
from lumen_installer import configure as configure_module
from lumen_installer.environment import plan_environment
from lumen_installer.errors import DriftError, InvalidInputError
from lumen_installer.services.qbittorrent import QbittorrentAdapter
from lumen_installer.setup import run_up
from lumen_installer.storage import validate_storage
from lumen_installer.update import UpdateManifest


setup_module = importlib.import_module("lumen_installer.setup")


class SeparateStorageContractTests(unittest.TestCase):
    def test_separate_mode_is_explicit_and_selects_its_compose_contract(self):
        options = ComposeOptions(storage_mode="separate")

        self.assertEqual(options.storage_mode, "separate")
        self.assertTrue(
            any(path.endswith("/docker-compose.separate.yml") for path in options.global_argv("/srv/lumen", "/srv/lumen/.env"))
        )

    def test_separate_storage_requires_matching_writable_mount_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "repo"
            library = base / "library"
            downloads = base / "downloads"
            repo.mkdir()
            library.mkdir()
            downloads.mkdir()

            def mount_probe(path):
                return {
                    "target": str(path),
                    "uuid": "0123456789ABCDEF",
                    "options": "rw",
                    "fstype": "ext4",
                }

            result = validate_storage(
                library,
                downloads,
                repo_root=repo,
                storage_mode="separate",
                expected_mount_uuid="0123456789ABCDEF",
                mount_probe=mount_probe,
                dry_run=True,
            )

            self.assertEqual(result.storage_mode, "separate")
            self.assertEqual(result.mount_identity["uuid"], "0123456789ABCDEF")

    def test_separate_storage_accepts_directory_on_matching_writable_mount(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "repo"
            library = base / "library"
            downloads = base / "downloads"
            repo.mkdir()
            library.mkdir()
            downloads.mkdir()

            def mount_probe(_path):
                return {
                    "target": str(base),
                    "uuid": "0123456789ABCDEF",
                    "options": "rw",
                    "fstype": "btrfs",
                }

            result = validate_storage(
                library,
                downloads,
                repo_root=repo,
                storage_mode="separate",
                expected_mount_uuid="0123456789ABCDEF",
                mount_probe=mount_probe,
                dry_run=True,
            )

            self.assertEqual(result.mount_identity["target"], str(base))

    def test_separate_storage_fails_closed_for_wrong_or_read_only_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "repo"
            library = base / "library"
            downloads = base / "downloads"
            repo.mkdir()
            library.mkdir()
            downloads.mkdir()

            for identity in (
                {"target": str(library), "uuid": "wrong", "options": "rw"},
                {
                    "target": str(library),
                    "uuid": "0123456789ABCDEF",
                    "options": "ro",
                    "fstype": "ext4",
                },
            ):
                with self.subTest(identity=identity):
                    with self.assertRaises(InvalidInputError):
                        validate_storage(
                            library,
                            downloads,
                            repo_root=repo,
                            storage_mode="separate",
                            expected_mount_uuid="0123456789ABCDEF",
                            mount_probe=lambda _path, value=identity: value,
                            dry_run=True,
                        )

    def test_separate_qbittorrent_uses_download_mount_without_changing_library_paths(self):
        adapter = QbittorrentAdapter(
            "http://127.0.0.1:8081",
            SimpleNamespace(request=lambda *args, **kwargs: None),
            environment={"STORAGE_MODE": "separate"},
        )

        self.assertEqual(adapter._default_save_path, "/downloads")
        self.assertEqual(adapter._category_paths["sonarr"], "/downloads/sonarr")

    def test_storage_mode_and_library_uuid_are_persisted_without_secret_values(self):
        plan = plan_environment(
            {
                "ROOT_PATH": "/srv/lumen-library",
                "DOWNLOADS_PATH": "/srv/lumen-staging",
            },
            {"uid": 1000, "gid": 1000, "timezone": "UTC"},
            {
                "STORAGE_MODE": "separate",
                "LIBRARY_MOUNT_UUID": "01234567-89ab-cdef",
            },
        )

        self.assertEqual(plan.values["STORAGE_MODE"], "separate")
        self.assertEqual(plan.values["LIBRARY_MOUNT_UUID"], "0123456789ABCDEF")

    def test_doctor_honors_separate_storage_mode_and_library_uuid(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            (repo / ".env").write_text(
                "STORAGE_MODE=separate\n"
                "LIBRARY_MOUNT_UUID=0123456789ABCDEF\n"
                "ROOT_PATH=/srv/library\n"
                "DOWNLOADS_PATH=/srv/downloads\n"
                "ACTIONS_TOKEN=token\n"
                "JELLYFIN_BIND_ADDRESS=127.0.0.1\n"
                "MANAGEMENT_BIND_ADDRESS=127.0.0.1\n"
                "PUBLIC_HOST=127.0.0.1\n",
                encoding="utf-8",
            )
            setup_module.InstallerState.new(
                repo,
                completed_stages=setup_module.FOUNDATION_STAGES,
            ).save()
            captured = {}

            def validate(*_args, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(report={"status": "ok"})

            state = SimpleNamespace(
                gpu_mode="none",
                completed_stages=setup_module.FOUNDATION_STAGES,
                report={"status": "ok"},
            )
            with mock.patch.object(setup_module, "validate_storage", side_effect=validate), \
                    mock.patch.object(setup_module.InstallerState, "load", return_value=state), \
                    mock.patch.object(setup_module, "gpu_diagnostics", return_value={"status": "disabled"}):
                report = setup_module.doctor_diagnostics(
                    repo,
                    host_report={"status": "ok"},
                    gpu_mode="none",
                )

        self.assertEqual(report["status"], "ok")
        self.assertEqual(captured["storage_mode"], "separate")
        self.assertFalse(captured["shared_mount_required"])
        self.assertEqual(captured["expected_mount_uuid"], "0123456789ABCDEF")

    def test_rendered_separate_compose_has_role_scoped_storage_mounts(self):
        repo = Path(__file__).resolve().parents[2]
        if shutil.which("docker") is None:
            self.skipTest("Docker is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            library = base / "library"
            downloads = base / "downloads"
            (library / "media").mkdir(parents=True)
            downloads.mkdir()
            env_file = base / ".env"
            env_file.write_text(
                (repo / ".env.example")
                .read_text(encoding="utf-8")
                .replace("STORAGE_MODE=shared", "STORAGE_MODE=separate")
                .replace("ROOT_PATH=.", f"ROOT_PATH={library}")
                .replace("DOWNLOADS_PATH=./downloads", f"DOWNLOADS_PATH={downloads}"),
                encoding="utf-8",
            )
            rendered = subprocess.run(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    str(env_file),
                    "-f",
                    str(repo / "docker-compose.yml"),
                    "-f",
                    str(repo / "docker-compose.separate.yml"),
                    "--profile",
                    "subtitles",
                    "--profile",
                    "maintenance",
                    "config",
                    "--format",
                    "json",
                ],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            payload = json.loads(rendered.stdout)
            validate_storage_mounts(
                payload,
                root_path=library,
                downloads_path=downloads,
                storage_mode="separate",
            )
            for service in ("sonarr", "radarr", "bazarr", "unpackerr"):
                mounts = payload["services"][service]["volumes"]
                self.assertIn(
                    {"type": "bind", "source": str(library / "media"), "target": "/data/media", "bind": {"create_host_path": False}},
                    mounts,
                )
                self.assertNotIn("/data", {item["target"] for item in mounts})
            qbit_targets = {item["target"] for item in payload["services"]["qbittorrent"]["volumes"]}
            self.assertEqual(qbit_targets, {"/downloads", "/config"})
            jellyfin_mounts = payload["services"]["jellyfin"]["volumes"]
            self.assertEqual(
                {item["target"] for item in jellyfin_mounts},
                {"/data/media", "/config"},
            )
            self.assertTrue(
                next(item for item in jellyfin_mounts if item["target"] == "/data/media")[
                    "read_only"
                ]
            )
            self.assertNotIn(
                "/guard-state",
                {
                    item["target"]
                    for item in payload["services"]["homepage-actions"]["volumes"]
                },
            )
            self.assertEqual(payload["services"]["qbittorrent"]["restart"], "unless-stopped")

    def test_rendered_validator_rejects_broad_root_storage_mount(self):
        payload = {
            "services": {
                "qbittorrent": {"volumes": [{"source": "/srv/library", "target": "/data"}]},
                "sonarr": {"volumes": [{"source": "/srv/library", "target": "/data"}, {"source": "/srv/downloads", "target": "/downloads"}]},
                "radarr": {"volumes": [{"source": "/srv/library", "target": "/data"}, {"source": "/srv/downloads", "target": "/downloads"}]},
            }
        }
        with self.assertRaisesRegex(InvalidInputError, "too broad|storage root is exposed"):
            validate_storage_mounts(
                payload,
                root_path="/srv/library",
                downloads_path="/srv/downloads",
                storage_mode="separate",
            )

    def test_rendered_validator_rejects_unexpected_reader_staging_mount(self):
        payload = {
            "services": {
                "qbittorrent": {
                    "volumes": [{"source": "/srv/downloads", "target": "/downloads"}]
                },
                "sonarr": {
                    "volumes": [
                        {"source": "/srv/library/media", "target": "/data/media"},
                        {"source": "/srv/downloads", "target": "/downloads"},
                    ]
                },
                "radarr": {
                    "volumes": [
                        {"source": "/srv/library/media", "target": "/data/media"},
                        {"source": "/srv/downloads", "target": "/downloads"},
                    ]
                },
                "jellyfin": {
                    "volumes": [
                        {
                            "source": "/srv/library/media",
                            "target": "/data/media",
                            "read_only": True,
                        },
                        {
                            "source": "/srv/downloads",
                            "target": "/downloads",
                            "read_only": True,
                        },
                    ]
                },
            }
        }

        with self.assertRaisesRegex(InvalidInputError, "unexpected"):
            validate_storage_mounts(
                payload,
                root_path="/srv/library",
                downloads_path="/srv/downloads",
                storage_mode="separate",
            )

    def test_rendered_validator_rejects_storage_mount_on_unknown_service(self):
        payload = {
            "services": {
                "qbittorrent": {
                    "volumes": [{"source": "/srv/downloads", "target": "/downloads"}]
                },
                "sonarr": {
                    "volumes": [
                        {"source": "/srv/library/media", "target": "/data/media"},
                        {"source": "/srv/downloads", "target": "/downloads"},
                    ]
                },
                "radarr": {
                    "volumes": [
                        {"source": "/srv/library/media", "target": "/data/media"},
                        {"source": "/srv/downloads", "target": "/downloads"},
                    ]
                },
                "unexpected": {
                    "volumes": [
                        {"source": "/srv/library/private", "target": "/private"}
                    ]
                },
            }
        }

        with self.assertRaisesRegex(InvalidInputError, "unexpected"):
            validate_storage_mounts(
                payload,
                root_path="/srv/library",
                downloads_path="/srv/downloads",
                storage_mode="separate",
            )

    def test_mount_identity_rejects_incomplete_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "repo"
            library = base / "library"
            downloads = base / "downloads"
            repo.mkdir()
            library.mkdir()
            downloads.mkdir()
            incomplete = (
                {"uuid": "0123456789ABCDEF", "options": "rw", "fstype": "ext4"},
                {"target": str(library), "options": "rw", "fstype": "ext4"},
                {"target": str(library), "uuid": "0123456789ABCDEF", "fstype": "ext4"},
                {"target": str(library), "uuid": "0123456789ABCDEF", "options": "rw"},
            )
            for identity in incomplete:
                with self.subTest(identity=identity):
                    with self.assertRaises(InvalidInputError):
                        validate_storage(
                            library,
                            downloads,
                            repo_root=repo,
                            storage_mode="separate",
                            expected_mount_uuid="0123456789ABCDEF",
                            mount_probe=lambda _path, value=identity: value,
                            dry_run=True,
                        )

    def test_missing_mount_uuid_is_rejected_for_explicit_separate_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "repo"
            library = base / "library"
            downloads = base / "downloads"
            repo.mkdir()
            library.mkdir()
            downloads.mkdir()

            with self.assertRaisesRegex(InvalidInputError, "mount UUID"):
                validate_storage(
                    library,
                    downloads,
                    repo_root=repo,
                    storage_mode="separate",
                    dry_run=True,
                )

    def test_configure_resolves_saved_storage_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".env").write_text(
                "STORAGE_MODE=separate\n"
                "ROOT_PATH=/srv/lumen-library\n"
                "DOWNLOADS_PATH=/srv/lumen-staging\n",
                encoding="utf-8",
            )

            options = configure_module._resolve_configure_options(
                root, ComposeOptions(), dry_run=True
            )

            self.assertEqual(options.storage_mode, "separate")

    def test_up_preflights_separate_storage_and_expanded_container_mounts(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "repo"
            library = base / "library"
            downloads = base / "downloads"
            repo.mkdir()
            (repo / ".git").mkdir()
            library.mkdir()
            downloads.mkdir()
            (repo / ".env").write_text(
                f"STORAGE_MODE=separate\n"
                f"LIBRARY_MOUNT_UUID=0123456789ABCDEF\n"
                f"ROOT_PATH={library}\n"
                f"DOWNLOADS_PATH={downloads}\n",
                encoding="utf-8",
            )
            payload = {
                "services": {
                    service: {
                        "volumes": [
                            {"source": str(downloads), "target": "/downloads"}
                            if service == "qbittorrent"
                            else {"source": str(library / "media"), "target": "/data/media"},
                            *([] if service == "qbittorrent" else [{"source": str(downloads), "target": "/downloads"}]),
                        ]
                    }
                    for service in ("qbittorrent", "sonarr", "radarr")
                }
            }

            class Runner:
                def run(self, argv, **_kwargs):
                    return CommandResult(tuple(argv), 0, json.dumps(payload))

            calls = []

            def storage_validator(*args, **kwargs):
                calls.append((args, kwargs))
                return {"storage_mode": "separate"}

            result = run_up(
                repo,
                runner=Runner(),
                options=ComposeOptions(storage_mode="separate"),
                dry_run=True,
                storage_validator=storage_validator,
                stale_finder=lambda *_args, **_kwargs: (),
            )

            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1]["storage_mode"], "separate")
            self.assertTrue(
                any("docker-compose.separate.yml" in item for item in result.planned_commands[0])
            )

    def test_up_rejects_legacy_disjoint_paths_without_storage_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "repo"
            library = base / "library"
            downloads = base / "downloads"
            repo.mkdir()
            (repo / ".git").mkdir()
            library.mkdir()
            downloads.mkdir()
            (repo / ".env").write_text(
                f"ROOT_PATH={library}\nDOWNLOADS_PATH={downloads}\n",
                encoding="utf-8",
            )

            with self.assertRaises(DriftError):
                run_up(
                    repo,
                    dry_run=True,
                    stale_finder=lambda *_args, **_kwargs: (),
                    storage_validator=lambda *args, **kwargs: self.fail(
                        "legacy layout reached storage validation"
                    ),
                )

    def test_up_rejects_missing_storage_paths_before_compose(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            (repo / ".env").write_text("STORAGE_MODE=shared\n", encoding="utf-8")

            with self.assertRaisesRegex(InvalidInputError, "both ROOT_PATH"):
                run_up(
                    repo,
                    runner=mock.Mock(),
                    dry_run=True,
                    stale_finder=lambda *_args, **_kwargs: (),
                )

    def test_update_manifest_round_trips_storage_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compose = root / "docker-compose.yml"
            compose.write_text("services: {}\n", encoding="utf-8")
            manifest = UpdateManifest.from_inputs(
                env_path=root / ".env",
                runtime_paths={},
                image_refs={},
                repo_digests={},
                local_image_ids={},
                profiles=(),
                gpu_mode="none",
                compose_files=(compose,),
                storage_mode="separate",
            )

            restored = UpdateManifest.from_dict(manifest.to_dict())

            self.assertEqual(restored.storage_mode, "separate")

    def test_update_preflights_the_separate_container_storage_view(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            root.mkdir()
            library = base / "library"
            downloads = base / "downloads"
            library.mkdir()
            downloads.mkdir()
            (root / "docker-compose.yml").write_text(
                "services:\n  qbittorrent:\n    image: example/qbt:stable\n",
                encoding="utf-8",
            )
            (root / "docker-compose.separate.yml").write_text("services: {}\n", encoding="utf-8")
            (root / ".env").write_text(
                f"STORAGE_MODE=separate\n"
                f"LIBRARY_MOUNT_UUID=0123456789ABCDEF\n"
                f"ROOT_PATH={library}\n"
                f"DOWNLOADS_PATH={downloads}\n",
                encoding="utf-8",
            )
            payload = {
                "services": {
                    service: {
                        "volumes": [
                            {"source": str(downloads), "target": "/downloads"}
                            if service == "qbittorrent"
                            else {"source": str(library / "media"), "target": "/data/media"},
                            *([] if service == "qbittorrent" else [{"source": str(downloads), "target": "/downloads"}]),
                        ]
                    }
                    for service in ("qbittorrent", "sonarr", "radarr")
                }
            }

            class Runner:
                def __init__(self):
                    self.calls = []

                def run(self, argv, **_kwargs):
                    self.calls.append(tuple(argv))
                    return CommandResult(tuple(argv), 0, json.dumps(payload))

            args = SimpleNamespace(profiles=None, gpu_mode="none", gpu=None, dev=False, storage_mode=None)
            runner = Runner()
            with mock.patch.object(cli, "validate_storage") as storage_check:
                manifest = cli._update_manifest(root, args, dry_run=True, runner=runner)

            storage_check.assert_called_once()
            self.assertEqual(storage_check.call_args.kwargs["storage_mode"], "separate")
            self.assertEqual(manifest.storage_mode, "separate")
            self.assertIn(str(root / "docker-compose.separate.yml"), manifest.compose_files)
            self.assertTrue(any(call[-3:] == ("config", "--format", "json") for call in runner.calls))

    def test_update_validates_implicit_shared_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            library = base / "library"
            downloads = library / "downloads"
            root.mkdir()
            downloads.mkdir(parents=True)
            (root / "docker-compose.yml").write_text(
                "services:\n  qbittorrent:\n    image: example/qbt:stable\n",
                encoding="utf-8",
            )
            (root / ".env").write_text(
                f"ROOT_PATH={library}\nDOWNLOADS_PATH={downloads}\n",
                encoding="utf-8",
            )
            args = SimpleNamespace(
                profiles=None, gpu_mode="none", gpu=None, dev=False, storage_mode=None
            )

            with mock.patch.object(cli, "validate_storage") as storage_check:
                manifest = cli._update_manifest(root, args, dry_run=True)

            storage_check.assert_called_once()
            self.assertEqual(storage_check.call_args.kwargs["storage_mode"], "shared")
            self.assertEqual(manifest.storage_mode, "shared")

    def test_configure_preflights_the_separate_container_storage_view(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            root.mkdir()
            library = base / "library"
            downloads = base / "downloads"
            library.mkdir()
            downloads.mkdir()
            payload = {
                "services": {
                    service: {
                        "volumes": [
                            {"source": str(downloads), "target": "/downloads"}
                            if service == "qbittorrent"
                            else {"source": str(library / "media"), "target": "/data/media"},
                            *([] if service == "qbittorrent" else [{"source": str(downloads), "target": "/downloads"}]),
                        ]
                    }
                    for service in ("qbittorrent", "sonarr", "radarr")
                }
            }

            class Runner:
                def run(self, argv, **_kwargs):
                    return CommandResult(tuple(argv), 0, json.dumps(payload))

            with mock.patch.object(configure_module, "validate_storage") as storage_check:
                result = configure_module.run_configure(
                    root,
                    runner=Runner(),
                    options=ComposeOptions(storage_mode="separate"),
                    environment={
                        "STORAGE_MODE": "separate",
                        "LIBRARY_MOUNT_UUID": "0123456789ABCDEF",
                        "ROOT_PATH": str(library),
                        "DOWNLOADS_PATH": str(downloads),
                    },
                    storage_validator=storage_check,
                    reconcile=lambda *_args, **_kwargs: {"status": "ok"},
                    restart=lambda: None,
                    direct_health=lambda: True,
                    proxy_health=lambda: True,
                )

            self.assertEqual(result.status, "ok")
            self.assertEqual(storage_check.call_args.kwargs["storage_mode"], "separate")


if __name__ == "__main__":
    unittest.main()
