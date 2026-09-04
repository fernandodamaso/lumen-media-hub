import contextlib
import io
import json
import os
import stat
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
from lumen_installer.errors import ExitCode, InvalidInputError
from lumen_installer.trakt import (
    TERMINAL_DEVICE_STATUSES,
    TraktAuthorizationError,
    TraktDeviceAuthorizer,
    TraktTokenState,
    TraktTokenStore,
    resolve_token_path,
    run_connect_trakt,
)


class TraktAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name) / "repo"
        self.root.mkdir()
        self.token_path = self.root / ".state" / "trakt" / "trakt-token.json"
        self.token_path.parent.mkdir(parents=True)
        TraktTokenStore(self.token_path).replace(
            TraktTokenState("access-old", "refresh-old", 2_000, 1_000)
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_pending_then_slowdown_then_success_replaces_state_without_printing_secrets(self):
        responses = [
            (200, {
                "device_code": "device-secret",
                "user_code": "ABCD-1234",
                "verification_url": "https://trakt.tv/activate",
                "expires_in": 100,
                "interval": 2,
            }),
            (400, {}),
            (429, {}),
            (200, {
                "access_token": "access-new-secret",
                "refresh_token": "refresh-new-secret",
                "expires_in": 3_600,
            }),
        ]
        calls = []
        sleeps = []
        output = []

        def transport(method, url, headers, body):
            calls.append((method, url, headers, body))
            return responses.pop(0)

        state = TraktDeviceAuthorizer(
            "client-id",
            client_secret="client-secret",
            token_path=self.token_path,
            transport=transport,
            clock=lambda: 100,
            sleep=sleeps.append,
        ).authorize(output=output.append)

        self.assertEqual(state.access_token, "access-new-secret")
        self.assertEqual(TraktTokenStore(self.token_path).load(), state)
        self.assertEqual(sleeps, [2, 2, 7])
        self.assertEqual(calls[0][1], "https://auth.trakt.tv/oauth/device/code")
        self.assertEqual(calls[1][1], "https://auth.trakt.tv/oauth/device/token")
        self.assertEqual(calls[-1][2]["User-Agent"], "lumen-media-hub-installer/1.0")
        self.assertIn("ABCD-1234", " ".join(output))
        for secret in ("client-secret", "device-secret", "access-new-secret", "refresh-new-secret"):
            self.assertNotIn(secret, " ".join(output))

    def test_terminal_device_statuses_preserve_existing_state(self):
        original = TraktTokenStore(self.token_path).load()
        for status in sorted(TERMINAL_DEVICE_STATUSES):
            with self.subTest(status=status):
                responses = [
                    (200, {
                        "device_code": "device-secret",
                        "user_code": "ABCD-1234",
                        "verification_url": "https://trakt.tv/activate",
                        "expires_in": 100,
                        "interval": 1,
                    }),
                    (status, {}),
                ]
                with self.assertRaises(TraktAuthorizationError) as raised:
                    TraktDeviceAuthorizer(
                        "client-id",
                        client_secret="client-secret",
                        token_path=self.token_path,
                        transport=lambda *args: responses.pop(0),
                        clock=lambda: 100,
                        sleep=lambda _: None,
                    ).authorize()
                self.assertEqual(raised.exception.status, status)
                self.assertEqual(TraktTokenStore(self.token_path).load(), original)

    def test_pending_until_device_authorization_expires_preserves_existing_state(self):
        original = TraktTokenStore(self.token_path).load()
        now = [100]

        def sleep(seconds):
            now[0] += seconds

        responses = [
            (200, {
                "device_code": "device-secret",
                "user_code": "ABCD-1234",
                "verification_url": "https://trakt.tv/activate",
                "expires_in": 3,
                "interval": 2,
            }),
            (400, {}),
            (400, {}),
        ]
        with self.assertRaises(TraktAuthorizationError) as raised:
            TraktDeviceAuthorizer(
                "client-id",
                client_secret="client-secret",
                token_path=self.token_path,
                transport=lambda *args: responses.pop(0),
                clock=lambda: now[0],
                sleep=sleep,
            ).authorize()
        self.assertEqual(raised.exception.code, "reconnect_required")
        self.assertEqual(TraktTokenStore(self.token_path).load(), original)

    def test_non_success_start_response_is_safe_and_preserves_existing_state(self):
        original = TraktTokenStore(self.token_path).load()
        secret = "response-secret"
        with self.assertRaises(InvalidInputError) as raised:
            TraktDeviceAuthorizer(
                "client-id",
                client_secret="client-secret",
                token_path=self.token_path,
                transport=lambda *args: (503, {"error": secret}),
            ).authorize()
        self.assertNotIn(secret, str(raised.exception))
        self.assertEqual(TraktTokenStore(self.token_path).load(), original)

    def test_atomic_replace_failure_preserves_previous_state(self):
        store = TraktTokenStore(self.token_path)
        original = TraktTokenStore(self.token_path).load()
        with mock.patch("lumen_installer.trakt.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.replace(TraktTokenState("access-new", "refresh-new", 3_000, 2_000))
        self.assertEqual(store.load(), original)

    def test_successful_state_is_schema_one_and_mode_0600(self):
        new_path = self.root / "new-state.json"
        TraktTokenStore(new_path).replace(
            TraktTokenState("access", "refresh", 2_000, 1_000)
        )
        self.assertEqual(
            json.loads(new_path.read_text(encoding="utf-8"))["schema_version"],
            1,
        )
        self.assertEqual(stat.S_IMODE(new_path.stat().st_mode), 0o600)

    def test_configured_container_path_resolves_under_configured_host_state_root(self):
        expected = self.root / "custom-state" / "nested" / "token.json"
        actual = resolve_token_path(
            self.root,
            {
                "TRAKT_STATE_PATH": "./custom-state",
                "TRAKT_TOKEN_PATH": "/state/nested/token.json",
            },
        )
        self.assertEqual(actual, expected)

    def test_reconnect_always_starts_device_flow_when_state_already_exists(self):
        responses = [
            (200, {
                "device_code": "device-secret",
                "user_code": "ABCD-1234",
                "verification_url": "https://trakt.tv/activate",
                "expires_in": 100,
                "interval": 1,
            }),
            (200, {
                "access_token": "access-reconnected",
                "refresh_token": "refresh-reconnected",
                "expires_in": 3_600,
            }),
        ]
        calls = []

        def transport(method, url, headers, body):
            calls.append(url)
            return responses.pop(0)

        result = run_connect_trakt(
            self.root,
            env_file=self.root / ".env",
            environment={
                "TRAKT_CLIENT_ID": "client-id",
                "TRAKT_CLIENT_SECRET": "client-secret",
            },
            token_path=self.token_path,
            transport=transport,
            clock=lambda: 100,
            sleep=lambda _: None,
            warmup=lambda: None,
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(calls, [
            "https://auth.trakt.tv/oauth/device/code",
            "https://auth.trakt.tv/oauth/device/token",
        ])
        self.assertEqual(TraktTokenStore(self.token_path).load().refresh_token, "refresh-reconnected")

    def test_warmup_failure_is_reported_without_failing_authorization(self):
        responses = [
            (200, {
                "device_code": "device-secret",
                "user_code": "ABCD-1234",
                "verification_url": "https://trakt.tv/activate",
                "expires_in": 100,
                "interval": 1,
            }),
            (200, {
                "access_token": "access-new-secret",
                "refresh_token": "refresh-new-secret",
                "expires_in": 3_600,
            }),
        ]
        result = run_connect_trakt(
            self.root,
            environment={
                "TRAKT_CLIENT_ID": "client-id",
                "TRAKT_CLIENT_SECRET": "client-secret",
            },
            token_path=self.token_path,
            transport=lambda *args: responses.pop(0),
            clock=lambda: 100,
            sleep=lambda _: None,
            warmup=lambda: (_ for _ in ()).throw(OSError("private warmup failure")),
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.warmup.status, "failed")
        self.assertEqual(TraktTokenStore(self.token_path).load().access_token, "access-new-secret")
        self.assertNotIn("private warmup failure", repr(result.report))

    def test_dry_run_is_read_only_and_does_not_start_device_flow_or_create_state_directory(self):
        env_path = self.root / ".env"
        env_text = (
            "TRAKT_CLIENT_ID=client-id\n"
            "TRAKT_CLIENT_SECRET=client-secret\n"
            "TRAKT_STATE_PATH=./dry-state\n"
            "TRAKT_TOKEN_PATH=/state/trakt-token.json\n"
        )
        env_path.write_text(env_text, encoding="utf-8")
        dry_path = self.root / "dry-state"
        result = run_connect_trakt(
            self.root,
            env_file=env_path,
            transport=lambda *args: self.fail("dry-run must not call Trakt"),
            dry_run=True,
        )
        self.assertEqual(result.status, "dry-run")
        self.assertTrue(result.dry_run)
        self.assertFalse(dry_path.exists())
        self.assertEqual(env_path.read_text(encoding="utf-8"), env_text)

    def test_report_and_output_do_not_contain_client_or_token_values(self):
        responses = [
            (200, {
                "device_code": "device-secret",
                "user_code": "ABCD-1234",
                "verification_url": "https://trakt.tv/activate",
                "expires_in": 100,
                "interval": 1,
            }),
            (200, {
                "access_token": "access-new-secret",
                "refresh_token": "refresh-new-secret",
                "expires_in": 3_600,
            }),
        ]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = cli.main([
                "connect-trakt",
                "--dry-run",
            ])
        self.assertEqual(result, int(ExitCode.INVALID))
        self.assertNotIn("client-secret", output.getvalue())
        self.assertNotIn("access-new-secret", repr(result))


class TraktCliWiringTests(unittest.TestCase):
    def test_connect_trakt_dispatches_to_linux_adapter_and_prints_safe_report(self):
        fake_result = type(
            "TraktResult",
            (),
            {"report": {"status": "dry-run", "token_path": "/state/trakt-token.json"}, "exit_code": 0},
        )()
        with mock.patch.object(cli, "run_connect_trakt", return_value=fake_result) as connect:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = cli.main(["connect-trakt", "--dry-run"])
        self.assertEqual(result, 0)
        connect.assert_called_once()
        self.assertIn('"status": "dry-run"', output.getvalue())


if __name__ == "__main__":
    unittest.main()
