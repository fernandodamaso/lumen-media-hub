import io
import json
import unittest
import urllib.error
from unittest import mock

import config
from clients import jellyseerr


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class JellyseerrClientTests(unittest.TestCase):
    def client_config(self):
        return (
            mock.patch.object(config, "JELLYSEERR_ENABLED", True),
            mock.patch.object(config, "JELLYSEERR_API_KEY", "private-key"),
            mock.patch.object(config, "JELLYSEERR_URL", "http://jellyseerr:5055"),
            mock.patch.object(config, "TIMEOUT", 7),
        )

    def test_post_sends_json_and_returns_decoded_response(self):
        payload = {
            "mediaType": "tv",
            "mediaId": 42,
            "seasons": [1, 2],
            "is4k": False,
        }
        patches = self.client_config()
        with patches[0], patches[1], patches[2], patches[3], mock.patch.object(
            jellyseerr.urllib.request,
            "urlopen",
            return_value=_Response({"id": 812, "status": 1}),
        ) as urlopen:
            result = jellyseerr._jellyseerr_post("/api/v1/request", payload)

        request = urlopen.call_args.args[0]
        self.assertEqual(result, {"id": 812, "status": 1})
        self.assertEqual(request.full_url, "http://jellyseerr:5055/api/v1/request")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data.decode("utf-8")), payload)
        self.assertEqual(request.get_header("X-api-key"), "private-key")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(urlopen.call_args.kwargs, {"timeout": 7})

    def test_http_error_retains_status_without_retaining_upstream_body(self):
        secret = "SECRET upstream body https://private.example"
        error = urllib.error.HTTPError(
            "http://jellyseerr:5055/api/v1/request",
            409,
            secret,
            {},
            io.BytesIO(secret.encode("utf-8")),
        )
        patches = self.client_config()
        with patches[0], patches[1], patches[2], patches[3], mock.patch.object(
            jellyseerr.urllib.request, "urlopen", side_effect=error
        ):
            with self.assertRaises(jellyseerr.JellyseerrUpstreamError) as raised:
                jellyseerr._jellyseerr_post(
                    "/api/v1/request",
                    {"mediaType": "movie", "mediaId": 42, "is4k": False},
                )

        self.assertEqual(raised.exception.status, 409)
        self.assertFalse(raised.exception.ambiguous)
        self.assertNotIn(secret, str(raised.exception))
        self.assertFalse(hasattr(raised.exception, "body"))

    def test_post_timeout_is_typed_as_ambiguous_and_sanitized(self):
        secret = "SECRET timeout path=C:\\private"
        patches = self.client_config()
        with patches[0], patches[1], patches[2], patches[3], mock.patch.object(
            jellyseerr.urllib.request, "urlopen", side_effect=TimeoutError(secret)
        ):
            with self.assertRaises(jellyseerr.JellyseerrUpstreamError) as raised:
                jellyseerr._jellyseerr_post(
                    "/api/v1/request",
                    {"mediaType": "movie", "mediaId": 42, "is4k": False},
                )

        self.assertIsNone(raised.exception.status)
        self.assertTrue(raised.exception.ambiguous)
        self.assertNotIn(secret, str(raised.exception))

    def test_get_http_error_uses_same_typed_safe_boundary(self):
        secret = "SECRET read body"
        error = urllib.error.HTTPError(
            "http://jellyseerr:5055/api/v1/movie/42",
            503,
            secret,
            {},
            io.BytesIO(secret.encode("utf-8")),
        )
        patches = self.client_config()
        with patches[0], patches[1], patches[2], patches[3], mock.patch.object(
            jellyseerr.urllib.request, "urlopen", side_effect=error
        ):
            with self.assertRaises(jellyseerr.JellyseerrUpstreamError) as raised:
                jellyseerr._jellyseerr_get("/api/v1/movie/42")

        self.assertEqual(raised.exception.status, 503)
        self.assertFalse(raised.exception.ambiguous)
        self.assertNotIn(secret, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
