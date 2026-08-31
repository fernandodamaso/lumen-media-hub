import contextlib
import io
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

        self.assertEqual(result, int(ExitCode.OK))
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

        self.assertEqual(result, int(ExitCode.OK))
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
