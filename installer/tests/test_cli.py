import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_ROOT = WORKTREE_ROOT / "installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer import cli
from lumen_installer.errors import (
    DriftError,
    ExitCode,
    InstallerError,
    InvalidInputError,
    PartialError,
)
from lumen_installer.compose import ComposeOptions


class CliContractTests(unittest.TestCase):
    def test_help_is_successful_and_lists_every_public_command(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = cli.main(["--help"])

        self.assertEqual(result, int(ExitCode.OK))
        help_text = output.getvalue()
        for command in cli.PUBLIC_COMMANDS:
            self.assertIn(command, help_text)

    def test_command_discovery_accepts_exact_public_commands(self):
        parser = cli.build_parser()

        accepted = {parser.parse_args([command]).command for command in cli.PUBLIC_COMMANDS}

        self.assertEqual(accepted, {
            "setup",
            "doctor",
            "up",
            "down",
            "frontend-dev",
            "redeploy-dashboard",
            "configure",
            "connect-trakt",
            "update",
        })

    def test_shared_host_and_answers_options_work_before_or_after_command(self):
        parser = cli.build_parser()

        before = parser.parse_args(
            [
                "--uid",
                "1001",
                "--gid",
                "1002",
                "--tz",
                "UTC",
                "--answers",
                "answers.json",
                "--non-interactive",
                "setup",
            ]
        )
        after = parser.parse_args(
            [
                "doctor",
                "--puid",
                "01001",
                "--pgid",
                "01002",
                "--timezone",
                "Europe/Lisbon",
                "--answers",
                "answers.json",
                "--non-interactive",
            ]
        )

        self.assertEqual((before.uid, before.gid), (1001, 1002))
        self.assertEqual(before.timezone, "UTC")
        self.assertEqual(before.answers, "answers.json")
        self.assertTrue(before.noninteractive)
        self.assertEqual((after.uid, after.gid), (1001, 1002))
        self.assertEqual(after.timezone, "Europe/Lisbon")
        self.assertTrue(after.noninteractive)

    def test_configure_accepts_explicit_drift_confirmation(self):
        parser = cli.build_parser()
        args = parser.parse_args(["configure", "--confirm"])
        self.assertTrue(args.confirm)

    def test_update_wires_checkout_manifest_and_flags_to_update_helper(self):
        fake_result = {"run_id": "run-7", "api_token": "must-not-escape"}
        output = io.StringIO()
        with mock.patch.object(cli, "run_update", return_value=fake_result) as run_update:
            with contextlib.redirect_stdout(output):
                result = cli.main(["update", "--confirm", "--dry-run"])

        self.assertEqual(result, int(ExitCode.OK))
        run_update.assert_called_once()
        root, manifest = run_update.call_args.args[:2]
        self.assertEqual(root, WORKTREE_ROOT)
        self.assertIsInstance(manifest, cli.UpdateManifest)
        self.assertEqual(manifest.env_path, str((WORKTREE_ROOT / ".env").resolve()))
        self.assertEqual(
            manifest.runtime_paths,
            {
                "config": str((WORKTREE_ROOT / "config").resolve()),
                "state": str(
                    (WORKTREE_ROOT / ".state" / "installer" / "state.json").resolve()
                ),
            },
        )
        self.assertTrue(run_update.call_args.kwargs["confirm"])
        self.assertTrue(run_update.call_args.kwargs["dry_run"])
        self.assertIn("redacted", output.getvalue())
        self.assertNotIn("must-not-escape", output.getvalue())

    def test_update_rollback_wires_run_id_and_confirmation_to_rollback_helper(self):
        fake_result = {"run_id": "run-7", "secret": "must-not-escape"}
        output = io.StringIO()
        with mock.patch.object(cli, "run_rollback", return_value=fake_result) as run_rollback:
            with contextlib.redirect_stdout(output):
                result = cli.main(["update", "--rollback", "run-7", "--confirm"])

        self.assertEqual(result, int(ExitCode.OK))
        run_rollback.assert_called_once()
        root, run_id = run_rollback.call_args.args[:2]
        self.assertEqual(root, WORKTREE_ROOT)
        self.assertEqual(run_id, "run-7")
        self.assertTrue(run_rollback.call_args.kwargs["confirm"])
        self.assertIn("redacted", output.getvalue())
        self.assertNotIn("must-not-escape", output.getvalue())

    def test_update_rollback_dry_run_is_read_only(self):
        output = io.StringIO()
        with mock.patch.object(cli, "run_rollback") as run_rollback:
            with contextlib.redirect_stdout(output):
                result = cli.main(["update", "--rollback", "run-7", "--dry-run"])

        self.assertEqual(result, int(ExitCode.OK))
        run_rollback.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertEqual(report["action"], "rollback")
        self.assertEqual(report["run_id"], "run-7")
        self.assertTrue(report["dry_run"])

    def test_update_propagates_helper_exit_code(self):
        output = io.StringIO()
        with mock.patch.object(
            cli,
            "run_update",
            return_value={"exit_code": int(ExitCode.PARTIAL)},
        ):
            with contextlib.redirect_stdout(output):
                result = cli.main(["update", "--dry-run"])

        self.assertEqual(result, int(ExitCode.PARTIAL))

    def test_update_manifest_inspects_images_and_keeps_only_active_profiles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / "docker-compose.yml").write_text(
                "services:\n"
                "  core:\n"
                "    image: registry.example/core:latest\n"
                "  optional:\n"
                "    image: registry.example/optional:latest\n"
                "    profiles: [requests]\n"
                "  built:\n"
                "    build:\n"
                "      context: .\n"
                "    image: local/built:local\n",
                encoding="utf-8",
            )
            (root / ".env").write_text("COMPOSE_PROFILES=requests\n", encoding="utf-8")
            inspected = {
                "registry.example/core:latest": {
                    "Id": "sha256:core",
                    "RepoDigests": ["registry.example/core@sha256:" + "1" * 64],
                },
                "registry.example/optional:latest": {
                    "Id": "sha256:optional",
                    "RepoDigests": ["registry.example/optional@sha256:" + "2" * 64],
                },
                "local/built:local": {"Id": "sha256:built", "RepoDigests": []},
            }
            calls = []

            def execute(argv, **_kwargs):
                calls.append(tuple(argv))
                reference = argv[-1]
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(inspected[reference]),
                    stderr="",
                )

            args = SimpleNamespace(
                profiles=None,
                gpu_mode="vaapi",
                gpu=None,
                dev=False,
            )
            manifest = cli._update_manifest(
                root,
                args,
                dry_run=False,
                runner=cli.CommandRunner(executor=execute),
            )
            self.assertEqual(["requests"], manifest.profiles)
            self.assertEqual("vaapi", manifest.gpu_mode)
            self.assertEqual(
                [str(root / "docker-compose.yml"), str(root / "docker-compose.vaapi.yml")],
                manifest.compose_files,
            )
            self.assertEqual(
                {"core", "optional", "built"}, set(manifest.image_refs)
            )
            self.assertEqual("sha256:built", manifest.local_image_ids["built"])
            self.assertEqual(3, len(calls))

    def test_update_manifest_uses_saved_profiles_when_env_profiles_are_absent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / "docker-compose.yml").write_text(
                "services:\n"
                "  core:\n"
                "    image: registry.example/core:stable\n"
                "  requests:\n"
                "    image: registry.example/requests:stable\n"
                "    profiles: [requests]\n"
                "  subtitles:\n"
                "    image: registry.example/subtitles:stable\n"
                "    profiles: [subtitles]\n",
                encoding="utf-8",
            )
            (root / ".env").write_text("GPU_MODE=none\n", encoding="utf-8")
            state_path = root / ".state" / "installer" / "state.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text(
                json.dumps({"profiles": ["requests"], "gpu_mode": "none"}),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                profiles=None,
                gpu_mode="none",
                gpu=None,
                dev=False,
            )
            with mock.patch.dict(os.environ, {"COMPOSE_PROFILES": ""}, clear=False):
                manifest = cli._update_manifest(root, args, dry_run=True)

            self.assertEqual(["requests"], manifest.profiles)
            self.assertEqual(
                {"core": "registry.example/core:stable", "requests": "registry.example/requests:stable"},
                manifest.image_refs,
            )

    def test_update_manifest_rejects_env_digest_that_disagrees_with_docker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docker-compose.yml").write_text(
                "services:\n  api:\n    image: registry.example/api:stable\n",
                encoding="utf-8",
            )
            stale = "sha256:" + "a" * 64
            current = "sha256:" + "b" * 64
            (root / ".env").write_text(
                f'LUMEN_REPO_DIGESTS={{"api":"{stale}"}}\n',
                encoding="utf-8",
            )

            def execute(argv, **_kwargs):
                self.assertEqual(argv[-1], "registry.example/api:stable")
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "Id": "sha256:local-api",
                            "RepoDigests": [f"registry.example/api@{current}"],
                        }
                    ),
                    stderr="",
                )

            with self.assertRaises(InvalidInputError):
                cli._update_manifest(
                    root,
                    SimpleNamespace(profiles=None, gpu_mode="none", gpu=None, dev=False),
                    dry_run=False,
                    runner=cli.CommandRunner(executor=execute),
                )

    def test_update_manifest_rejects_configured_digest_when_docker_has_no_repo_digest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stale = "sha256:" + "a" * 64
            (root / "docker-compose.yml").write_text(
                "services:\n  api:\n    image: registry.example/api:stable\n",
                encoding="utf-8",
            )
            (root / ".env").write_text(
                f'LUMEN_REPO_DIGESTS={{"api":"{stale}"}}\n',
                encoding="utf-8",
            )

            def execute(_argv, **_kwargs):
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps({"Id": "sha256:local-api", "RepoDigests": []}),
                    stderr="",
                )

            with self.assertRaises(InvalidInputError):
                cli._update_manifest(
                    root,
                    SimpleNamespace(profiles=None, gpu_mode="none", gpu=None, dev=False),
                    dry_run=False,
                    runner=cli.CommandRunner(executor=execute),
                )

    def test_update_manifest_rejects_repository_qualified_digest_for_wrong_repository(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            digest = "sha256:" + "a" * 64
            (root / "docker-compose.yml").write_text(
                "services:\n  api:\n    image: registry.example/api:stable\n",
                encoding="utf-8",
            )
            (root / ".env").write_text(
                f'LUMEN_REPO_DIGESTS={{"api":"other.example/api@{digest}"}}\n',
                encoding="utf-8",
            )

            def execute(_argv, **_kwargs):
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "Id": "sha256:local-api",
                            "RepoDigests": [f"registry.example/api@{digest}"],
                        }
                    ),
                    stderr="",
                )

            with self.assertRaises(InvalidInputError):
                cli._update_manifest(
                    root,
                    SimpleNamespace(profiles=None, gpu_mode="none", gpu=None, dev=False),
                    dry_run=False,
                    runner=cli.CommandRunner(executor=execute),
                )

    def test_update_manifest_discards_local_ids_for_inactive_profile_services(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docker-compose.yml").write_text(
                "services:\n"
                "  core:\n"
                "    image: registry.example/core:stable\n"
                "  requests:\n"
                "    image: registry.example/requests:stable\n"
                "    profiles: [requests]\n",
                encoding="utf-8",
            )
            (root / ".env").write_text(
                'LUMEN_LOCAL_IMAGE_IDS={"core":"sha256:core","requests":"sha256:requests"}\n',
                encoding="utf-8",
            )
            args = SimpleNamespace(profiles=None, gpu_mode="none", gpu=None, dev=False)
            with mock.patch.dict(os.environ, {}, clear=False):
                manifest = cli._update_manifest(root, args, dry_run=True)

            self.assertEqual({"core"}, set(manifest.local_image_ids))

    def test_update_manifest_rejects_local_id_for_registry_service_before_inspect(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docker-compose.yml").write_text(
                "services:\n  api:\n    image: registry.example/api:stable\n",
                encoding="utf-8",
            )
            (root / ".env").write_text(
                'LUMEN_LOCAL_IMAGE_IDS={"api":"fabricated"}\n', encoding="utf-8"
            )
            runner = mock.Mock()
            with self.assertRaises(InvalidInputError):
                cli._update_manifest(
                    root,
                    SimpleNamespace(profiles=None, gpu_mode="none", gpu=None, dev=False),
                    dry_run=False,
                    runner=runner,
                )
            runner.run.assert_not_called()

    def test_update_manifest_rejects_unsafe_service_name_before_inspect(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docker-compose.yml").write_text(
                "services:\n  api:\n    image: registry.example/api:stable\n",
                encoding="utf-8",
            )
            (root / ".env").write_text(
                'LUMEN_IMAGE_REFS={"--remove-orphans":"registry.example/api:stable"}\n',
                encoding="utf-8",
            )
            runner = mock.Mock()
            with self.assertRaises(InvalidInputError):
                cli._update_manifest(
                    root,
                    SimpleNamespace(profiles=None, gpu_mode="none", gpu=None, dev=False),
                    dry_run=False,
                    runner=runner,
                )
            runner.run.assert_not_called()

    def test_update_manifest_rejects_configured_build_id_that_disagrees_with_inspect(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docker-compose.yml").write_text(
                "services:\n"
                "  dashboard:\n"
                "    build: .\n"
                "    image: local/dashboard:local\n",
                encoding="utf-8",
            )
            (root / ".env").write_text(
                'LUMEN_LOCAL_IMAGE_IDS={"dashboard":"fabricated"}\n', encoding="utf-8"
            )

            def execute(_argv, **_kwargs):
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps({"Id": "sha256:actual", "RepoDigests": []}),
                    stderr="",
                )

            with self.assertRaises(InvalidInputError):
                cli._update_manifest(
                    root,
                    SimpleNamespace(profiles=None, gpu_mode="none", gpu=None, dev=False),
                    dry_run=False,
                    runner=cli.CommandRunner(executor=execute),
                )

    def test_update_rollback_does_not_pre_read_record_before_helper_validation(self):
        output = io.StringIO()
        fake_result = {"run_id": "run-7"}
        with mock.patch.object(cli, "run_rollback", return_value=fake_result) as helper:
            with mock.patch.object(
                Path, "is_file", return_value=True
            ), mock.patch.object(
                Path,
                "read_text",
                side_effect=AssertionError("CLI read an unvalidated rollback record"),
            ):
                with contextlib.redirect_stdout(output):
                    result = cli.main(["update", "--rollback", "run-7", "--confirm"])

        self.assertEqual(result, int(ExitCode.OK))
        helper.assert_called_once()

    def test_update_manifest_and_compose_options_resolve_auto_from_saved_gpu_mode(self):
        for mode in ("nvidia", "vaapi"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                (root / "docker-compose.yml").write_text(
                    "services:\n  api:\n    image: registry.example/api:stable\n",
                    encoding="utf-8",
                )
                overlay = root / f"docker-compose.{ 'gpu' if mode == 'nvidia' else 'vaapi' }.yml"
                overlay.write_text("services: {}\n", encoding="utf-8")
                (root / ".env").write_text("GPU_MODE=auto\n", encoding="utf-8")
                state_path = root / ".state" / "installer" / "state.json"
                state_path.parent.mkdir(parents=True)
                state_path.write_text(
                    json.dumps({"profiles": [], "gpu_mode": mode}),
                    encoding="utf-8",
                )
                args = SimpleNamespace(
                    profiles=None,
                    gpu_mode=None,
                    gpu=None,
                    dev=False,
                )
                manifest = cli._update_manifest(root, args, dry_run=True)
                options = cli._update_compose_options(manifest, args)

                self.assertEqual(mode, manifest.gpu_mode)
                self.assertEqual(mode, options.gpu_mode)
                self.assertIn(str(overlay), manifest.compose_files)
                self.assertIn(str(overlay), options.global_argv(root, root / ".env"))

    def test_update_rejects_unsafe_rollback_id_before_dry_run_reads_or_writes(self):
        stderr = io.StringIO()
        with mock.patch.object(cli, "run_rollback") as run_rollback:
            with contextlib.redirect_stderr(stderr):
                result = cli.main(["update", "--rollback", "../escape", "--dry-run"])

        self.assertEqual(result, int(ExitCode.INVALID))
        run_rollback.assert_not_called()
        self.assertNotIn("../escape", stderr.getvalue())

    def test_update_manifest_dry_run_never_inspects_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docker-compose.yml").write_text(
                "services:\n  api:\n    image: registry.example/api:latest\n",
                encoding="utf-8",
            )
            runner = mock.Mock()
            manifest = cli._update_manifest(
                root,
                SimpleNamespace(profiles=None, gpu_mode="none", gpu=None, dev=False),
                dry_run=True,
                runner=runner,
            )
            self.assertEqual("none", manifest.gpu_mode)
            runner.run.assert_not_called()

    def test_update_manifest_selects_gpu_overlays_and_disposable_vaapi_plan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docker-compose.yml").write_text(
                "services:\n  api:\n    image: registry.example/api:stable\n",
                encoding="utf-8",
            )
            for mode, overlay in (
                ("none", "docker-compose.yml"),
                ("nvidia", "docker-compose.gpu.yml"),
                ("vaapi", "docker-compose.vaapi.yml"),
            ):
                with self.subTest(mode=mode):
                    manifest = cli._update_manifest(
                        root,
                        SimpleNamespace(profiles=None, gpu_mode=mode, gpu=None, dev=False),
                        dry_run=True,
                    )
                    self.assertEqual(mode, manifest.gpu_mode)
                    self.assertIn(str(root / overlay), manifest.compose_files)
                    if mode == "vaapi":
                        self.assertEqual(
                            {"RENDER_GID": "65534", "VIDEO_GID": "65533"},
                            manifest.gpu_environment,
                        )
                    else:
                        self.assertEqual({}, manifest.gpu_environment)

    def test_update_callbacks_order_and_rollback_commands_are_safe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            compose_file = root / "docker-compose.yml"
            compose_file.write_text(
                "services:\n"
                "  api:\n"
                "    image: registry.example/api:stable\n"
                "  dashboard:\n"
                "    build:\n"
                "      context: .\n"
                "    image: local/dashboard:local\n",
                encoding="utf-8",
            )
            env_path = root / ".env"
            env_path.write_text("ACTIONS_TOKEN=not-for-output\n", encoding="utf-8")
            manifest = cli.UpdateManifest.from_inputs(
                env_path,
                {},
                {"api": "registry.example/api:stable", "dashboard": "local/dashboard:local"},
                {"api": "sha256:" + "a" * 64},
                {"dashboard": "sha256:dashboard"},
                [],
                "none",
                [compose_file],
            )
            calls = []

            def execute(argv, **_kwargs):
                calls.append(tuple(argv))
                if tuple(argv[-3:]) == ("config", "--format", "json"):
                    stdout = json.dumps(
                        {
                            "services": {
                                "api": {"image": "registry.example/api:stable"},
                                "dashboard": {
                                    "image": "local/dashboard:local",
                                    "build": {"context": "."},
                                },
                            }
                        }
                    )
                else:
                    stdout = ""
                return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

            runner = cli.CommandRunner(executor=execute)
            args = SimpleNamespace(dev=False)
            tag, pull, recreate = cli._update_callbacks(root, manifest, args, runner)
            tags = tag("run-1")
            pull("run-1")
            with mock.patch.object(cli, "wait_for_health") as health:
                recreate("run-1")
            self.assertEqual("lumen-rollback/dashboard:run-1", tags["dashboard"])
            commands = [" ".join(command) for command in calls]
            self.assertIn("docker image tag local/dashboard:local lumen-rollback/dashboard:run-1", commands)
            self.assertTrue(any("pull api" in command for command in commands))
            self.assertTrue(any("build dashboard" in command for command in commands))
            self.assertTrue(any("up -d --force-recreate" in command for command in commands))
            self.assertTrue(all("--remove-orphans" not in command for command in commands))
            health.assert_called_once_with()

    def test_rollback_callbacks_stop_named_services_and_use_override_without_orphans(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env_path = root / ".env"
            env_path.write_text("ACTIONS_TOKEN=private\n", encoding="utf-8")
            compose_file = root / "docker-compose.yml"
            compose_file.write_text("services:\n  api:\n    image: example/api:stable\n", encoding="utf-8")
            manifest = cli.UpdateManifest.from_inputs(
                env_path,
                {},
                {"api": "example/api:stable"},
                {"api": "sha256:" + "a" * 64},
                {},
                ["requests"],
                "vaapi",
                [compose_file, root / "docker-compose.vaapi.yml"],
                {"RENDER_GID": "100", "VIDEO_GID": "101"},
            )
            calls = []

            def execute(argv, **_kwargs):
                calls.append(tuple(argv))
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            runner = cli.CommandRunner(executor=execute)
            stop, start = cli._rollback_callbacks(
                root, manifest, SimpleNamespace(dev=False), runner
            )
            stop("run-2")
            with mock.patch.object(cli, "wait_for_health") as health:
                start("run-2")
            self.assertIn("stop", calls[0])
            self.assertIn("api", calls[0])
            self.assertTrue(any("docker-compose.vaapi.yml" in item for item in calls[0]))
            self.assertTrue(any("docker-compose.vaapi.yml" in item for item in calls[1]))
            self.assertTrue(any("rollback/run-2.yml" in item for item in calls[1]))
            self.assertIn("up", calls[1])
            self.assertIn("--force-recreate", calls[1])
            self.assertTrue(all("--remove-orphans" not in call for call in calls))
            health.assert_called_once_with()

    def test_setup_confirmation_is_explicit_and_not_a_gpu_confirmation_abbreviation(self):
        parser = cli.build_parser()
        args = parser.parse_args(["setup", "--confirm"])

        self.assertTrue(getattr(args, "confirm", False))
        self.assertFalse(getattr(args, "gpu_confirm", False))

    def test_configure_gpu_confirmation_remains_distinct_with_legacy_alias(self):
        parser = cli.build_parser()

        for flag in ("--confirm-gpu", "--gpu-confirm"):
            with self.subTest(flag=flag):
                args = parser.parse_args(["configure", flag])
                self.assertTrue(args.gpu_confirm)
                self.assertFalse(getattr(args, "confirm", False))

    def test_configure_dispatch_prints_redacted_report_and_returns_result_code(self):
        fake_result = type(
            "ConfigureResult",
            (),
            {"report": {"status": "drift", "api_key": "must-not-escape"}, "exit_code": 3},
        )()
        output = io.StringIO()
        with mock.patch.object(cli, "run_configure", return_value=fake_result) as run_configure:
            with contextlib.redirect_stdout(output):
                result = cli.main(["configure", "--non-interactive"])

        self.assertEqual(result, 3)
        self.assertIn("redacted", output.getvalue())
        self.assertNotIn("must-not-escape", output.getvalue())
        run_configure.assert_called_once()

    def test_setup_runs_core_configure_after_foundation(self):
        foundation = type("FoundationResult", (), {"report": {"status": "ok"}})()
        configured = type(
            "ConfigureResult",
            (),
            {"report": {"status": "partial"}, "exit_code": 4},
        )()
        output = io.StringIO()
        with mock.patch.object(cli, "run_foundation", return_value=foundation), \
             mock.patch.object(cli, "run_configure", return_value=configured) as run_configure:
            with contextlib.redirect_stdout(output):
                result = cli.main(["setup"])

        self.assertEqual(result, 4)
        run_configure.assert_called_once()
        self.assertIn("foundation", output.getvalue())
        self.assertIn("configure", output.getvalue())

    def test_setup_forwards_public_confirmation_to_foundation(self):
        foundation = type("FoundationResult", (), {"report": {"status": "ok"}})()
        configured = type(
            "ConfigureResult",
            (),
            {"report": {"status": "ok"}, "exit_code": 0},
        )()
        with mock.patch.object(cli, "run_foundation", return_value=foundation) as run_foundation, \
             mock.patch.object(cli, "run_configure", return_value=configured):
            result = cli.main(["setup", "--confirm"])

        self.assertEqual(result, 0)
        self.assertTrue(run_foundation.call_args.kwargs.get("confirm", False))
        self.assertFalse(run_foundation.call_args.kwargs["gpu_confirm"])

    def test_setup_passes_foundation_effective_options_to_real_configure_boundary(self):
        import lumen_installer.configure as configure_module

        effective_options = ComposeOptions(
            profiles=("requests",),
            gpu="vaapi",
            dev=True,
        )
        foundation = type(
            "FoundationResult",
            (),
            {"report": {"status": "ok"}, "options": effective_options},
        )()
        configured_options = []

        def configure_boundary(*, options, interactive, dry_run):
            configured_options.append(options)
            with tempfile.TemporaryDirectory() as temporary:
                return configure_module.run_configure(
                    Path(temporary),
                    options=options,
                    reconcile=lambda service: {"service": service, "status": "ok"},
                    env_commit=lambda: None,
                    restart=lambda: None,
                    direct_health=lambda: True,
                    proxy_health=lambda: True,
                    interactive=interactive,
                    dry_run=dry_run,
                )

        with mock.patch.object(cli, "run_foundation", return_value=foundation), \
             mock.patch.object(cli, "run_configure", side_effect=configure_boundary):
            result = cli.main(["setup"])

        self.assertEqual(result, 0)
        self.assertEqual(configured_options, [effective_options])

    def test_exit_codes_are_stable(self):
        self.assertEqual(int(ExitCode.OK), 0)
        self.assertEqual(int(ExitCode.INVALID), 2)
        self.assertEqual(int(ExitCode.DRIFT), 3)
        self.assertEqual(int(ExitCode.PARTIAL), 4)

    def test_main_maps_typed_installer_errors_to_their_exit_codes(self):
        cases = (
            (InvalidInputError("bad input"), ExitCode.INVALID),
            (DriftError("drift needs approval"), ExitCode.DRIFT),
            (PartialError("health incomplete"), ExitCode.PARTIAL),
            (InstallerError("done", ExitCode.OK), ExitCode.OK),
        )

        for error, expected in cases:
            with self.subTest(expected=expected), mock.patch.object(
                cli, "dispatch", side_effect=error
            ):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cli.main(["doctor"]), int(expected))

    def test_main_does_not_swallow_untyped_errors(self):
        with mock.patch.object(cli, "dispatch", side_effect=RuntimeError("bug")):
            with self.assertRaisesRegex(RuntimeError, "bug"):
                cli.main(["doctor"])

    def test_unknown_arguments_return_invalid_exit_code(self):
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            result = cli.main(["not-a-command"])
        self.assertEqual(result, int(ExitCode.INVALID))
        self.assertIn("argument error", errors.getvalue())

        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["doctor", "--unknown"]), int(ExitCode.INVALID))

    def test_unknown_argument_values_are_not_echoed(self):
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            result = cli.main(["doctor", "--token", "SUPERSECRET"])

        self.assertEqual(result, int(ExitCode.INVALID))
        self.assertIn("unrecognized arguments", errors.getvalue())
        self.assertNotIn("SUPERSECRET", errors.getvalue())

    def test_doctor_host_portion_prints_redacted_preflight_report_and_maps_failure(self):
        fake_report = {
            "status": "ok",
            "docker_version": (26, 1, 4),
            "compose_version": (2, 24, 4),
            "secret": "must-not-appear",
        }
        with mock.patch("lumen_installer.cli.run_host_doctor", return_value=fake_report):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = cli.main(["doctor"])

        self.assertEqual(result, int(ExitCode.INVALID))
        self.assertNotIn("must-not-appear", output.getvalue())
        self.assertIn("compose_version", output.getvalue())

    def test_doctor_preflight_failure_uses_invalid_exit_code(self):
        with mock.patch(
            "lumen_installer.cli.run_host_doctor",
            side_effect=InvalidInputError("Compose 2.24.3 is below required floor"),
        ):
            with contextlib.redirect_stderr(io.StringIO()):
                result = cli.main(["doctor"])

        self.assertEqual(result, int(ExitCode.INVALID))

    def test_doctor_passes_explicit_host_overrides_to_host_preflight(self):
        with mock.patch(
            "lumen_installer.cli.run_host_doctor",
            return_value={"status": "ok"},
        ) as run_host_doctor:
            with contextlib.redirect_stdout(io.StringIO()):
                result = cli.main(
                    [
                        "doctor",
                        "--uid",
                        "1001",
                        "--gid",
                        "1002",
                        "--timezone",
                        "UTC",
                        "--image",
                        "example/image:latest",
                    ]
                )

        self.assertEqual(result, int(ExitCode.INVALID))
        run_host_doctor.assert_called_once_with(
            uid=1001,
            gid=1002,
            timezone="UTC",
            image="example/image:latest",
        )

    def test_launcher_works_from_another_current_directory(self):
        install_sh = WORKTREE_ROOT / "install.sh"
        with tempfile.TemporaryDirectory() as other_cwd:
            result = subprocess.run(
                [str(install_sh), "--help"],
                cwd=other_cwd,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("setup", result.stdout)
        self.assertIn("lumen_installer", result.stdout)

    def test_launcher_rejects_python_before_starting_cli(self):
        install_sh = WORKTREE_ROOT / "install.sh"
        with tempfile.TemporaryDirectory() as fake_bin, tempfile.TemporaryDirectory() as other_cwd:
            fake_python = Path(fake_bin) / "python3"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"$1\" == \"-c\" ]]; then printf '3 9\\n'; exit 0; fi\n"
                "printf 'unexpected python invocation\\n' >&2\n"
                "exit 99\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            result = subprocess.run(
                [str(install_sh), "--help"],
                cwd=other_cwd,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, int(ExitCode.INVALID), result.stderr)
        self.assertIn("Python 3.10", result.stderr)
        self.assertNotIn("unexpected python invocation", result.stderr)

    def test_launcher_requires_bash(self):
        install_sh = WORKTREE_ROOT / "install.sh"
        shell = shutil.which("sh")
        if shell is None or Path(shell).resolve().name == "bash":
            self.skipTest("the available sh is Bash on this host")
        result = subprocess.run(
            [shell, str(install_sh), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, int(ExitCode.INVALID), result.stderr)
        self.assertIn("requires Bash", result.stderr)


if __name__ == "__main__":
    unittest.main()
