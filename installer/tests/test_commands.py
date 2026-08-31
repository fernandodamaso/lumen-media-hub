import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_ROOT = WORKTREE_ROOT / "installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.commands import CommandExecutionError, CommandRunner


class PackageExportsTests(unittest.TestCase):
    def test_task_four_interfaces_are_available_from_package(self):
        import lumen_installer

        self.assertIs(lumen_installer.CommandRunner, CommandRunner)
        self.assertTrue(callable(lumen_installer.dependency_plan))
        self.assertTrue(callable(lumen_installer.inspect_manifest_architectures))


class CommandRunnerTests(unittest.TestCase):
    def test_run_uses_argument_vector_and_never_a_shell(self):
        completed = subprocess.CompletedProcess(
            ["printf", "hello"], 0, stdout="hello", stderr=""
        )
        with mock.patch("lumen_installer.commands.subprocess.run", return_value=completed) as run:
            result = CommandRunner().run(["printf", "hello"])

        run.assert_called_once()
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["printf", "hello"])
        self.assertFalse(kwargs["shell"])
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["text"])
        self.assertEqual(result.stdout, "hello")

    def test_rejects_string_commands_before_invoking_subprocess(self):
        with mock.patch("lumen_installer.commands.subprocess.run") as run:
            with self.assertRaises(TypeError):
                CommandRunner().run("printf secret")
        run.assert_not_called()

    def test_success_report_redacts_every_configured_secret(self):
        secret = "s3cr3t-token"
        completed = subprocess.CompletedProcess(
            ["tool", secret], 0,
            stdout=f"used {secret}", stderr=f"warning {secret}",
        )
        with mock.patch("lumen_installer.commands.subprocess.run", return_value=completed):
            result = CommandRunner().run(["tool", secret], redact=(secret,))

        self.assertNotIn(secret, repr(result.report))
        self.assertEqual(result.report["argv"], ["tool", "<redacted>"])
        self.assertEqual(result.report["stdout"], "used <redacted>")
        self.assertEqual(result.report["stderr"], "warning <redacted>")

    def test_failed_command_raises_typed_redacted_error(self):
        secret = "password-value"
        completed = subprocess.CompletedProcess(
            ["tool", secret], 17,
            stdout=f"failed with {secret}", stderr=f"fatal {secret}",
        )
        with mock.patch("lumen_installer.commands.subprocess.run", return_value=completed):
            with self.assertRaises(CommandExecutionError) as raised:
                CommandRunner().run(["tool", secret], redact=(secret,))

        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn(secret, repr(raised.exception.report))
        self.assertEqual(raised.exception.report["returncode"], 17)

    def test_os_error_is_typed_and_redacted(self):
        secret = "hidden"
        with mock.patch(
            "lumen_installer.commands.subprocess.run",
            side_effect=FileNotFoundError(f"{secret}: not found"),
        ):
            with self.assertRaises(CommandExecutionError) as raised:
                CommandRunner().run(["missing", secret], redact=(secret,))

        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn(secret, repr(raised.exception.report))


if __name__ == "__main__":
    unittest.main()
