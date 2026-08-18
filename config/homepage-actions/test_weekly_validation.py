"""Tests for config/homepage-actions/weekly_validation.py diagnostics."""
import io
import json
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
from pathlib import Path

import weekly_validation as wv


class _FakeResp:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, *_args, **_kwargs):
        return self._data


def _http_error(code):
    return urllib.error.HTTPError("http://jellyfin:8096/Library/VirtualFolders", code, "err", {}, io.BytesIO())


class ValidateJellyfinTests(unittest.TestCase):
    def test_transient_503_then_success(self):
        calls = {
            "n": 0,
            "results": [_http_error(503), _http_error(503), _FakeResp([{"Name": "Movies"}, {"Name": "TV Shows"}])],
        }

        def fake_urlopen(*_args, **_kwargs):
            res = calls["results"][calls["n"]]
            calls["n"] += 1
            if isinstance(res, urllib.error.HTTPError):
                raise res
            return res

        sleeps = []

        def fake_sleep(secs):
            sleeps.append(secs)

        with patch("weekly_validation.urllib.request.urlopen", side_effect=fake_urlopen), patch(
            "weekly_validation.time.sleep", side_effect=fake_sleep
        ):
            result = wv.validate_jellyfin("http://jellyfin:8096", "key", attempts=3, delay_seconds=5)

        self.assertEqual(result["readiness"]["status"], "ready")
        self.assertEqual(result["authentication"]["status"], "ok")
        self.assertEqual(result["libraries"]["status"], "ok")
        self.assertEqual(result["libraries"]["missing"], [])
        self.assertEqual(sleeps, [5, 5])

    def test_503_exhaustion_reports_timeout(self):
        calls = {"n": 0}

        def fake_urlopen(*_args, **_kwargs):
            calls["n"] += 1
            raise _http_error(503)

        with patch("weekly_validation.urllib.request.urlopen", side_effect=fake_urlopen), patch(
            "weekly_validation.time.sleep"
        ):
            result = wv.validate_jellyfin("http://jellyfin:8096", "key", attempts=3, delay_seconds=5)

        self.assertEqual(result["readiness"]["status"], "timeout")
        self.assertEqual(result["libraries"]["status"], "not_checked")
        self.assertEqual(calls["n"], 3)

    def test_network_exhaustion_reports_timeout(self):
        calls = {"n": 0}

        def fake_urlopen(*_args, **_kwargs):
            calls["n"] += 1
            raise urllib.error.URLError("refused")

        with patch("weekly_validation.urllib.request.urlopen", side_effect=fake_urlopen), patch(
            "weekly_validation.time.sleep"
        ):
            result = wv.validate_jellyfin("http://jellyfin:8096", "key", attempts=6, delay_seconds=5)

        self.assertEqual(result["readiness"]["status"], "timeout")
        self.assertEqual(result["authentication"]["status"], "not_checked")

    def test_401_auth_failure_stops_without_retry(self):
        calls = {"n": 0}

        def fake_urlopen(*_args, **_kwargs):
            calls["n"] += 1
            raise _http_error(401)

        with patch("weekly_validation.urllib.request.urlopen", side_effect=fake_urlopen), patch(
            "weekly_validation.time.sleep"
        ) as sleep_mock:
            result = wv.validate_jellyfin("http://jellyfin:8096", "key", attempts=6, delay_seconds=5)

        self.assertEqual(result["readiness"]["status"], "ready")
        self.assertEqual(result["authentication"]["status"], "failed")
        self.assertEqual(result["libraries"]["status"], "not_checked")
        self.assertEqual(calls["n"], 1)
        sleep_mock.assert_not_called()

    def test_missing_api_key_reports_missing_configuration(self):
        result = wv.validate_jellyfin("http://jellyfin:8096", "", attempts=3)
        self.assertEqual(result["authentication"]["status"], "missing_configuration")
        self.assertEqual(result["readiness"]["status"], "not_checked")

    def test_empty_base_url_reports_unavailable(self):
        result = wv.validate_jellyfin("", "key")
        self.assertEqual(result["readiness"]["status"], "unavailable")

    def test_missing_movies_library_reports_missing(self):
        def fake_urlopen(*_args, **_kwargs):
            return _FakeResp([{"Name": "TV Shows"}])

        with patch("weekly_validation.urllib.request.urlopen", side_effect=fake_urlopen):
            result = wv.validate_jellyfin("http://jellyfin:8096", "key", attempts=1)

        self.assertEqual(result["readiness"]["status"], "ready")
        self.assertEqual(result["libraries"]["status"], "missing")
        self.assertEqual(result["libraries"]["missing"], ["Movies"])

    def test_malformed_body_exhaustion_reports_timeout(self):
        calls = {"n": 0}

        def fake_urlopen(*_args, **_kwargs):
            calls["n"] += 1
            return _FakeResp({"not": "a list"})

        with patch("weekly_validation.urllib.request.urlopen", side_effect=fake_urlopen), patch(
            "weekly_validation.time.sleep"
        ):
            result = wv.validate_jellyfin("http://jellyfin:8096", "key", attempts=2, delay_seconds=5)

        self.assertEqual(result["readiness"]["status"], "timeout")
        self.assertEqual(calls["n"], 2)

    def test_invalid_json_body_exhaustion_reports_timeout(self):
        calls = {"n": 0}

        class _RawBytes:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, *_args, **_kwargs):
                return b"this is not json {{{"

        def fake_urlopen(*_args, **_kwargs):
            calls["n"] += 1
            return _RawBytes()

        with patch("weekly_validation.urllib.request.urlopen", side_effect=fake_urlopen), patch(
            "weekly_validation.time.sleep"
        ):
            result = wv.validate_jellyfin("http://jellyfin:8096", "key", attempts=2, delay_seconds=5)

        # Invalid JSON must not escape the module; it is a transient unavailable body.
        self.assertEqual(result["readiness"]["status"], "timeout")
        self.assertEqual(result["libraries"]["status"], "not_checked")
        self.assertEqual(calls["n"], 2)

    def test_failure_result_leaks_no_secret_or_identifiers(self):
        token = "super-secret-token-value"
        calls = {"n": 0}

        def fake_urlopen(*_args, **_kwargs):
            calls["n"] += 1
            raise _http_error(403)

        with patch("weekly_validation.urllib.request.urlopen", side_effect=fake_urlopen):
            result = wv.validate_jellyfin("http://jellyfin:8096", token, attempts=2)

        serialized = json.dumps(result)
        self.assertNotIn(token, serialized)
        self.assertNotIn("jellyfin:8096", serialized)


