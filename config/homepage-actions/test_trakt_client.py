import json
import os
import inspect
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

from clients.trakt import (
    TraktDeviceAuthorizer,
    TraktAuthError,
    TraktClient,
    TraktTokenState,
    TraktTokenStore,
)


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload


class TraktTokenStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmpdir.name, "trakt-token.json")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_load_validates_and_replaces_token_state_atomically(self):
        store = TraktTokenStore(self.path)
        state = TraktTokenState("access-a", "refresh-a", 2_000, 1_000)
        store.replace(state)

        self.assertEqual(store.load(), state)
        with open(self.path, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["refresh_token"], "refresh-a")

        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"schema_version": 1, "access_token": "only-access"}, handle)
        with self.assertRaises(ValueError):
            store.load()

    def test_load_sanitizes_unexpected_filesystem_errors(self):
        store = TraktTokenStore(self.path)
        leaked = r"C:\private\trakt-token.json: access denied"
        with mock.patch("clients.trakt.open", side_effect=PermissionError(leaked)):
            with self.assertRaisesRegex(RuntimeError, "^Trakt temporarily unavailable$") as context:
                store.load()
        self.assertNotIn(leaked, str(context.exception))

    def test_failed_atomic_replace_preserves_previous_state(self):
        store = TraktTokenStore(self.path)
        original = TraktTokenState("access-a", "refresh-a", 2_000, 1_000)
        store.replace(original)
        with mock.patch("clients.trakt.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.replace(TraktTokenState("access-b", "refresh-b", 3_000, 2_000))
        self.assertEqual(store.load(), original)


class TraktClientTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmpdir.name, "trakt-token.json")
        TraktTokenStore(self.path).replace(
            TraktTokenState("access-old", "refresh-old", 1_000, 900)
        )
        self.now = 950
        self.calls = []

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_static_access_token_compatibility_path_is_removed(self):
        import config as settings

        self.assertFalse(hasattr(settings, "TRAKT_" + "ACCESS_TOKEN"))
        self.assertNotIn("fallback_access_token", inspect.signature(TraktClient).parameters)

    def test_final_repository_contract_has_no_static_token_configuration(self):
        static_token_name = "TRAKT_" + "ACCESS_TOKEN"
        tracked_paths = (
            ".env.example",
            "docker-compose.yml",
            "README.md",
            "dashboard-app/docs/architecture.md",
            "dashboard-app/docs/trakt-renewable-oauth-design.md",
            "config/recommendations/README.md",
            "config/recommendations/HERMES_DISCOVER_PROMPT.md",
        )
        for relative_path in tracked_paths:
            content = (Path(REPO_ROOT) / relative_path).read_text(encoding="utf-8")
            self.assertNotIn(static_token_name, content, relative_path)

        env_example = (Path(REPO_ROOT) / ".env.example").read_text(encoding="utf-8")
        compose = (Path(REPO_ROOT) / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("TRAKT_WATCHED_PATH=/state/trakt-watched.json", env_example)
        self.assertIn("TRAKT_WATCHED_PATH=${TRAKT_WATCHED_PATH:-/state/trakt-watched.json}", compose)

    def client(self, transport):
        return TraktClient(
            client_id="client-id",
            client_secret="client-secret",
            token_path=self.path,
            transport=transport,
            clock=lambda: self.now,
        )

    def test_proactively_refreshes_when_less_than_one_minute_remains(self):
        def transport(method, url, headers, body):
            self.calls.append((method, url, headers, body))
            if url.endswith("/oauth/token"):
                return FakeResponse(
                    200,
                    {"access_token": "access-new", "refresh_token": "refresh-new", "expires_in": 3600},
                )
            return FakeResponse(200, {"ok": True})

        self.assertEqual(self.client(transport).get("/recommendations/movies"), {"ok": True})
        self.assertEqual(len([call for call in self.calls if call[1].endswith("/oauth/token")]), 1)
        refresh_call = next(call for call in self.calls if call[1].endswith("/oauth/token"))
        self.assertEqual(refresh_call[1], "https://auth.trakt.tv/oauth/token")
        self.assertEqual(refresh_call[2]["Content-Type"], "application/json")
        self.assertEqual(json.loads(refresh_call[3].decode("utf-8"))["grant_type"], "refresh_token")
        self.assertEqual(TraktTokenStore(self.path).load().access_token, "access-new")

    def test_401_refreshes_and_retries_once(self):
        responses = [FakeResponse(401, {}), FakeResponse(200, {"items": [1]})]

        def transport(method, url, headers, body):
            self.calls.append((method, url, headers, body))
            if url.endswith("/oauth/token"):
                return FakeResponse(200, {"access_token": "access-new", "refresh_token": "refresh-new", "expires_in": 3600})
            return responses.pop(0)

        self.now = 100
        self.assertEqual(self.client(transport).get("/recommendations/movies"), {"items": [1]})
        api_calls = [call for call in self.calls if "/recommendations/" in call[1]]
        self.assertEqual(len(api_calls), 2)
        self.assertEqual(api_calls[-1][2]["Authorization"], "Bearer access-new")

    def test_second_401_requires_reconnect_without_leaking_details(self):
        def transport(method, url, headers, body):
            self.calls.append((method, url, headers, body))
            if url.endswith("/oauth/token"):
                return FakeResponse(200, {"access_token": "access-new", "refresh_token": "refresh-new", "expires_in": 3600})
            return FakeResponse(401, {})

        with self.assertRaises(TraktAuthError) as context:
            self.client(transport).get("/recommendations/movies")
        self.assertEqual(context.exception.code, "reconnect_required")
        self.assertEqual(str(context.exception), "Trakt reconnect required")
        self.assertEqual(len([call for call in self.calls if "/recommendations/" in call[1]]), 2)

    def test_refresh_rejection_is_safe_and_contains_no_secret(self):
        def transport(method, url, headers, body):
            if url.endswith("/oauth/token"):
                return FakeResponse(400, {"error": "invalid_grant", "access_token": "do-not-leak"})
            self.fail("the expired request must refresh first")

        with self.assertRaises(TraktAuthError) as context:
            self.client(transport).get("/recommendations/movies")
        self.assertEqual(context.exception.code, "reconnect_required")
        self.assertNotIn("refresh-old", str(context.exception))
        self.assertNotIn("do-not-leak", str(context.exception))

    def test_invalid_persisted_state_requires_reconnect_without_details(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write('{"schema_version": 1, "access_token": "old"}')
        with self.assertRaises(TraktAuthError) as context:
            self.client(lambda *args: self.fail("invalid state must not call Trakt")).get("/recommendations/movies")
        self.assertEqual(context.exception.code, "reconnect_required")
        self.assertEqual(str(context.exception), "Trakt reconnect required")

    def test_state_sanitizes_unexpected_token_store_read_errors(self):
        client = self.client(lambda *args: self.fail("state read must fail before transport"))
        client.token_store = mock.Mock()
        leaked = r"C:\private\trakt-token.json: access denied"
        client.token_store.load.side_effect = PermissionError(leaked)
        with self.assertRaisesRegex(RuntimeError, "^Trakt temporarily unavailable$") as context:
            client._state()
        self.assertNotIn(leaked, str(context.exception))

    def test_concurrent_proactive_refreshes_rotate_once(self):
        refresh_started = threading.Event()
        release_refresh = threading.Event()
        refresh_count = 0
        refresh_count_lock = threading.Lock()

        def transport(method, url, headers, body):
            nonlocal refresh_count
            if url.endswith("/oauth/token"):
                with refresh_count_lock:
                    refresh_count += 1
                refresh_started.set()
                release_refresh.wait(2)
                return FakeResponse(200, {"access_token": "access-new", "refresh_token": "refresh-new", "expires_in": 3600})
            return FakeResponse(200, {"ok": True})

        client = self.client(transport)
        results = []
        threads = [threading.Thread(target=lambda: results.append(client.get("/recommendations/movies"))) for _ in range(2)]
        for thread in threads:
            thread.start()
        self.assertTrue(refresh_started.wait(1))
        release_refresh.set()
        for thread in threads:
            thread.join(2)
        self.assertEqual(refresh_count, 1)
        self.assertEqual(results, [{"ok": True}, {"ok": True}])

    def test_temporary_refresh_failure_preserves_state_without_leaking_details(self):
        original = TraktTokenStore(self.path).load()

        def transport(method, url, headers, body):
            if url.endswith("/oauth/token"):
                return FakeResponse(503, {"access_token": "do-not-leak"})
            self.fail("the expired request must refresh first")

        with self.assertRaisesRegex(RuntimeError, "^Trakt temporarily unavailable$") as context:
            self.client(transport).get("/recommendations/movies")
        self.assertEqual(TraktTokenStore(self.path).load(), original)
        self.assertNotIn("refresh-old", str(context.exception))
        self.assertNotIn("do-not-leak", str(context.exception))

    def test_concurrent_401_retries_rotate_once(self):
        refresh_started = threading.Event()
        release_refresh = threading.Event()
        refresh_count = 0
        refresh_count_lock = threading.Lock()
        api_lock = threading.Lock()
        api_calls = 0

        def transport(method, url, headers, body):
            nonlocal refresh_count, api_calls
            if url.endswith("/oauth/token"):
                with refresh_count_lock:
                    refresh_count += 1
                refresh_started.set()
                release_refresh.wait(2)
                return FakeResponse(
                    200,
                    {"access_token": "access-new", "refresh_token": "refresh-new", "expires_in": 3600},
                )
            with api_lock:
                api_calls += 1
                if api_calls <= 2:
                    return FakeResponse(401, {})
            return FakeResponse(200, {"ok": True})

        self.now = 100
        client = self.client(transport)
        results = []
        threads = [
            threading.Thread(target=lambda: results.append(client.get("/recommendations/movies")))
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        self.assertTrue(refresh_started.wait(1))
        release_refresh.set()
        for thread in threads:
            thread.join(2)
        self.assertEqual(refresh_count, 1)
        self.assertEqual(results, [{"ok": True}, {"ok": True}])


class TraktDeviceAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmpdir.name, "trakt-token.json")
        TraktTokenStore(self.path).replace(
            TraktTokenState("access-old", "refresh-old", 2_000, 1_000)
        )
        self.now = 1_100
        self.output = []

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_success_polls_pending_then_slowdown_and_persists_tokens(self):
        responses = [
            (200, {"device_code": "device", "user_code": "ABCD", "verification_url": "https://trakt.tv/activate", "expires_in": 100, "interval": 1}),
            (400, {}),
            (429, {}),
            (200, {"access_token": "access-new", "refresh_token": "refresh-new", "expires_in": 3600}),
        ]
        sleeps = []
        calls = []

        def transport(method, url, headers, body):
            calls.append((method, url, headers, body))
            return responses.pop(0)

        authorizer = TraktDeviceAuthorizer(
            "client-id", token_path=self.path, transport=transport,
            client_secret="client-secret", clock=lambda: self.now,
            sleep=sleeps.append,
        )
        state = authorizer.authorize(output=self.output.append)
        self.assertEqual(state.access_token, "access-new")
        self.assertEqual(TraktTokenStore(self.path).load(), state)
        self.assertEqual(sleeps, [1, 1, 6])
        self.assertEqual(calls[0][1], "https://auth.trakt.tv/oauth/device/code")
        self.assertEqual(calls[0][2]["Content-Type"], "application/json")
        self.assertEqual(json.loads(calls[0][3].decode("utf-8"))["client_id"], "client-id")
        self.assertEqual(calls[-1][1], "https://auth.trakt.tv/oauth/device/token")
        self.assertEqual(calls[-1][2]["Content-Type"], "application/json")
        self.assertTrue(any("ABCD" in message for message in self.output))
        self.assertFalse(any("access-new" in message or "refresh-new" in message for message in self.output))

    def test_denial_and_expiry_preserve_previous_state(self):
        original = TraktTokenStore(self.path).load()
        responses = [
            (200, {"device_code": "device", "user_code": "ABCD", "verification_url": "https://trakt.tv/activate", "expires_in": 1, "interval": 1}),
            (418, {}),
        ]
        authorizer = TraktDeviceAuthorizer(
            "client-id", token_path=self.path, transport=lambda *args: responses.pop(0),
            client_secret="client-secret", clock=lambda: self.now, sleep=lambda _: None,
        )
        with self.assertRaises(TraktAuthError):
            authorizer.authorize()
        self.assertEqual(TraktTokenStore(self.path).load(), original)

    def test_documented_terminal_statuses_preserve_previous_state(self):
        for status in (404, 409, 410):
            with self.subTest(status=status):
                original = TraktTokenStore(self.path).load()
                responses = [
                    (200, {"device_code": "device", "user_code": "ABCD", "verification_url": "https://trakt.tv/activate", "expires_in": 100, "interval": 1}),
                    (status, {}),
                ]
                authorizer = TraktDeviceAuthorizer(
                    "client-id", token_path=self.path,
                    transport=lambda *args: responses.pop(0),
                    client_secret="client-secret", clock=lambda: self.now,
                    sleep=lambda _: None,
                )
                with self.assertRaises(TraktAuthError):
                    authorizer.authorize()
                self.assertEqual(TraktTokenStore(self.path).load(), original)

    def test_connect_mode_does_not_skip_existing_state(self):
        with open(os.path.join(REPO_ROOT, "install.ps1"), encoding="utf-8") as handle:
            script = handle.read()
        connect_start = script.index("function Invoke-TraktDeviceAuthorization")
        connect_end = script.index("function Invoke-FrontendDev", connect_start)
        connect_function = script[connect_start:connect_end]
        self.assertNotIn("Trakt token state already exists. No authorization was started.", connect_function)

    def test_connect_mode_honors_configured_token_path(self):
        with open(os.path.join(REPO_ROOT, "install.ps1"), encoding="utf-8") as handle:
            script = handle.read()
        self.assertIn("function Get-TraktTokenStatePath", script)
        connect_start = script.index("function Invoke-TraktDeviceAuthorization")
        connect_end = script.index("function Invoke-FrontendDev", connect_start)
        connect_function = script[connect_start:connect_end]
        self.assertIn("Get-TraktTokenStatePath", connect_function)
        self.assertNotIn("Join-Path $stateRoot 'trakt-token.json'", connect_function)


if __name__ == "__main__":
    unittest.main()
