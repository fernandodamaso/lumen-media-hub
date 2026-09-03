"""Bounded, injectable HTTP transport for installer service adapters.

The transport deliberately keeps the low-level ``urllib`` boundary small.  It
does not expose request or response content through installer errors: service
credentials, authorization headers, request bodies, and response bodies are
all treated as sensitive by default.
"""

from __future__ import annotations

import json as jsonlib
import http.client
import inspect
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol

from .errors import InstallerError, InvalidInputError


DEFAULT_HTTP_TIMEOUT = 30.0
_UNSET = object()
_METHOD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9!#$%&'*+.^_`|~-]*$")
_HEADER_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_SENSITIVE_PATH_MARKERS = (
    "api-key",
    "apikey",
    "api_key",
    "authorization",
    "bearer",
    "credential",
    "password",
    "passwd",
    "secret",
    "token",
)


def _has_url_control(value: str) -> bool:
    return any(ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F for char in value)


def _safe_path(path: str) -> str:
    """Keep useful endpoint context while removing credential-like segments."""

    segments = path.split("/")
    safe_segments: list[str] = []
    redact_next = False
    for segment in segments:
        if not segment:
            continue
        decoded = urllib.parse.unquote(segment)
        folded = decoded.casefold()
        sensitive = (
            redact_next
            or any(marker in folded for marker in _SENSITIVE_PATH_MARKERS)
            or "=" in decoded
            or ":" in decoded
        )
        safe_segments.append("<redacted>" if sensitive else segment)
        redact_next = any(marker in folded for marker in _SENSITIVE_PATH_MARKERS)
    return "/" + "/".join(safe_segments) if safe_segments else "/"


def _safe_url(url: Any) -> str:
    """Return URL context without credentials, query values, or fragments."""

    if not isinstance(url, str) or not url:
        return "<invalid-url>"
    if any(char.isspace() for char in url) or _has_url_control(url):
        return "<invalid-url>"
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return "<invalid-url>"
        scheme = parsed.scheme.lower()
        host = parsed.hostname or "<invalid-host>"
        # ``hostname`` strips userinfo, but preserve an explicit non-default
        # port only when parsing it is safe.
        port = ""
        try:
            if parsed.port is not None:
                port = f":{parsed.port}"
        except ValueError:
            port = ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        path = _safe_path(parsed.path or "/")
        return f"{scheme}://{host}{port}{path}"
    except Exception:
        return "<invalid-url>"


def _context(method: str, url: Any) -> str:
    return f"{method} {_safe_url(url)}"