class ValidateDocumentationTests(unittest.TestCase):
    def test_all_tracked_docs_present_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").touch()
            (root / "dashboard-app" / "docs").mkdir(parents=True)
            (root / "dashboard-app" / "docs" / "architecture.md").touch()
            (root / "dashboard-app" / "docs" / "quality-gates.md").touch()
            result = wv.validate_documentation(tmp)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["missing"], [])

    def test_missing_tracked_doc_reports_relative_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").touch()
            result = wv.validate_documentation(tmp)
        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["missing"], ["dashboard-app/docs/architecture.md", "dashboard-app/docs/quality-gates.md"])


class MainTests(unittest.TestCase):
    def test_main_prints_compact_sanitized_json_and_exit_code(self):
        env = {
            "JELLYFIN_URL": "http://127.0.0.1:8096",
            "JELLYFIN_API_KEY": "secret-key",
            "PROJECT_ROOT": "SOME_MISSING_ROOT",
        }

        def fake_urlopen_success(*_args, **_kwargs):
            return _FakeResp([{"Name": "Movies"}, {"Name": "TV Shows"}])

        import contextlib
        import io as _io

        out = _io.StringIO()

        # Missing PROJECT_ROOT makes documentation fail; Jellyfin succeeds.
        with (
            patch("weekly_validation.urllib.request.urlopen", side_effect=fake_urlopen_success),
            patch.dict("os.environ", env, clear=False),
            contextlib.redirect_stdout(out),
        ):
            code = wv.main()

        payload = json.loads(out.getvalue())
        self.assertEqual(payload["jellyfin"]["libraries"]["status"], "ok")
        self.assertEqual(payload["documentation"]["status"], "missing")
        # Documentation missing is a hard failure.
        self.assertEqual(code, 1)
        self.assertNotIn("secret-key", out.getvalue())


if __name__ == "__main__":
    unittest.main()
