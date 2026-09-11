import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import config
from server import ActionsHandler


class StorageCleanupRouteTests(unittest.TestCase):
    def request(self, server, method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        headers = {
            "Origin": "http://test.local",
            "X-Actions-Token": "test-token",
        }
        encoded = None
        if body is not None:
            encoded = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(encoded))
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        connection.close()
        return response.status, payload

    def test_cleanup_preview_is_post_only_and_no_storage_delete_route_exists(self):
        with patch.object(config, "ACTIONS_TOKEN", "test-token"), patch.object(
            config, "CORS_ORIGINS", ["http://test.local"]
        ):
            server = ThreadingHTTPServer(("127.0.0.1", 0), ActionsHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, payload = self.request(server, "POST", "/storage/cleanup-preview", {})
                self.assertEqual(status, 400)
                self.assertFalse(payload["ok"])

                status, payload = self.request(server, "DELETE", "/storage/cleanup-preview")
                self.assertEqual(status, 404)
                self.assertEqual(payload, {"ok": False, "error": "Unknown endpoint"})

                status, payload = self.request(server, "POST", "/storage/cleanup-delete", {})
                self.assertEqual(status, 404)
                self.assertEqual(payload, {"ok": False, "error": "Unknown endpoint"})
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