class HttpTransportError(InstallerError):
    """Base class for redacted failures at the HTTP service boundary."""

    kind = "HTTP request failed"

    def __init__(
        self,
        message: str | None = None,
        *,
        method: str = "REQUEST",
        url: Any = "",
        status: int | None = None,
        timeout: float | None = None,
    ) -> None:
        self.method = str(method)
        self.url = _safe_url(url)
        self.status = status
        self.timeout = timeout
        detail = message or self.kind
        # Callers in this module pass only fixed, non-sensitive details.  Do
        # not append exception text, headers, or payloads here.
        safe_message = f"{detail} ({_context(self.method, url)})"
        super().__init__(safe_message)

    @property
    def report(self) -> dict[str, Any]:
        """A stable, content-free projection suitable for diagnostics."""

        return {
            "error": str(self),
            "method": self.method,
            "url": self.url,
            "status": self.status,
            "timeout": self.timeout,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report


class HttpRequestError(HttpTransportError):
    """The request could not be represented safely."""


class HttpStatusError(HttpTransportError):
    """The service returned a non-success HTTP status."""

    def __init__(self, *, method: str, url: Any, status: int) -> None:
        super().__init__(
            f"HTTP request returned status {status}",
            method=method,
            url=url,
            status=status,
        )

    @property
    def status_code(self) -> int | None:
        return self.status


class HttpTimeoutError(HttpTransportError):
    """The bounded HTTP operation exceeded its timeout."""

    def __init__(self, *, method: str, url: Any, timeout: float | None = None) -> None:
        super().__init__("HTTP request timed out", method=method, url=url, timeout=timeout)


class HttpConnectionError(HttpTransportError):
    """The HTTP operation could not connect or read from the service."""

    def __init__(self, *, method: str, url: Any) -> None:
        super().__init__("HTTP connection failed", method=method, url=url)


class HttpUrlError(HttpTransportError):
    """The URL was invalid or unsupported for this transport."""

    def __init__(self, *, method: str, url: Any) -> None:
        super().__init__("HTTP URL is invalid", method=method, url=url)


class MalformedJsonError(HttpTransportError):
    """The response body was not valid UTF-8 JSON."""

    def __init__(self, *, method: str, url: Any) -> None:
        super().__init__("HTTP response contained malformed JSON", method=method, url=url)


# Short aliases make the boundary convenient for adapters while preserving
# the more explicit names above for callers that need to catch a subtype.
HttpError = HttpTransportError
HttpResponseError = HttpStatusError
JsonDecodeError = MalformedJsonError
HttpJsonError = MalformedJsonError


@dataclass(frozen=True)
class HttpResponse:
    """Small immutable response value retaining status, headers, and bytes."""

    status: int
    headers: Mapping[str, str]
    body: bytes
    _method: str = field(default="GET", repr=False, compare=False)
    _url: str = field(default="", repr=False, compare=False)

    def __post_init__(self) -> None:
        try:
            status = int(self.status)
        except (TypeError, ValueError) as exc:
            raise ValueError("HTTP response status must be an integer") from exc
        if not isinstance(self.body, bytes):
            raise TypeError("HTTP response body must be bytes")
        try:
            headers = dict(self.headers)
        except (TypeError, ValueError) as exc:
            raise TypeError("HTTP response headers must be a mapping") from exc
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "headers", MappingProxyType(headers))

    @property
    def raw_body(self) -> bytes:
        return self.body

    @property
    def content(self) -> bytes:
        return self.body

    def json(self) -> Any:
        """Decode JSON, mapping malformed content to a redacted typed error."""

        try:
            return jsonlib.loads(self.body)
        except (UnicodeDecodeError, jsonlib.JSONDecodeError, TypeError, ValueError):
            # Raise outside the ``except`` block so even ``__context__`` does
            # not retain a decoder object whose ``doc`` may contain secrets.
            error = MalformedJsonError(method=self._method, url=self._url)
        raise error from None

    def json_data(self) -> Any:
        """Explicit alias for adapters that prefer a named decoding boundary."""

        return self.json()


class _Opener(Protocol):
    def __call__(self, request: urllib.request.Request, *, timeout: float) -> Any:
        ...


def _timeout(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidInputError("HTTP timeout must be a positive finite number") from exc
    if not math.isfinite(result) or result <= 0:
        raise InvalidInputError("HTTP timeout must be a positive finite number")
    return result


def _validate_method(method: Any) -> str:
    if not isinstance(method, str) or not _METHOD_RE.fullmatch(method):
        raise InvalidInputError("HTTP method is invalid")
    return method.upper()


def _validate_url(method: str, url: Any) -> str:
    if not isinstance(url, str) or not url:
        raise HttpUrlError(method=method, url=url)
    if any(char.isspace() for char in url) or _has_url_control(url):
        raise HttpUrlError(method=method, url=url)
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise ValueError
        # Force validation of malformed ports and bracketed hostnames.
        _ = parsed.port
        if parsed.hostname is None:
            raise ValueError
    except (TypeError, ValueError):
        raise HttpUrlError(method=method, url=url) from None
    return url


def _validate_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    if headers is None:
        return {}
    if not isinstance(headers, Mapping):
        raise InvalidInputError("HTTP headers must be a mapping")
    normalized: dict[str, str] = {}
    for name, value in headers.items():
        if (
            not isinstance(name, str)
            or not _HEADER_RE.fullmatch(name)
            or not isinstance(value, str)
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
        ):
            raise InvalidInputError("HTTP headers contain an invalid value")
        normalized[name] = value
    return normalized


def _header_present(headers: Mapping[str, str], name: str) -> bool:
    return any(key.lower() == name.lower() for key in headers)


def _is_timeout(error: BaseException) -> bool:
    """Recognize timeout wrappers without retaining their reason text."""

    if isinstance(error, TimeoutError):
        return True
    reason = getattr(error, "reason", None)
    return (
        isinstance(reason, TimeoutError)
        or "timed out" in type(reason).__name__.lower()
        or (isinstance(reason, str) and "timed out" in reason.lower())
    )


def _invoke_opener(opener: Any, request: urllib.request.Request, timeout: float) -> Any:
    """Call an injected opener with either keyword or positional timeout.

    ``urllib`` exposes timeout as a keyword-capable parameter, while tiny test
    seams and adapter-owned openers commonly use a positional parameter.  Use
    signature inspection to support both without retrying a request when the
    opener itself raises ``TypeError``.  An opener that cannot accept the
    explicit timeout is rejected instead of creating an unbounded network
    path.
    """

    target = opener.open if hasattr(opener, "open") else opener
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):
        return target(request, timeout=timeout)
    parameters = tuple(signature.parameters.values())
    timeout_parameter = signature.parameters.get("timeout")
    if timeout_parameter is not None and timeout_parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
        return target(request, timeout)
    if timeout_parameter is not None or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters
    ):
        return target(request, timeout=timeout)
    if any(parameter.kind is inspect.Parameter.VAR_POSITIONAL for parameter in parameters):
        return target(request, timeout)
    raise InvalidInputError("HTTP opener must accept an explicit timeout")


