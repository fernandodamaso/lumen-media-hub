#!/usr/bin/env python3
"""Tests for data-safe Sonarr queue mutations."""

import json
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import clients.arr as arr_client


class _CaptureRequestHandler(BaseHTTPRequestHandler):
    request_data = None
    request_ready = threading.Event()

    def do_DELETE(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        type(self).request_data = {
            "command": self.command,
            "path": self.path,
            "body": json.loads(body.decode("utf-8")),
        }
        type(self).request_ready.set()
        self.send_response(204)
        self.end_headers()

    def log_message(self, format, *args):
        pass


class SonarrQueueClientTestCase(unittest.TestCase):
    def setUp(self):
        _CaptureRequestHandler.request_data = None
        _CaptureRequestHandler.request_ready.clear()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _CaptureRequestHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_ignore_queue_items_uses_safe_sonarr_bulk_delete_contract(self):
        base = f"http://127.0.0.1:{self.server.server_address[1]}"
        with mock.patch.object(arr_client.settings, "SONARR_URL", base), mock.patch.object(
            arr_client.settings, "SONARR_API_KEY", "test-sonarr-key"
        ):
            arr_client.ignore_sonarr_queue_items([22, 11, 22])

        self.assertTrue(_CaptureRequestHandler.request_ready.wait(timeout=5))
        request = _CaptureRequestHandler.request_data
        parsed = urllib.parse.urlparse(request["path"])
        self.assertEqual(request["command"], "DELETE")
        self.assertEqual(parsed.path, "/api/v3/queue/bulk")
        self.assertEqual(
            urllib.parse.parse_qs(parsed.query),
            {
                "removeFromClient": ["false"],
                "blocklist": ["false"],
                "skipRedownload": ["false"],
                "changeCategory": ["false"],
            },
        )
        self.assertEqual(request["body"], {"ids": [11, 22]})

    def test_ignore_queue_items_rejects_invalid_ids_without_request(self):
        invalid_queue_ids = ([True], [False], ["1"], [0], [-1], [])

        for queue_ids in invalid_queue_ids:
            with self.subTest(queue_ids=queue_ids):
                with self.assertRaises(ValueError):
                    arr_client.ignore_sonarr_queue_items(queue_ids)

        self.assertFalse(_CaptureRequestHandler.request_ready.is_set())
        self.assertIsNone(_CaptureRequestHandler.request_data)


if __name__ == "__main__":
    unittest.main()
