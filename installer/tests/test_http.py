import json
import http.client
import socket
import sys
import unittest
import urllib.error
from pathlib import Path


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_ROOT = WORKTREE_ROOT / "installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.errors import InvalidInputError
from lumen_installer.http import (
    HttpConnectionError,
    HttpRequestError,
    HttpStatusError,
    HttpTimeoutError,
    HttpTransport,
    HttpUrlError,
    MalformedJsonError,
)


class _Response:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def close(self):
        pass


class _StatusResponse(_Response):
    def __init__(self, status, body=b"", headers=None):
        self.status = status
        self.headers = headers or {}
        super().__init__(body)


class HttpTransportTests(unittest.TestCase):
    def test_successful_json_response_is_typed_and_decodable(self):
        requests = []

        def opener(request, *, timeout):
            requests.append((request, timeout))
            return _Response(json.dumps({"ok": True}).encode())

        response = HttpTransport(opener=opener).get("http://127.0.0.1:8096/api/items")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertEqual(response.body, b'{"ok": true}')
        self.assertEqual(requests[0][0].get_method(), "GET")
        self.assertGreater(requests[0][1], 0)

    def test_json_body_is_encoded_at_the_request_boundary(self):
        requests = []

        def opener(request, *, timeout):
            requests.append(request)
            return _Response(b'{"accepted":true}')

        response = HttpTransport(opener=opener).post(
            "http://127.0.0.1:8096/api/items",
            json_body={"title": "A film", "enabled": True},
        )

        self.assertEqual(response.json(), {"accepted": True})
        self.assertEqual(requests[0].get_method(), "POST")
        self.assertEqual(requests[0].data, b'{"title":"A film","enabled":true}')
        self.assertEqual(requests[0].get_header("Content-type"), "application/json")

    def test_form_body_and_explicit_method_headers_are_encoded(self):
        requests = []

        def opener(request, *, timeout):
            requests.append(request)
            return _Response(b"ok")

        HttpTransport(opener=opener).request(
            "PATCH",
            "http://127.0.0.1:8096/api/items/7",
            form=[("name", "A film"), ("tag", "one"), ("tag", "two")],
            headers={"Authorization": "Bearer secret", "X-Trace": "test"},
            timeout=1.25,
        )

        request = requests[0]
        self.assertEqual(request.get_method(), "PATCH")
        self.assertEqual(request.data, b"name=A+film&tag=one&tag=two")
        self.assertEqual(request.get_header("Content-type"), "application/x-www-form-urlencoded")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(request.get_header("X-trace"), "test")

    def test_supported_method_helpers_build_the_requested_methods(self):
        requests = []

        def opener(request, *, timeout):
            requests.append(request)
            return _Response(b"")

        transport = HttpTransport(opener=opener)
        transport.put("http://127.0.0.1:8096/api/items/7")
        transport.delete("http://127.0.0.1:8096/api/items/7")
        transport.head("http://127.0.0.1:8096/api/items/7")

        self.assertEqual([request.get_method() for request in requests], ["PUT", "DELETE", "HEAD"])

    def test_malformed_json_is_typed_without_returning_response_content(self):
        secret = "response-secret"

        def opener(request, *, timeout):
            return _Response(f'{{"token":"{secret}"'.encode())

        response = HttpTransport(opener=opener).get(
            f"http://127.0.0.1:8096/api/items?token={secret}"
        )

        with self.assertRaises(MalformedJsonError) as raised:
            response.json()
        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn(secret, repr(raised.exception.report))
        self.assertIn("GET http://127.0.0.1:8096/api/items", str(raised.exception))

    def test_unauthorized_status_is_typed_and_preserves_status_only(self):
        secret = "authorization-secret"

        def opener(request, *, timeout):
            return _StatusResponse(
                401,
                f'{{"error":"{secret}"}}'.encode(),
                {"Authorization": f"Bearer {secret}"},
            )

        with self.assertRaises(HttpStatusError) as raised:
            HttpTransport(opener=opener).get(
                f"http://127.0.0.1:8096/api/items?api_key={secret}",
                headers={"Authorization": f"Bearer {secret}"},
            )

        self.assertEqual(raised.exception.status, 401)
        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn(secret, repr(raised.exception.report))
        self.assertIn("GET http://127.0.0.1:8096/api/items", str(raised.exception))

    def test_other_non_success_statuses_are_typed_with_status(self):
        for status in (300, 404, 500):
            with self.subTest(status=status):
                with self.assertRaises(HttpStatusError) as raised:
                    HttpTransport(
                        opener=lambda request, *, timeout, status=status: _StatusResponse(status)
                    ).get("http://127.0.0.1:8096/api/items")
                self.assertEqual(raised.exception.status, status)

    def test_urllib_http_error_keeps_unauthorized_status_without_body(self):
        secret = "http-error-secret"

        def opener(request, *, timeout):
            error = urllib.error.HTTPError(
                request.full_url,
                401,
                "unauthorized",
                {"Authorization": f"Bearer {secret}"},
                None,
            )
            error.close()
            raise error

        with self.assertRaises(HttpStatusError) as raised:
            HttpTransport(opener=opener).get(
                f"http://127.0.0.1:8096/api/items?token={secret}",
                headers={"Authorization": f"Bearer {secret}"},
            )
        self.assertEqual(raised.exception.status, 401)
        self.assertNotIn(secret, str(raised.exception))
        self.assertIsNone(raised.exception.__context__)

    def test_timeout_during_response_read_is_typed_as_timeout(self):
        class ReadTimeout(_Response):
            def read(self):
                raise TimeoutError("secret read timeout")

        with self.assertRaises(HttpTimeoutError) as raised:
            HttpTransport(opener=lambda request, *, timeout: ReadTimeout(b"")).get(
                "http://127.0.0.1:8096/api/items"
            )
        self.assertNotIn("secret", str(raised.exception))
        self.assertIsNone(raised.exception.__context__)

    def test_connection_failure_during_response_read_is_typed_as_connection(self):
        class ReadFailure(_Response):
            def read(self):
                raise urllib.error.URLError("secret read failure")

        with self.assertRaises(HttpConnectionError) as raised:
            HttpTransport(opener=lambda request, *, timeout: ReadFailure(b"")).get(
                "http://127.0.0.1:8096/api/items"
            )
        self.assertNotIn("secret", str(raised.exception))
        self.assertIsNone(raised.exception.__context__)

    def test_timeout_is_typed_and_the_configured_timeout_is_always_passed(self):
        observed = []

        def opener(request, *, timeout):
            observed.append(timeout)
            raise TimeoutError("secret should not be copied")

        with self.assertRaises(HttpTimeoutError) as raised:
            HttpTransport(opener=opener, timeout=2.5).get("http://127.0.0.1:8096/api/items")
        self.assertEqual(observed, [2.5])
        self.assertEqual(raised.exception.timeout, 2.5)

    def test_injected_positional_timeout_opener_is_supported(self):
        observed = []

        def opener(request, timeout):
            observed.append(timeout)
            return _Response(b"ok")

        HttpTransport(opener=opener, timeout=1.75).get("http://127.0.0.1:8096/api/items")
        self.assertEqual(observed, [1.75])

    def test_url_timeout_failure_is_typed_without_reason_text(self):
        secret = "socket-secret"

        def opener(request, *, timeout):
            raise urllib.error.URLError(socket.timeout(secret))

        with self.assertRaises(HttpTimeoutError) as raised:
            HttpTransport(opener=opener).get(f"http://127.0.0.1:8096/api/items?token={secret}")
        self.assertNotIn(secret, str(raised.exception))
        self.assertIsNone(raised.exception.__context__)

    def test_connection_failure_is_typed_without_exception_text(self):
        secret = "connection-secret"

        def opener(request, *, timeout):
            raise urllib.error.URLError(secret)

        with self.assertRaises(HttpConnectionError) as raised:
            HttpTransport(opener=opener).get(
                f"http://127.0.0.1:8096/api/items?token={secret}"
            )
        self.assertNotIn(secret, str(raised.exception))
        self.assertIsNone(raised.exception.__context__)

    def test_json_encoding_failure_drops_the_sensitive_cause(self):
        with self.assertRaises(HttpRequestError) as raised:
            HttpTransport(opener=lambda request, *, timeout: _Response(b"ok")).post(
                "http://127.0.0.1:8096/api/items",
                json_body=object(),
            )
        self.assertIsNone(raised.exception.__context__)

    def test_newline_injection_is_rejected_without_echoing_input(self):
        secret = "header-secret"
        transport = HttpTransport(opener=lambda request, *, timeout: _Response(b"ok"))

        with self.assertRaises(InvalidInputError) as raised:
            transport.get(
                "http://127.0.0.1:8096/api/items",
                headers={"X-Injected": f"ok\r\nAuthorization: {secret}"},
            )
        self.assertNotIn(secret, str(raised.exception))

        with self.assertRaises(InvalidInputError):
            transport.request("GET\r\nX-Injected: yes", "http://127.0.0.1:8096/api/items")

    def test_malformed_url_is_typed_without_echoing_credentials(self):
        secret = "url-secret"
        transport = HttpTransport(opener=lambda request, *, timeout: _Response(b"ok"))

        with self.assertRaises(HttpUrlError) as raised:
            transport.get(f"https://user:{secret}@bad host/api?token={secret}")
        self.assertNotIn(secret, str(raised.exception))
        self.assertIn("GET <invalid-url>", str(raised.exception))

    def test_all_c0_url_controls_are_rejected_and_never_reported(self):
        transport = HttpTransport(opener=lambda request, *, timeout: _Response(b"ok"))
        for url, control in (
            ("http://bad\x00host/api/items", "\x00"),
            ("http://example.test/api/\x01items", "\x01"),
            ("http://example.test/api/\x1fitems", "\x1f"),
            ("http://example.test/api/items\x7f", "\x7f"),
        ):
            with self.subTest(control=repr(control)):
                with self.assertRaises(HttpUrlError) as raised:
                    transport.get(url)
                self.assertNotIn(control, str(raised.exception))
                self.assertIsNone(raised.exception.__context__)

    def test_safe_url_reduction_removes_sensitive_path_and_url_components(self):
        secret = "path-secret"
        transport = HttpTransport(
            opener=lambda request, *, timeout: _StatusResponse(500, b"service failure")
        )

        with self.assertRaises(HttpStatusError) as raised:
            transport.get(
                f"https://user:{secret}@example.test/api/{secret}?token={secret}#{secret}",
                headers={"Authorization": f"Bearer {secret}"},
            )

        message = str(raised.exception)
        self.assertNotIn(secret, message)
        self.assertNotIn("user", message)
        self.assertIn("GET https://example.test/api", message)

    def test_malformed_port_urls_are_fully_redacted_without_exception_context(self):
        transport = HttpTransport(opener=lambda request, *, timeout: _Response(b"ok"))
        cases = (
            ("https://example.test:port-secret/api", "port-secret"),
            ("https://host-secret:foo/api", "host-secret"),
            ("https://%68ost-secret:foo/api", "%68ost-secret"),
        )

        for url, forbidden in cases:
            with self.subTest(url=url):
                with self.assertRaises(HttpUrlError) as raised:
                    transport.get(url)
                self.assertIsNone(raised.exception.__context__)
                self.assertNotIn(forbidden, str(raised.exception))
                self.assertNotIn(forbidden, repr(raised.exception.report))
                self.assertIn("GET <invalid-url>", str(raised.exception))

    def test_timeout_must_be_positive_and_finite(self):
        for value in (0, -1, float("inf"), float("nan"), "not-a-number"):
            with self.subTest(value=value):
                with self.assertRaises(InvalidInputError):
                    HttpTransport(timeout=value)

    def test_opener_without_timeout_parameter_is_rejected(self):
        calls = []

        def unbounded_opener(request):
            calls.append(request)
            return _Response(b"ok")

        with self.assertRaisesRegex(InvalidInputError, "timeout"):
            HttpTransport(opener=unbounded_opener).get(
                "http://127.0.0.1:8096/api/items"
            )
        self.assertEqual(calls, [])

    def test_incomplete_response_is_typed_as_connection_failure(self):
        class IncompleteResponse(_Response):
            def read(self):
                raise http.client.IncompleteRead(b"partial", 2)

        with self.assertRaises(HttpConnectionError):
            HttpTransport(opener=lambda request, *, timeout: IncompleteResponse(b"")).get(
                "http://127.0.0.1:8096/api/items"
            )

    def test_malformed_json_drops_the_sensitive_decode_cause(self):
        secret = "response-secret"
        response = HttpTransport(
            opener=lambda request, *, timeout: _Response(
                (f'{{"secret":"{secret}"').encode()
            )
        ).get("http://127.0.0.1:8096/api/items")

        with self.assertRaises(MalformedJsonError) as raised:
            response.json()
        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)

    def test_request_creation_failure_drops_the_sensitive_cause(self):
        secret = "request-secret"

        def request_factory(*args, **kwargs):
            raise ValueError(secret)

        with self.assertRaises(HttpRequestError) as raised:
            HttpTransport(
                opener=lambda request, *, timeout: _Response(b"ok"),
                request_factory=request_factory,
            ).get(f"https://example.test/api?token={secret}")
        self.assertNotIn(secret, str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)

    def test_response_exposes_raw_body_alias(self):
        body = b"raw bytes"
        response = HttpTransport(opener=lambda request, *, timeout: _Response(body)).get(
            "http://127.0.0.1:8096/api/items"
        )
        self.assertEqual(response.raw_body, body)
        self.assertEqual(response.content, body)


if __name__ == "__main__":
    unittest.main()