class HttpTransport:
    """A standard-library HTTP transport with one bounded execution seam."""

    def __init__(
        self,
        opener: _Opener | Any | None = None,
        *,
        timeout: float = DEFAULT_HTTP_TIMEOUT,
        request_factory: Callable[..., urllib.request.Request] | None = None,
    ) -> None:
        self.timeout = _timeout(timeout)
        self._opener = urllib.request.urlopen if opener is None else opener
        self._request_factory = urllib.request.Request if request_factory is None else request_factory

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, Any] | None = None,
        body: bytes | str | None = None,
        data: bytes | str | None = None,
        json_body: Any = _UNSET,
        form: Mapping[str, Any] | list[tuple[str, Any]] | tuple[tuple[str, Any], ...] | None = None,
        json: Any = _UNSET,
        timeout: float | None = None,
        expect_json: bool = False,
    ) -> HttpResponse:
        """Execute one HTTP request and return a typed response.

        ``json_body`` (or its ``json`` alias) and ``form`` are mutually
        exclusive with raw ``body``/``data``.  ``expect_json`` validates the
        response using :meth:`HttpResponse.json` while still returning the raw
        response value to the caller.
        """

        normalized_method = _validate_method(method)
        request_url = _validate_url(normalized_method, url)
        request_headers = _validate_headers(headers)
        selected_timeout = self.timeout if timeout is None else _timeout(timeout)

        if json_body is not _UNSET and json is not _UNSET:
            raise InvalidInputError("HTTP JSON body was provided more than once")
        if json is not _UNSET:
            json_body = json
        if data is not None and body is not None:
            raise InvalidInputError("HTTP request body was provided more than once")
        if data is not None:
            body = data
        if sum(value is not _UNSET for value in (json_body,)) + int(form is not None) + int(body is not None) > 1:
            raise InvalidInputError("HTTP request body was provided more than once")

        encoded_body: bytes | None
        encoding_error: HttpRequestError | None = None
        if json_body is not _UNSET:
            try:
                encoded_body = jsonlib.dumps(json_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            except (TypeError, ValueError, UnicodeError):
                encoding_error = HttpRequestError(
                    "HTTP JSON body could not be encoded",
                    method=normalized_method,
                    url=request_url,
                )
                encoded_body = None
            if not _header_present(request_headers, "Content-Type"):
                request_headers["Content-Type"] = "application/json"
        elif form is not None:
            try:
                encoded_body = urllib.parse.urlencode(form, doseq=True).encode("ascii")
            except (TypeError, ValueError, UnicodeError):
                encoding_error = HttpRequestError(
                    "HTTP form body could not be encoded",
                    method=normalized_method,
                    url=request_url,
                )
                encoded_body = None
            if not _header_present(request_headers, "Content-Type"):
                request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is None:
            encoded_body = None
        elif isinstance(body, bytes):
            encoded_body = body
        elif isinstance(body, str):
            encoded_body = body.encode("utf-8")
        else:
            raise InvalidInputError("HTTP request body must be bytes or text")

        if encoding_error is not None:
            raise encoding_error from None

        try:
            request = self._request_factory(
                request_url,
                data=encoded_body,
                headers=request_headers,
                method=normalized_method,
            )
        except (TypeError, ValueError):
            request_error = HttpRequestError(
                "HTTP request could not be created",
                method=normalized_method,
                url=request_url,
            )
        else:
            request_error = None
        if request_error is not None:
            raise request_error

        opener_error: HttpTransportError | None = None
        try:
            raw_response = _invoke_opener(self._opener, request, selected_timeout)
        except urllib.error.HTTPError as exc:
            status = getattr(exc, "code", None)
            try:
                status = int(status)
            except (TypeError, ValueError):
                status = 0
            opener_error = HttpStatusError(method=normalized_method, url=request_url, status=status)
        except TimeoutError:
            opener_error = HttpTimeoutError(
                method=normalized_method, url=request_url, timeout=selected_timeout
            )
        except http.client.InvalidURL:
            opener_error = HttpUrlError(method=normalized_method, url=request_url)
        except http.client.HTTPException:
            opener_error = HttpConnectionError(method=normalized_method, url=request_url)
        except urllib.error.URLError as exc:
            # URLError is intentionally reduced to a generic category: its
            # reason can contain the URL, credentials, or service internals.
            if _is_timeout(exc):
                opener_error = HttpTimeoutError(
                    method=normalized_method, url=request_url, timeout=selected_timeout
                )
            else:
                opener_error = HttpConnectionError(method=normalized_method, url=request_url)
        except OSError:
            opener_error = HttpConnectionError(method=normalized_method, url=request_url)

        if opener_error is not None:
            raise opener_error from None

        response_error: HttpTransportError | None = None
        response_status: int
        response_headers: Mapping[str, str]
        response_body: bytes
        try:
            try:
                response_status = getattr(raw_response, "status", None)
                if response_status is None:
                    response_status = raw_response.getcode()
                response_status = int(response_status)
                response_headers = getattr(raw_response, "headers", {})
                if response_headers is None:
                    response_headers = {}
                if hasattr(response_headers, "items"):
                    response_headers = dict(response_headers.items())
                else:
                    response_headers = dict(response_headers)
                response_body = raw_response.read()
                if not isinstance(response_body, bytes):
                    if isinstance(response_body, str):
                        response_body = response_body.encode("utf-8")
                    else:
                        raise TypeError
            except TimeoutError:
                response_error = HttpTimeoutError(
                    method=normalized_method, url=request_url, timeout=selected_timeout
                )
            except http.client.HTTPException:
                response_error = HttpConnectionError(method=normalized_method, url=request_url)
            except urllib.error.URLError as exc:
                if _is_timeout(exc):
                    response_error = HttpTimeoutError(
                        method=normalized_method, url=request_url, timeout=selected_timeout
                    )
                else:
                    response_error = HttpConnectionError(method=normalized_method, url=request_url)
            except OSError:
                response_error = HttpConnectionError(method=normalized_method, url=request_url)
            except (AttributeError, TypeError, ValueError):
                response_error = HttpRequestError(
                    "HTTP response was invalid",
                    method=normalized_method,
                    url=request_url,
                )
        finally:
            close = getattr(raw_response, "close", None)
            if callable(close):
                close()

        if response_error is not None:
            raise response_error from None

        response = HttpResponse(
            response_status,
            response_headers,
            response_body,
            _method=normalized_method,
            _url=request_url,
        )
        if not 200 <= response.status < 300:
            raise HttpStatusError(method=normalized_method, url=request_url, status=response.status)
        if expect_json:
            response.json()
        return response

    def request_json(self, method: str, url: str, **kwargs: Any) -> Any:
        """Execute a request and return its decoded JSON payload."""

        return self.request(method, url, expect_json=True, **kwargs).json()

    def get(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("DELETE", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("HEAD", url, **kwargs)


# Names used by a few adapter-oriented call sites remain aliases so this
# module is a small stable boundary rather than a naming constraint.
HttpClient = HttpTransport
Response = HttpResponse


__all__ = [
    "DEFAULT_HTTP_TIMEOUT",
    "HttpClient",
    "HttpConnectionError",
    "HttpError",
    "HttpJsonError",
    "HttpRequestError",
    "HttpResponse",
    "HttpResponseError",
    "HttpStatusError",
    "HttpTimeoutError",
    "HttpTransport",
    "HttpTransportError",
    "HttpUrlError",
    "JsonDecodeError",
    "MalformedJsonError",
    "Response",
]
