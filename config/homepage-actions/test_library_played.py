#!/usr/bin/env python3
"""Tests for PATCH /jellyfin/items/{id}/played."""

import http.client
import json
import shutil
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

import config
from server import ActionsHandler

TOKEN = "test-actions-token"
ALLOWED_ORIGIN = "http://localhost:3000"
ITEM_ID = "abc123"


class LibraryPlayedTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="library-played-test-")
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

        self._old_token = config.ACTIONS_TOKEN
        self._old_cors = config.CORS_ORIGINS
        self._old_jellyfin_key = config.JELLYFIN_API_KEY
        self._old_cache = dict(config._jellyfin_cache)
        config.ACTIONS_TOKEN = TOKEN
        config.CORS_ORIGINS = [ALLOWED_ORIGIN]
        config.JELLYFIN_API_KEY = "test-jellyfin-key"
        config._jellyfin_cache.clear()
        self.addCleanup(self._restore_config)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ActionsHandler)
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _restore_config(self):
        config.ACTIONS_TOKEN = self._old_token
        config.CORS_ORIGINS = self._old_cors
        config.JELLYFIN_API_KEY = self._old_jellyfin_key
        config._jellyfin_cache.clear()
        config._jellyfin_cache.update(self._old_cache)

    def _request(self, method, path, body=None, token=None, origin=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token is not None:
            headers["X-Actions-Token"] = token
        if origin is not None:
            headers["Origin"] = origin
        payload = json.dumps(body) if body is not None else None
        conn.request(method, path, body=payload, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        parsed = json.loads(data.decode("utf-8")) if data else None
        return resp.status, parsed

    @mock.patch("clients.jellyfin.jellyfin_post")
    @mock.patch("clients.jellyfin._jellyfin_user_id_for_queries", return_value="user-1")
    def test_played_true_posts_then_clears_cache(self, _mock_user, mock_post):
        config._jellyfin_cache["Movie"] = {"ts": 0, "payload": {"ok": True}}

        status, body = self._request(
            "PATCH",
            f"/jellyfin/items/{ITEM_ID}/played",
            {"played": True},
            token=TOKEN,
            origin=ALLOWED_ORIGIN,
        )

        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True, "played": True})
        mock_post.assert_called_once_with(
            f"/Users/user-1/PlayedItems/{ITEM_ID}", method="POST"
        )
        self.assertEqual(config._jellyfin_cache, {})

    @mock.patch("clients.jellyfin.jellyfin_post")
    @mock.patch("clients.jellyfin._jellyfin_user_id_for_queries", return_value="user-1")
    def test_played_false_deletes(self, _mock_user, mock_post):
        status, body = self._request(
            "PATCH",
            f"/jellyfin/items/{ITEM_ID}/played",
            {"played": False},
            token=TOKEN,
            origin=ALLOWED_ORIGIN,
        )

        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True, "played": False})
        mock_post.assert_called_once_with(
            f"/Users/user-1/PlayedItems/{ITEM_ID}", method="DELETE"
        )

    @mock.patch("clients.jellyfin.jellyfin_post", side_effect=RuntimeError("secret /Users/boom"))
    @mock.patch("clients.jellyfin._jellyfin_user_id_for_queries", return_value="user-1")
    def test_jellyfin_exception_returns_502_and_keeps_cache(self, _mock_user, _mock_post):
        config._jellyfin_cache["Movie"] = {"ts": 0, "payload": {"ok": True}}

        status, body = self._request(
            "PATCH",
            f"/jellyfin/items/{ITEM_ID}/played",
            {"played": True},
            token=TOKEN,
            origin=ALLOWED_ORIGIN,
        )

        self.assertEqual(status, 502)
        self.assertEqual(body, {"ok": False, "error": "Unable to update watched state"})
        self.assertIn("Movie", config._jellyfin_cache)
        raw = json.dumps(body)
        self.assertNotIn("secret", raw)
        self.assertNotIn("/Users/", raw)

    def test_missing_token_rejects(self):
        status, body = self._request(
            "PATCH",
            f"/jellyfin/items/{ITEM_ID}/played",
            {"played": True},
            token=None,
            origin=ALLOWED_ORIGIN,
        )
        self.assertEqual(status, 401)
        self.assertEqual(body, {"ok": False, "error": "Unauthorized"})

    def test_disallowed_origin_rejects(self):
        status, body = self._request(
            "PATCH",
            f"/jellyfin/items/{ITEM_ID}/played",
            {"played": True},
            token=TOKEN,
            origin="http://evil.example",
        )
        self.assertEqual(status, 403)
        self.assertEqual(body, {"ok": False, "error": "Origin not allowed"})


if __name__ == "__main__":
    unittest.main()
