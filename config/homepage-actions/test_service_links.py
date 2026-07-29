"""Tests for GET /service-links browser deep-link bases."""
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

import config
from server import ActionsHandler


class ServiceLinksTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ActionsHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            body = response.read()
            return response.status, json.loads(body.decode("utf-8"))
        finally:
            conn.close()

    def test_service_link_bases_defaults(self):
        bases = config.service_link_bases()
        self.assertEqual(bases["jellyfin"], config.JELLYFIN_EXTERNAL_URL)
        self.assertEqual(bases["sonarr"], config.SONARR_EXTERNAL_URL)
        self.assertEqual(bases["radarr"], config.RADARR_EXTERNAL_URL)
        self.assertEqual(bases["prowlarr"], config.PROWLARR_EXTERNAL_URL)
        self.assertEqual(bases["qbittorrent"], config.QBITTORRENT_EXTERNAL_URL)
        self.assertEqual(bases["bazarr"], config.BAZARR_EXTERNAL_URL)

    def test_get_service_links(self):
        with mock.patch.multiple(
            config,
            JELLYFIN_EXTERNAL_URL="http://localhost:18096",
            SONARR_EXTERNAL_URL="http://localhost:18989",
            RADARR_EXTERNAL_URL="http://localhost:17878",
            PROWLARR_EXTERNAL_URL="http://localhost:19696",
            QBITTORRENT_EXTERNAL_URL="http://127.0.0.1:18081",
            BAZARR_EXTERNAL_URL="http://localhost:16767",
        ):
            status, body = self._get("/service-links")
        self.assertEqual(status, 200)
        self.assertEqual(
            body,
            {
                "jellyfin": "http://localhost:18096",
                "sonarr": "http://localhost:18989",
                "radarr": "http://localhost:17878",
                "prowlarr": "http://localhost:19696",
                "qbittorrent": "http://127.0.0.1:18081",
                "bazarr": "http://localhost:16767",
            },
        )


if __name__ == "__main__":
    unittest.main()
