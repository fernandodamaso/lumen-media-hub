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
