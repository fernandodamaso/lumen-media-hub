import subprocess
import sys
import time
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
        self.assertEqual(lumen_installer.DEFAULT_TIMEOUT, 30.0)
        self.assertTrue(callable(lumen_installer.normalize_stream))
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
        self.assertIsInstance(kwargs["timeout"], (int, float))
        self.assertGreater(kwargs["timeout"], 0)
        self.assertEqual(result.stdout, "hello")

    def test_object_executor_with_run_method_is_supported(self):
        delegate = mock.Mock()
        delegate.run.return_value = subprocess.CompletedProcess(
            ["tool"], 0, stdout="ok", stderr=""
        )

        result = CommandRunner(executor=delegate).run(["tool"])

        self.assertEqual(result.stdout, "ok")
        delegate.run.assert_called_once_with(["tool"], input_text=None, timeout=30.0)

    def test_injected_executor_receives_the_configured_timeout(self):
        observed = []

        def execute(_argv, *, timeout=None):
            observed.append(timeout)
            return subprocess.CompletedProcess(["tool"], 0, stdout="ok", stderr="")

        result = CommandRunner(executor=execute, timeout=0.25).run(["tool"])

        self.assertEqual(result.stdout, "ok")
        self.assertEqual(observed, [0.25])

    def test_delayed_injected_executor_has_a_typed_redacted_timeout(self):
        secret = "delayed-secret"

        def delayed(_argv, *, timeout=None):
            del timeout
            time.sleep(0.05)
            return subprocess.CompletedProcess(["tool", secret], 0, stdout=secret, stderr=secret)

        with self.assertRaises(CommandExecutionError) as raised:
            CommandRunner(executor=delayed, timeout=0.005).run(
                ["tool", secret], redact=(secret,)
            )

        self.assertTrue(raised.exception.report["timed_out"])
        self.assertEqual(raised.exception.report["timeout"], 0.005)
        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn(secret, repr(raised.exception.report))

    def test_default_timeout_is_bounded_and_timeout_error_is_typed_and_redacted(self):
        secret = "timeout-secret"
        timed_out = subprocess.TimeoutExpired(
            ["tool", secret], 15, output=f"out {secret}", stderr=f"err {secret}"
        )
        with mock.patch("lumen_installer.commands.subprocess.run", side_effect=timed_out):
            with self.assertRaises(CommandExecutionError) as raised:
                CommandRunner().run(["tool", secret], redact=(secret,))

        self.assertTrue(raised.exception.report["timed_out"])
        self.assertEqual(raised.exception.report["timeout"], 30.0)
        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn(secret, repr(raised.exception))

    def test_byte_streams_are_normalized_to_text_and_invalid_utf8_is_replaced(self):
        completed = subprocess.CompletedProcess(
            ["tool"], 0, stdout=b"out \xff", stderr=b"err \xfe"
        )
        with mock.patch("lumen_installer.commands.subprocess.run", return_value=completed):
            result = CommandRunner().run(["tool"])

        self.assertEqual(result.stdout, "out \ufffd")
        self.assertEqual(result.stderr, "err \ufffd")
        self.assertIsInstance(result.stdout, str)

    def test_empty_byte_redaction_value_is_ignored(self):
        completed = subprocess.CompletedProcess(["tool"], 0, stdout="abc", stderr="")
        with mock.patch("lumen_installer.commands.subprocess.run", return_value=completed):
            result = CommandRunner().run(["tool"], redact=(b"",))

        self.assertEqual(result.report["stdout"], "abc")

    def test_nonempty_byte_redaction_value_is_decoded_before_redaction(self):
        secret = "byte-secret"
        completed = subprocess.CompletedProcess(
            ["tool", secret], 0, stdout=f"seen {secret}", stderr=""
        )
        with mock.patch("lumen_installer.commands.subprocess.run", return_value=completed):
            result = CommandRunner().run(["tool", secret], redact=(secret.encode(),))

        self.assertNotIn(secret, repr(result.report))

    def test_unexpected_stream_types_are_typed_failures(self):
        completed = subprocess.CompletedProcess(["tool"], 0, stdout=object(), stderr="")
        with mock.patch("lumen_installer.commands.subprocess.run", return_value=completed):
            with self.assertRaises(CommandExecutionError):
                CommandRunner().run(["tool"])

    def test_all_falsey_non_text_stream_types_are_typed_failures(self):
        for field in ("stdout", "stderr"):
            for value in (0, False, [], {}):
                with self.subTest(field=field, value=type(value).__name__):
                    streams = {"stdout": "", "stderr": ""}
                    streams[field] = value
                    completed = subprocess.CompletedProcess(["tool"], 0, **streams)
                    with mock.patch(
                        "lumen_installer.commands.subprocess.run", return_value=completed
                    ):
                        with self.assertRaises(CommandExecutionError):
                            CommandRunner().run(["tool"])

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

    def test_injected_startup_exceptions_are_typed_and_redacted(self):
        secret = "executor-secret"
        exceptions = (
            ValueError(f"bad value {secret}"),
            TypeError(f"bad type {secret}"),
            UnicodeDecodeError(
                "utf-8",
                (secret + "\xff").encode(),
                len(secret),
                len(secret) + 1,
                "invalid continuation byte",
            ),
            RuntimeError(f"runtime failure {secret}"),
        )
        for exception in exceptions:
            with self.subTest(exception=type(exception).__name__):
                def fail(_argv, _exception=exception):
                    raise _exception

                with self.assertRaises(CommandExecutionError) as raised:
                    CommandRunner(executor=fail).run(["tool", secret], redact=(secret,))
                self.assertNotIn(secret, str(raised.exception))
                self.assertNotIn(secret, repr(raised.exception))

    def test_keyboard_interrupt_and_system_exit_are_not_swallowed(self):
        for exception in (KeyboardInterrupt(), SystemExit(9)):
            with self.subTest(exception=type(exception).__name__):
                def stop(_argv, _exception=exception):
                    raise _exception

                with self.assertRaises(type(exception)):
                    CommandRunner(executor=stop).run(["tool"])


if __name__ == "__main__":
    unittest.main()
