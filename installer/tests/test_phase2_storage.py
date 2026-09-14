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
from lumen_installer.errors import InvalidInputError
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
                    "uuid": "B8A426BFA4267FCC",
                    "options": "rw",
                    "fstype": "ext4",
                }

            result = validate_storage(
                library,
                downloads,
                repo_root=repo,
                storage_mode="separate",
                expected_mount_uuid="B8A426BFA4267FCC",
                mount_probe=mount_probe,
                dry_run=True,
            )

            self.assertEqual(result.storage_mode, "separate")
            self.assertEqual(result.mount_identity["uuid"], "B8A426BFA4267FCC")

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
                    "uuid": "B8A426BFA4267FCC",
                    "options": "rw",
                    "fstype": "btrfs",
                }

            result = validate_storage(
                library,
                downloads,
                repo_root=repo,
                storage_mode="separate",
                expected_mount_uuid="B8A426BFA4267FCC",
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
                    "uuid": "B8A426BFA4267FCC",
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
                            expected_mount_uuid="B8A426BFA4267FCC",
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
                "ROOT_PATH": "/run/media/admin/ARQUIVOS",
                "DOWNLOADS_PATH": "/home/admin/lumen-downloads",
            },
            {"uid": 1000, "gid": 1000, "timezone": "UTC"},
            {
                "STORAGE_MODE": "separate",
                "LIBRARY_MOUNT_UUID": "b8a426bf-a426-7fcc",
            },
        )

        self.assertEqual(plan.values["STORAGE_MODE"], "separate")
        self.assertEqual(plan.values["LIBRARY_MOUNT_UUID"], "B8A426BFA4267FCC")

    def test_doctor_honors_separate_storage_mode_and_library_uuid(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            (repo / ".env").write_text(
                "STORAGE_MODE=separate\n"
                "LIBRARY_MOUNT_UUID=B8A426BFA4267FCC\n"
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
        self.assertEqual(captured["expected_mount_uuid"], "B8A426BFA4267FCC")

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
            self.assertTrue(payload["services"]["jellyfin"]["volumes"][0]["read_only"])
            self.assertEqual(payload["services"]["jellyfin"]["volumes"][0]["target"], "/data/media")

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
                {"uuid": "B8A426BFA4267FCC", "options": "rw", "fstype": "ext4"},
                {"target": str(library), "options": "rw", "fstype": "ext4"},
                {"target": str(library), "uuid": "B8A426BFA4267FCC", "fstype": "ext4"},
                {"target": str(library), "uuid": "B8A426BFA4267FCC", "options": "rw"},
            )
            for identity in incomplete:
                with self.subTest(identity=identity):
                    with self.assertRaises(InvalidInputError):
                        validate_storage(
                            library,
                            downloads,
                            repo_root=repo,
                            storage_mode="separate",
                            expected_mount_uuid="B8A426BFA4267FCC",
                            mount_probe=lambda _path, value=identity: value,
                            dry_run=True,
                        )

    def test_staged_writer_contract_preserves_lifecycle_ownership(self):
        repo = Path(__file__).resolve().parents[2]
        unit = (repo / "installer/artifacts/phase9/lumen-storage-writers.service").read_text(encoding="utf-8")
        helper = (repo / "installer/artifacts/phase9/lumen-storage-writers").read_text(encoding="utf-8")
        self.assertIn("Requires=run-media-admin-ARQUIVOS.mount docker.service", unit)
        self.assertIn("BindsTo=run-media-admin-ARQUIVOS.mount docker.service", unit)
        self.assertIn("ExecStart=/usr/bin/bash /home/admin/Projects/lumen-media-hub/installer/artifacts/phase9/lumen-storage-writers start", unit)
        self.assertIn('services = ["qbittorrent", "sonarr", "radarr"]', helper)
        self.assertIn('services.append("bazarr")', helper)
        self.assertIn('services.append("unpackerr")', helper)
        self.assertIn('values.get("COMPOSE_FILE", "")', helper)

    def test_staged_writer_stop_releases_owned_containers_with_bad_config(self):
        repo = Path(__file__).resolve().parents[2]
        helper = repo / "installer/artifacts/phase9/lumen-storage-writers"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".env").write_text("STORAGE_MODE=separate\nmalformed = \"unterminated\n", encoding="utf-8")
            (root / ".state").mkdir()
            (root / ".state/installer").mkdir()
            (root / ".state/installer/state.json").write_text("not json", encoding="utf-8")
            capture = root / "docker-args.txt"
            fake_docker = root / "docker"
            fake_docker.write_text(
                "#!/usr/bin/env bash\n"
                "if [ \"$1\" = container ] && [ \"$2\" = inspect ]; then\n"
                "  printf '/%s\\n' \"$5\"\n"
                "  exit 0\n"
                "fi\n"
                "printf '%s\\n' \"$@\" > \"$LUMEN_CAPTURE\"\n",
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)
            environment = dict(os.environ)
            environment.update(
                {
                    "LUMEN_WRITER_REPO": str(root),
                    "LUMEN_WRITER_DOCKER_BIN": str(fake_docker),
                    "LUMEN_CAPTURE": str(capture),
                }
            )
            result = subprocess.run(
                ["bash", str(helper), "stop"],
                capture_output=True,
                text=True,
                env=environment,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            argv = capture.read_text(encoding="utf-8").splitlines()
            self.assertEqual(argv[:3], ["container", "stop", "--time"])
            for service in ("qbittorrent", "sonarr", "radarr", "bazarr", "unpackerr"):
                self.assertIn(service, argv)
            self.assertNotIn("compose", argv)

    def test_staged_writer_stop_releases_owned_containers_without_config(self):
        repo = Path(__file__).resolve().parents[2]
        helper = repo / "installer/artifacts/phase9/lumen-storage-writers"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            capture = root / "docker-args.txt"
            fake_docker = root / "docker"
            fake_docker.write_text(
                "#!/usr/bin/env bash\n"
                "if [ \"$1\" = container ] && [ \"$2\" = inspect ]; then\n"
                "  printf '/%s\\n' \"$5\"\n"
                "  exit 0\n"
                "fi\n"
                "printf '%s\\n' \"$@\" > \"$LUMEN_CAPTURE\"\n",
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)
            environment = dict(os.environ)
            environment.update(
                {
                    "LUMEN_WRITER_REPO": str(root),
                    "LUMEN_WRITER_DOCKER_BIN": str(fake_docker),
                    "LUMEN_CAPTURE": str(capture),
                }
            )
            result = subprocess.run(
                ["bash", str(helper), "stop"],
                capture_output=True,
                text=True,
                env=environment,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("qbittorrent", capture.read_text(encoding="utf-8"))

    def test_staged_writer_start_renders_and_validates_before_up(self):
        repo = Path(__file__).resolve().parents[2]
        helper = repo / "installer/artifacts/phase9/lumen-storage-writers"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            root.mkdir()
            (root / "installer").symlink_to(repo / "installer", target_is_directory=True)
            library = base / "library"
            downloads = base / "downloads"
            (library / "media").mkdir(parents=True)
            downloads.mkdir()
            (root / ".state/installer").mkdir(parents=True)
            (root / ".state/installer/state.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profiles": ["subtitles", "maintenance"],
                        "gpu_mode": "none",
                        "owned_resources": {},
                        "completed_stages": [],
                    }
                ),
                encoding="utf-8",
            )
            for name in ("base.yml", "host-override.yml", "tail.yml", "docker-compose.separate.yml"):
                (root / name).write_text("services: {}\n", encoding="utf-8")
            (root / ".env").write_text(
                f"STORAGE_MODE=separate\n"
                f"ROOT_PATH={library}\n"
                f"DOWNLOADS_PATH={downloads}\n"
                "LIBRARY_MOUNT_UUID=B8A426BFA4267FCC\n"
                "MIN_FREE_SPACE_GIB=0\n"
                "BAZARR_ENABLED=true\n"
                "COMPOSE_FILE=base.yml:host-override.yml:docker-compose.separate.yml:tail.yml\n",
                encoding="utf-8",
            )
            mount_probe = root / "findmnt"
            mount_probe.write_text(
                "#!/usr/bin/env bash\n"
                "target=\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = --target ]; then target=\"$2\"; shift 2; else shift; fi\n"
                "done\n"
                "printf '{\"filesystems\":[{\"target\":\"%s\",\"uuid\":\"B8A426BFA4267FCC\",\"options\":\"rw,relatime\",\"fstype\":\"ext4\"}]}\\n' \"$target\"\n",
                encoding="utf-8",
            )
            mount_probe.chmod(0o755)
            capture = root / "docker-calls.txt"
            rendered = root / "rendered.json"
            fake_docker = root / "docker"

            def storage(source, target, read_only=False):
                item = {"type": "bind", "source": str(source), "target": target}
                if read_only:
                    item["read_only"] = True
                return item

            payload = {
                "services": {
                    "qbittorrent": {"restart": "no", "volumes": [storage(downloads, "/downloads")]},
                    "sonarr": {"restart": "no", "volumes": [storage(library / "media", "/data/media"), storage(downloads, "/downloads")]},
                    "radarr": {"restart": "no", "volumes": [storage(library / "media", "/data/media"), storage(downloads, "/downloads")]},
                    "bazarr": {"restart": "no", "volumes": [storage(library / "media", "/data/media")]},
                    "unpackerr": {"restart": "no", "volumes": [storage(library / "media", "/data/media"), storage(downloads, "/downloads")]},
                    "jellyfin": {"restart": "unless-stopped", "volumes": [storage(library / "media", "/data/media", True)]},
                    "homepage-actions": {"restart": "unless-stopped", "volumes": [storage(library / "media", "/data/media", True), storage(downloads, "/downloads", True)]},
                }
            }
            rendered.write_text(json.dumps(payload), encoding="utf-8")
            fake_docker.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$@\" >> \"$LUMEN_CAPTURE\"\n"
                "is_config=false\n"
                "for arg in \"$@\"; do [ \"$arg\" = config ] && is_config=true; done\n"
                "if [ \"$is_config\" = true ]; then cat \"$LUMEN_RENDERED\"; fi\n",
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)
            environment = dict(os.environ)
            environment.update(
                {
                    "PATH": f"{root}:{environment.get('PATH', '')}",
                    "LUMEN_WRITER_REPO": str(root),
                    "LUMEN_WRITER_DOCKER_BIN": str(fake_docker),
                    "LUMEN_CAPTURE": str(capture),
                    "LUMEN_RENDERED": str(rendered),
                }
            )
            result = subprocess.run(
                ["bash", str(helper), "start"],
                capture_output=True,
                text=True,
                env=environment,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = capture.read_text(encoding="utf-8").splitlines()
            self.assertIn("config", calls)
            self.assertIn("up", calls)
            for service in ("qbittorrent", "sonarr", "radarr", "bazarr", "unpackerr"):
                self.assertIn(service, calls)
            files = [calls[index + 1] for index, item in enumerate(calls[:-1]) if item == "-f"]
            self.assertEqual(files[-1], str(root / "docker-compose.separate.yml"))

    def test_staged_writer_start_rejects_invalid_render_without_up(self):
        repo = Path(__file__).resolve().parents[2]
        helper = repo / "installer/artifacts/phase9/lumen-storage-writers"
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            root.mkdir()
            (root / "installer").symlink_to(repo / "installer", target_is_directory=True)
            library = base / "library"
            downloads = base / "downloads"
            (library / "media").mkdir(parents=True)
            downloads.mkdir()
            (root / ".env").write_text(
                f"STORAGE_MODE=separate\nROOT_PATH={library}\nDOWNLOADS_PATH={downloads}\n"
                "LIBRARY_MOUNT_UUID=B8A426BFA4267FCC\nMIN_FREE_SPACE_GIB=0\n",
                encoding="utf-8",
            )
            rendered = root / "rendered.json"
            capture = root / "docker-calls.txt"
            fake_docker = root / "docker"
            mount_probe = root / "findmnt"
            mount_probe.write_text(
                "#!/usr/bin/env bash\n"
                "target=\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = --target ]; then target=\"$2\"; shift 2; else shift; fi\n"
                "done\n"
                "printf '{\"filesystems\":[{\"target\":\"%s\",\"uuid\":\"B8A426BFA4267FCC\",\"options\":\"rw\",\"fstype\":\"ext4\"}]}\\n' \"$target\"\n",
                encoding="utf-8",
            )
            mount_probe.chmod(0o755)
            fake_docker.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$@\" >> \"$LUMEN_CAPTURE\"\n"
                "cat \"$LUMEN_RENDERED\"\n",
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)
            base_services = {
                "qbittorrent": {"restart": "no", "volumes": [{"source": str(downloads), "target": "/downloads"}]},
                "sonarr": {"restart": "no", "volumes": [{"source": str(library / "media"), "target": "/data/media"}, {"source": str(downloads), "target": "/downloads"}]},
                "radarr": {"restart": "no", "volumes": [{"source": str(library / "media"), "target": "/data/media"}, {"source": str(downloads), "target": "/downloads"}]},
            }
            for invalid in ("restart", "mount"):
                with self.subTest(invalid=invalid):
                    payload = {"services": json.loads(json.dumps(base_services))}
                    if invalid == "restart":
                        payload["services"]["sonarr"]["restart"] = "unless-stopped"
                    else:
                        payload["services"]["qbittorrent"]["volumes"] = [{"source": str(library), "target": "/data"}]
                    rendered.write_text(json.dumps(payload), encoding="utf-8")
                    capture.write_text("", encoding="utf-8")
                    environment = dict(os.environ)
                    environment.update(
                        {
                            "PATH": f"{root}:{environment.get('PATH', '')}",
                            "LUMEN_WRITER_REPO": str(root),
                            "LUMEN_WRITER_DOCKER_BIN": str(fake_docker),
                            "LUMEN_CAPTURE": str(capture),
                            "LUMEN_RENDERED": str(rendered),
                        }
                    )
                    result = subprocess.run(
                        ["bash", str(helper), "start"],
                        capture_output=True,
                        text=True,
                        env=environment,
                        check=False,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("up", capture.read_text(encoding="utf-8").splitlines())

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
                "ROOT_PATH=/run/media/admin/ARQUIVOS\n"
                "DOWNLOADS_PATH=/home/admin/lumen-downloads\n",
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
                f"LIBRARY_MOUNT_UUID=B8A426BFA4267FCC\n"
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
                f"LIBRARY_MOUNT_UUID=B8A426BFA4267FCC\n"
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
                        "LIBRARY_MOUNT_UUID": "B8A426BFA4267FCC",
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
