#!/usr/bin/env python3
"""Tests for qBittorrent mutation routes and fail-closed token auth."""

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
HASH40 = "a" * 40
HASH64 = "b" * 64


class QbtActionsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="qbt-actions-test-")
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

        self._old_token = config.ACTIONS_TOKEN
        self._old_cors = config.CORS_ORIGINS
        config.ACTIONS_TOKEN = TOKEN
        config.CORS_ORIGINS = [ALLOWED_ORIGIN]
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

    def _request(
        self,
        method,
        path,
        body=None,
        token=None,
        origin=None,
        raw_body=None,
    ):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token is not None:
            headers["X-Actions-Token"] = token
        if origin is not None:
            headers["Origin"] = origin
        payload = raw_body
        if payload is None and body is not None:
            payload = json.dumps(body)
        conn.request(method, path, body=payload, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        try:
            parsed = json.loads(data.decode("utf-8")) if data else None
        except json.JSONDecodeError:
            parsed = None
        return resp.status, parsed

    @mock.patch("routes.qbittorrent.qbt_post")
    @mock.patch("routes.qbittorrent.qbt_login")
    def test_valid_40_char_hash_forwards(self, mock_login, mock_post):
        mock_post.return_value = (200, "Ok.")

        status, body = self._request(
            "POST",
            "/qbt/torrents/stop",
            {"id": HASH40},
            token=TOKEN,
            origin=ALLOWED_ORIGIN,
        )

        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True})
        mock_post.assert_called_once_with(
            "/api/v2/torrents/stop", {"hashes": HASH40}, mock.ANY
        )

    @mock.patch("routes.qbittorrent.qbt_post")
    @mock.patch("routes.qbittorrent.qbt_login")
    def test_valid_64_char_hash_forwards(self, mock_login, mock_post):
        mock_post.return_value = (200, "Ok.")

        status, body = self._request(
            "POST",
            "/qbt/torrents/start",
            {"id": HASH64},
            token=TOKEN,
            origin=ALLOWED_ORIGIN,
        )

        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True})
        mock_post.assert_called_once_with(
            "/api/v2/torrents/start", {"hashes": HASH64.lower()}, mock.ANY
        )

    def test_empty_configured_token_rejects(self):
        config.ACTIONS_TOKEN = ""
        status, body = self._request(
            "POST",
            "/qbt/torrents/stop",
            {"id": HASH40},
            token=TOKEN,
            origin=ALLOWED_ORIGIN,
        )
        self.assertEqual(status, 401)
        self.assertEqual(body, {"ok": False, "error": "Unauthorized"})

    def test_missing_token_rejects(self):
        status, body = self._request(
            "POST",
            "/qbt/torrents/stop",
            {"id": HASH40},
            token=None,
            origin=ALLOWED_ORIGIN,
        )
        self.assertEqual(status, 401)
        self.assertEqual(body, {"ok": False, "error": "Unauthorized"})

    def test_wrong_token_rejects(self):
        status, body = self._request(
            "POST",
            "/qbt/torrents/stop",
            {"id": HASH40},
            token="wrong-token",
            origin=ALLOWED_ORIGIN,
        )
        self.assertEqual(status, 401)
        self.assertEqual(body, {"ok": False, "error": "Unauthorized"})

    def test_disallowed_origin_rejects(self):
        status, body = self._request(
            "POST",
            "/qbt/torrents/stop",
            {"id": HASH40},
            token=TOKEN,
            origin="http://evil.example",
        )
        self.assertEqual(status, 403)
        self.assertEqual(body, {"ok": False, "error": "Origin not allowed"})

    def test_malformed_json_rejects(self):
        status, body = self._request(
            "POST",
            "/qbt/torrents/stop",
            token=TOKEN,
            origin=ALLOWED_ORIGIN,
            raw_body="{not-json",
        )
        self.assertEqual(status, 400)
        self.assertEqual(body, {"ok": False, "error": "Invalid JSON"})

    @mock.patch("routes.qbittorrent.qbt_post")
    @mock.patch("routes.qbittorrent.qbt_login")
    def test_invalid_ids_rejected_before_qbt(self, mock_login, mock_post):
        invalid_ids = [
            "",
            "all",
            "abc",
            "g" * 40,
            HASH40 + ",dead",
            HASH40 + "extra",
            "../" + HASH40,
            HASH40[:20],
        ]
        for torrent_id in invalid_ids:
            with self.subTest(torrent_id=torrent_id):
                status, body = self._request(
                    "POST",
                    "/qbt/torrents/stop",
                    {"id": torrent_id},
                    token=TOKEN,
                    origin=ALLOWED_ORIGIN,
                )
                self.assertEqual(status, 400)
                self.assertEqual(body, {"ok": False, "error": "Invalid torrent id"})
        mock_login.assert_not_called()
        mock_post.assert_not_called()

    @mock.patch("routes.qbittorrent.qbt_post")
    @mock.patch("routes.qbittorrent.qbt_login")
    def test_downstream_error_returns_502(self, mock_login, mock_post):
        mock_post.side_effect = RuntimeError("qBittorrent down")

        status, body = self._request(
            "POST",
            "/qbt/torrents/stop",
            {"id": HASH40},
            token=TOKEN,
            origin=ALLOWED_ORIGIN,
        )

        self.assertEqual(status, 502)
        self.assertFalse(body["ok"])
        self.assertIn("qBittorrent down", body["error"])


if __name__ == "__main__":
    unittest.main()
