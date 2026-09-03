"""Safe qBittorrent Web API configuration for the Linux installer.

The adapter authenticates only through the Web API. Credentials, temporary
log candidates, and the Web API cookie stay in private execution state; plans,
results, exceptions, and representations contain only stable safe metadata.
"""

from __future__ import annotations

import inspect
import io
import json
import posixpath
import re
import urllib.parse
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..errors import InstallerError, InvalidInputError, PartialError
from ..http import (
    HttpConnectionError,
    HttpResponse,
    HttpStatusError,
    HttpTimeoutError,
    HttpTransportError,
    MalformedJsonError,
)
from .base import ServiceCheckpoint, ServicePlan, ServiceResult


SERVICE_NAME = "qbittorrent"
USERNAME = "admin"
DEFAULT_BASE_URL = "http://127.0.0.1:8081"
DEFAULT_SAVE_PATH = "/downloads"
DEFAULT_LOG_MAX_BYTES = 64 * 1024
DEFAULT_LOG_MAX_LINES = 200

_TEMPORARY_PASSWORD_LINE = re.compile(
    r"The WebUI administrator password was not set\. "
    r"A temporary password is provided for this session: (?P<password>\S+)"
)
_MISSING = object()


class QbittorrentError(InstallerError):
    """Base class for sanitized qBittorrent adapter failures."""

    code = "qbittorrent-error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        self.code = code or type(self).code
        InstallerError.__init__(self, message)


class QbittorrentAuthenticationError(PartialError, QbittorrentError):
    """The Web API refused a credential or the service is currently banning it."""

    code = "qbittorrent-authentication"

    def __init__(self, status: int | None = None) -> None:
        self.status = status
        self.status_code = status
        self.banned = status in {403, 429}
        suffix = " or wait for the WebUI ban to expire" if self.banned else ""
        self.code = type(self).code
        PartialError.__init__(
            self,
            "qBittorrent authentication was refused; verify the current credentials"
            + suffix,
        )


class QbittorrentPasswordVerificationError(QbittorrentAuthenticationError):
    """The password selected for adoption could not be verified after setting it."""

    code = "qbittorrent-password-verification"

    def __init__(self, status: int | None = None) -> None:
        self.status = status
        self.status_code = status
        self.banned = status in {403, 429}
        self.code = type(self).code
        PartialError.__init__(
            self,
            "qBittorrent password verification failed; retain the existing credential and retry",
        )


class QbittorrentCredentialError(PartialError, QbittorrentError):
    """No known credential was safe to try against an adopted service."""

    code = "qbittorrent-credentials"

    def __init__(self) -> None:
        self.code = type(self).code
        PartialError.__init__(
            self,
            "qBittorrent credentials are unknown; provide QBT_PASSWORD or choose credential recovery"
        )


class QbittorrentSchemaError(InvalidInputError, QbittorrentError):
    """The service returned a response outside the supported API contract."""

    code = "qbittorrent-schema"

    def __init__(self) -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, "qBittorrent response schema is unsupported")


class QbittorrentTransportError(QbittorrentError):
    """An unexpected injected transport failure with its cause removed."""

    code = "qbittorrent-transport"

    def __init__(self) -> None:
        self.code = type(self).code
        InstallerError.__init__(self, "qBittorrent request failed")


QbittorrentAuthError = QbittorrentAuthenticationError
QBittorrentError = QbittorrentError
QBittorrentAuthenticationError = QbittorrentAuthenticationError
QBittorrentCredentialError = QbittorrentCredentialError
QBittorrentPasswordVerificationError = QbittorrentPasswordVerificationError
QBittorrentSchemaError = QbittorrentSchemaError


class QbittorrentEnvironmentUpdate(Mapping[str, str]):
    """An explicitly consumable update whose normal representation is redacted."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, Any] | None = None) -> None:
        normalized: dict[str, str] = {}
        for key, value in (values or {}).items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError("qBittorrent environment update values must be text")
            normalized[key] = value
        self._values = normalized

    def __getitem__(self, key: str) -> str:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return self._values == dict(other)
        return NotImplemented

    def as_dict(self) -> dict[str, str]:
        """Return the private values for the caller that will consume the update."""

        return dict(self._values)

    @property
    def values(self) -> dict[str, str]:
        return self.as_dict()

    @property
    def redacted(self) -> dict[str, str]:
        return {key: "<redacted>" for key in self._values}

    def __repr__(self) -> str:
        return f"QbittorrentEnvironmentUpdate(keys={tuple(self._values)!r})"


@dataclass(frozen=True)
class QbittorrentResult(ServiceResult):
    """Operation result with a private, non-serialized environment update."""

    environment_update: QbittorrentEnvironmentUpdate = field(
        default_factory=QbittorrentEnvironmentUpdate,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        update = self.environment_update
        if not isinstance(update, QbittorrentEnvironmentUpdate):
            object.__setattr__(self, "environment_update", QbittorrentEnvironmentUpdate(update))

    @property
    def exit_code(self) -> int:
        return int(getattr(self.error, "exit_code", 0) or 0)

    @property
    def report(self) -> dict[str, Any]:
        report = super().report
        if self.environment_update:
            report["environment_update"] = self.environment_update.redacted
        return report

    @property
    def env_update(self) -> QbittorrentEnvironmentUpdate:
        return self.environment_update

    @property
    def password_update(self) -> QbittorrentEnvironmentUpdate:
        return self.environment_update

    def __repr__(self) -> str:
        return (
            f"QbittorrentResult(service={self.service!r}, status={self.status!r}, "
            f"actions={self.actions!r}, dry_run={self.dry_run!r})"
        )


QBittorrentResult = QbittorrentResult


def _base_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError("qBittorrent URL is required")
    candidate = value.strip().rstrip("/")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in candidate):
        raise InvalidInputError("qBittorrent URL is invalid")
    try:
        parsed = urllib.parse.urlsplit(candidate)
        _ = parsed.port
    except (TypeError, ValueError):
        raise InvalidInputError("qBittorrent URL is invalid") from None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise InvalidInputError("qBittorrent URL is invalid")
    return candidate


def _safe_mapping_value(source: Any, *keys: str) -> Any:
    if not isinstance(source, Mapping):
        return _MISSING
    for key in keys:
        if key in source:
            return source[key]
        upper = key.upper()
        if upper in source:
            return source[upper]
        lower = key.lower()
        if lower in source:
            return source[lower]
    return _MISSING


def _environment_mapping(source: Any) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    values = getattr(source, "values", None)
    if isinstance(values, Mapping):
        return dict(values)
    return {}


def _secret(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def parse_temporary_password(
    logs: str | bytes,
    *,
    max_bytes: int = DEFAULT_LOG_MAX_BYTES,
    max_lines: int = DEFAULT_LOG_MAX_LINES,
) -> str | None:
    """Extract only the documented temporary-password line within hard bounds."""

    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0:
        raise InvalidInputError("qBittorrent log byte limit is invalid")
    if not isinstance(max_lines, int) or isinstance(max_lines, bool) or max_lines < 0:
        raise InvalidInputError("qBittorrent log line limit is invalid")
    if isinstance(logs, bytes):
        stream: Any = io.BytesIO(logs)
        is_bytes = True
    elif isinstance(logs, str):
        stream = io.StringIO(logs)
        is_bytes = False
    else:
        raise InvalidInputError("qBittorrent logs must be text or bytes")

    consumed = 0
    for _ in range(max_lines):
        line = stream.readline()
        if line == b"" or line == "":
            break
        if is_bytes:
            line_size = len(line)
        else:
            try:
                line_size = len(line.encode("utf-8"))
            except UnicodeEncodeError:
                continue
        consumed += line_size
        if consumed > max_bytes:
            break
        if is_bytes:
            try:
                line = line.decode("utf-8")
            except UnicodeDecodeError:
                continue
        candidate = line.strip()
        matched = _TEMPORARY_PASSWORD_LINE.fullmatch(candidate)
        if matched is not None:
            return matched.group("password")
    return None


def temporary_password_from_logs(logs: str | bytes, **kwargs: Any) -> str | None:
    """Compatibility name for the bounded temporary-password parser."""

    return parse_temporary_password(logs, **kwargs)


def _response_status(response: Any) -> int:
    status = getattr(response, "status", None)
    if status is None and isinstance(response, Mapping):
        status = response.get("status", 200)
    if status is None:
        status = 200
    status_error: QbittorrentSchemaError | None = None
    try:
        return int(status)
    except (TypeError, ValueError):
        status_error = QbittorrentSchemaError()
    if status_error is not None:
        raise status_error from None
    raise QbittorrentSchemaError() from None


def _response_headers(response: Any) -> Mapping[str, Any]:
    headers = getattr(response, "headers", None)
    if headers is None and isinstance(response, Mapping):
        headers = response.get("headers", {})
    if headers is None:
        return {}
    if not isinstance(headers, Mapping):
        header_error: QbittorrentSchemaError | None = None
        try:
            headers = dict(headers)
        except (TypeError, ValueError):
            header_error = QbittorrentSchemaError()
        if header_error is not None:
            raise header_error from None
    return headers


def _response_body(response: Any) -> Any:
    if isinstance(response, Mapping) and not isinstance(response, HttpResponse):
        if "body" in response:
            return response["body"]
        return response
    return getattr(response, "body", _MISSING)


def _response_text(response: Any) -> str:
    payload = _response_body(response)
    if isinstance(payload, bytes):
        decode_error: QbittorrentSchemaError | None = None
        try:
            return payload.decode("utf-8").strip()
        except UnicodeDecodeError:
            decode_error = QbittorrentSchemaError()
        if decode_error is not None:
            raise decode_error from None
    if isinstance(payload, str):
        return payload.strip()
    if payload is _MISSING or payload is None:
        decoder = getattr(response, "read", None)
        if callable(decoder):
            read_error: QbittorrentTransportError | None = None
            try:
                payload = decoder()
            except Exception:
                read_error = QbittorrentTransportError()
            if read_error is not None:
                raise read_error from None
            if isinstance(payload, bytes):
                return payload.decode("utf-8", errors="replace").strip()
            if isinstance(payload, str):
                return payload.strip()
        return ""
    return str(payload).strip()


def _response_json(response: Any) -> Any:
    payload = _response_body(response)
    if isinstance(payload, Mapping):
        return payload
    if isinstance(payload, bytes):
        decode_error: QbittorrentSchemaError | None = None
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError:
            decode_error = QbittorrentSchemaError()
        if decode_error is not None:
            raise decode_error from None
    if isinstance(payload, str):
        json_error: QbittorrentSchemaError | None = None
        try:
            return json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            json_error = QbittorrentSchemaError()
        if json_error is not None:
            raise json_error from None
    decoder = getattr(response, "json", None)
    if callable(decoder):
        decoder_error: QbittorrentSchemaError | None = None
        try:
            return decoder()
        except (MalformedJsonError, UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError):
            decoder_error = QbittorrentSchemaError()
        if decoder_error is not None:
            raise decoder_error from None
    raise QbittorrentSchemaError()


def _cookie(response: Any) -> str | None:
    headers = _response_headers(response)
    value = next((value for key, value in headers.items() if str(key).lower() == "set-cookie"), None)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if not isinstance(value, str):
        return None
    candidate = value.split(";", 1)[0].strip()
    if "=" not in candidate or any(ord(char) < 0x20 or ord(char) == 0x7F for char in candidate):
        return None
    return candidate


def _invoke_prompt(prompt: Callable[..., Any]) -> Any:
    try:
        signature = inspect.signature(prompt)
    except (TypeError, ValueError):
        return prompt()
    positional = tuple(
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
    )
    if positional:
        return prompt("QBT_PASSWORD")
    return prompt()


class QbittorrentSession:
    """Authenticated in-memory session; its cookie is never rendered."""

    __slots__ = ("_cookie",)

    def __init__(self, cookie: str | None) -> None:
        self._cookie = cookie

    @property
    def headers(self) -> dict[str, str]:
        return {"Cookie": self._cookie} if self._cookie is not None else {}

    def __repr__(self) -> str:
        return "QbittorrentSession(authenticated=True)"


class QbittorrentAdapter:
    """Authenticate, adopt credentials, and reconcile qBittorrent defaults."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        transport: Any = None,
        *,
        env: Mapping[str, Any] | None = None,
        environment: Mapping[str, Any] | None = None,
        current_env: Mapping[str, Any] | None = None,
        logs: str | bytes | None = None,
        container_logs: str | bytes | None = None,
        log_max_bytes: int = DEFAULT_LOG_MAX_BYTES,
        log_max_lines: int = DEFAULT_LOG_MAX_LINES,
        password: str | None = None,
        qbt_password: str | None = None,
        current_password: str | None = None,
        selected_password: str | None = None,
        new_password: str | None = None,
        interactive_password: str | None = None,
        prompt: Callable[..., Any] | None = None,
        password_prompt: Callable[..., Any] | None = None,
        interactive: bool = True,
        username: str = USERNAME,
        admin_name: str | None = None,
        default_save_path: str = DEFAULT_SAVE_PATH,
        category_paths: Mapping[str, str] | None = None,
    ) -> None:
        if transport is None or not callable(getattr(transport, "request", None)):
            raise InvalidInputError("qBittorrent transport is required")
        chosen_username = admin_name if admin_name is not None else username
        if chosen_username != USERNAME:
            raise InvalidInputError("qBittorrent username must remain admin")
        self.base_url = _base_url(base_url)
        self._transport = transport
        merged_env: dict[str, Any] = {}
        for source in (current_env, environment, env):
            merged_env.update(_environment_mapping(source))
        self._env = merged_env
        self._explicit_qbt_password = qbt_password
        self._explicit_current_password = current_password if current_password is not None else password
        self._selected_password_value = selected_password if selected_password is not None else new_password
        self._interactive_password = interactive_password
        self._prompt = prompt if prompt is not None else password_prompt
        self._interactive = bool(interactive)
        self._prompted_password: str | None = None
        self._temporary_password = None
        provided_logs = logs if logs is not None else container_logs
        if provided_logs is not None:
            self._temporary_password = parse_temporary_password(
                provided_logs,
                max_bytes=log_max_bytes,
                max_lines=log_max_lines,
            )
        self._default_save_path = self._validated_path(default_save_path, "default save path")
        paths = {
            "sonarr": f"{self._default_save_path.rstrip('/')}/sonarr",
            "radarr": f"{self._default_save_path.rstrip('/')}/radarr",
        }
        if self._default_save_path == "/":
            paths = {"sonarr": "/sonarr", "radarr": "/radarr"}
        if category_paths is not None:
            if not isinstance(category_paths, Mapping):
                raise InvalidInputError("qBittorrent category paths must be a mapping")
            for name, path in category_paths.items():
                if name not in paths:
                    raise InvalidInputError("qBittorrent category name is unsupported")
                paths[name] = self._validated_path(path, "category path")
        self._category_paths = paths
        self._cookie_value: str | None = None

    @staticmethod
    def _validated_path(value: Any, label: str) -> str:
        if not isinstance(value, str) or not value or not value.startswith("/"):
            raise InvalidInputError(f"qBittorrent {label} is invalid")
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value) or ".." in value.split("/"):
            raise InvalidInputError(f"qBittorrent {label} is invalid")
        return posixpath.normpath(value)

    def __repr__(self) -> str:
        return "QbittorrentAdapter(configured=True)"

    @property
    def username(self) -> str:
        return USERNAME

    @property
    def session(self) -> QbittorrentSession | None:
        return QbittorrentSession(self._cookie_value) if self._cookie_value is not None else None

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Referer": f"{self.base_url}/"}
        if self._cookie_value is not None:
            headers["Cookie"] = self._cookie_value
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        form: Mapping[str, Any] | None = None,
        operation: str = "read",
    ) -> Any:
        url = self._url(path)
        kwargs: dict[str, Any] = {"headers": self._headers()}
        if form is not None:
            kwargs["form"] = form
        try:
            response = self._transport.request(method, url, **kwargs)
        except HttpStatusError as error:
            if operation == "authenticate" and error.status in {401, 403, 429}:
                raise QbittorrentAuthenticationError(error.status) from None
            raise
        except HttpTransportError:
            raise
        except TimeoutError:
            raise HttpTimeoutError(method=method, url=url) from None
        except OSError:
            raise HttpConnectionError(method=method, url=url) from None
        except Exception:
            raise QbittorrentTransportError() from None
        status = _response_status(response)
        if not 200 <= status < 300:
            if operation == "authenticate" and status in {401, 403, 429}:
                raise QbittorrentAuthenticationError(status) from None
            raise HttpStatusError(method=method, url=url, status=status)
        return response

    def _login_once(self, password: str) -> QbittorrentSession:
        self._cookie_value = None
        response = self._request(
            "POST",
            "/api/v2/auth/login",
            form={"username": USERNAME, "password": password},
            operation="authenticate",
        )
        body = _response_text(response)
        if body == "Fails.":
            raise QbittorrentAuthenticationError() from None
        if body not in {"", "Ok."}:
            raise QbittorrentAuthenticationError() from None
        self._cookie_value = _cookie(response)
        if body == "":
            self._request("GET", "/api/v2/app/version", operation="authenticate")
        return QbittorrentSession(self._cookie_value)

    def _candidate_passwords(self) -> list[str]:
        candidates: list[str] = []
        sources = (
            _safe_mapping_value(self._env, "QBT_PASSWORD"),
            self._explicit_qbt_password,
            self._temporary_password,
            self._explicit_current_password,
            _safe_mapping_value(self._env, "STACK_PASSWORD"),
            self._interactive_password,
        )
        for value in sources:
            candidate = _secret(value)
            if candidate is not None and candidate not in candidates:
                candidates.append(candidate)
        return candidates

    def _selected_password(self) -> str | None:
        explicit = _secret(self._selected_password_value)
        if explicit is not None:
            return explicit
        for value in (
            _safe_mapping_value(self._env, "QBT_PASSWORD"),
            self._explicit_qbt_password,
            self._explicit_current_password,
            _safe_mapping_value(self._env, "STACK_PASSWORD"),
            self._interactive_password,
            self._prompted_password,
            self._temporary_password,
        ):
            candidate = _secret(value)
            if candidate is not None:
                return candidate
        return None

    def _authenticate_candidates(self) -> QbittorrentSession:
        candidates = self._candidate_passwords()
        if not candidates and not (self._interactive and self._prompt is not None):
            raise QbittorrentCredentialError() from None
        last_error: QbittorrentAuthenticationError | None = None
        for candidate in candidates:
            try:
                return self._login_once(candidate)
            except QbittorrentAuthenticationError as error:
                last_error = error
        if self._interactive and self._prompt is not None:
            try:
                prompted = _invoke_prompt(self._prompt)
            except Exception:
                raise QbittorrentCredentialError() from None
            candidate = _secret(prompted)
            self._prompted_password = candidate
            if candidate is not None and candidate not in candidates:
                try:
                    return self._login_once(candidate)
                except QbittorrentAuthenticationError as error:
                    last_error = error
        if last_error is not None:
            raise last_error from None
        raise QbittorrentCredentialError() from None

    def authenticate(self, password: str | None = None) -> QbittorrentSession:
        """Authenticate with an explicit password or the documented source order."""

        if password is not None:
            candidate = _secret(password)
            if candidate is None:
                raise InvalidInputError("qBittorrent password is required")
            return self._login_once(candidate)
        return self._authenticate_candidates()

    @staticmethod
    def _preferences(payload: Any) -> Mapping[str, Any]:
        if not isinstance(payload, Mapping):
            raise QbittorrentSchemaError() from None
        return payload

    @staticmethod
    def _categories(payload: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(payload, Mapping):
            raise QbittorrentSchemaError() from None
        categories: dict[str, dict[str, Any]] = {}
        for name, value in payload.items():
            if not isinstance(name, str) or not isinstance(value, Mapping):
                raise QbittorrentSchemaError() from None
            categories[name] = dict(value)
        return categories

    def _category_path(self, category: Mapping[str, Any]) -> str | None:
        value = category.get("savePath", _MISSING)
        if value is _MISSING:
            value = category.get("save_path", _MISSING)
        return value if isinstance(value, str) else None

    def _embedded_category_changes(self, payload: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], bool]:
        categories = self._categories(payload.get("categories", {}))
        changed = False
        for name, target in self._category_paths.items():
            current = categories.get(name)
            if current is None:
                current = {}
                categories[name] = current
                changed = True
            if self._category_path(current) != target:
                current["save_path"] = target
                changed = True
        return categories, changed

    def _preference_changes(self, preferences: Mapping[str, Any], password: str) -> tuple[dict[str, Any], bool]:
        changes: dict[str, Any] = {"web_ui_password": password}
        current_path = preferences.get("save_path", _MISSING)
        if current_path is not _MISSING and current_path is not None and not isinstance(current_path, str):
            raise QbittorrentSchemaError() from None
        if current_path != self._default_save_path:
            changes["save_path"] = self._default_save_path
        if "categories" in preferences:
            categories, changed = self._embedded_category_changes(preferences)
            if changed:
                changes["categories"] = categories
        return changes, "categories" in changes

    def _reconcile_categories(self, payload: Any) -> list[str]:
        categories = self._categories(payload)
        actions: list[str] = []
        for name, target in self._category_paths.items():
            current = categories.get(name)
            if current is None:
                self._request(
                    "POST",
                    "/api/v2/torrents/createCategory",
                    form={"category": name, "savePath": target},
                    operation="mutation",
                )
                actions.append(f"create-category:{name}")
                continue
            if self._category_path(current) != target:
                self._request(
                    "POST",
                    "/api/v2/torrents/editCategory",
                    form={"category": name, "savePath": target},
                    operation="mutation",
                )
                actions.append(f"reconcile-category:{name}")
        return actions

    def plan(
        self,
        *,
        adopt: bool | None = None,
        fresh: bool | None = None,
        dry_run: bool = False,
    ) -> ServicePlan:
        if adopt is not None and fresh is not None and bool(adopt) == bool(fresh):
            raise InvalidInputError("qBittorrent setup mode is conflicting")
        mode = "fresh" if fresh else "adopted" if adopt else None
        return ServicePlan(
            service=SERVICE_NAME,
            actions=("authenticate", "set-password", "verify-password", "reconcile-categories"),
            dry_run=bool(dry_run),
            mode=mode,
        )

    def _guided(
        self,
        *,
        code: str,
        reason: str,
        error: QbittorrentError,
        actions: list[str],
    ) -> QbittorrentResult:
        return QbittorrentResult(
            service=SERVICE_NAME,
            status="guided",
            actions=tuple(actions),
            checkpoints=(
                ServiceCheckpoint(
                    code=code,
                    reason=reason,
                    action="authenticate",
                    severity="error",
                ),
            ),
            error=error,
        )

    def apply(self, plan: ServicePlan, *, dry_run: bool | None = None) -> QbittorrentResult:
        if not isinstance(plan, ServicePlan) or plan.service != SERVICE_NAME:
            raise InvalidInputError("qBittorrent plan is invalid")
        selected_dry_run = plan.dry_run if dry_run is None else bool(dry_run)
        if selected_dry_run:
            return QbittorrentResult(
                service=SERVICE_NAME,
                status="dry-run",
                actions=plan.actions,
                dry_run=True,
                mode=plan.mode,
            )

        actions: list[str] = []
        try:
            self._authenticate_candidates()
            actions.append("authenticate")
        except QbittorrentCredentialError as error:
            return self._guided(
                code="qbittorrent-credentials",
                reason="Provide QBT_PASSWORD or explicitly choose the qBittorrent credential recovery step.",
                error=error,
                actions=actions,
            )
        except QbittorrentAuthenticationError as error:
            return self._guided(
                code="qbittorrent-authentication",
                reason="Verify the current qBittorrent credentials and retry after any WebUI ban expires.",
                error=error,
                actions=actions,
            )

        selected = self._selected_password()
        if selected is None:
            error = QbittorrentCredentialError()
            return self._guided(
                code="qbittorrent-credentials",
                reason="Select a verified password before changing qBittorrent credentials.",
                error=error,
                actions=actions,
            )

        preferences = self._preferences(
            _response_json(self._request("GET", "/api/v2/app/preferences"))
        )
        changes, embedded_category_change = self._preference_changes(preferences, selected)
        category_actions: list[str] = []
        category_payload: Any = None
        if "categories" not in preferences:
            category_payload = _response_json(
                self._request("GET", "/api/v2/torrents/categories")
            )
        self._request(
            "POST",
            "/api/v2/app/setPreferences",
            form={"json": json.dumps(changes, ensure_ascii=False, separators=(",", ":"))},
            operation="mutation",
        )
        actions.append("set-password")
        if category_payload is not None:
            category_actions = self._reconcile_categories(category_payload)
        if embedded_category_change or category_actions:
            actions.append("reconcile-categories")

        self._cookie_value = None
        try:
            self._login_once(selected)
        except QbittorrentAuthenticationError as error:
            verification_error = QbittorrentPasswordVerificationError(error.status)
            return self._guided(
                code="qbittorrent-password-verification",
                reason="The selected password was not verified; retain the existing credential and retry.",
                error=verification_error,
                actions=actions,
            )
        actions.append("verify-password")
        return QbittorrentResult(
            service=SERVICE_NAME,
            status="ok",
            actions=tuple(actions),
            mode=plan.mode,
            environment_update=QbittorrentEnvironmentUpdate(
                {"QBT_PASSWORD": selected, "STACK_PASSWORD": selected}
            ),
        )

    def configure(
        self,
        *,
        adopt: bool | None = None,
        fresh: bool | None = None,
        dry_run: bool = False,
    ) -> QbittorrentResult:
        return self.apply(self.plan(adopt=adopt, fresh=fresh, dry_run=dry_run))


QBittorrentAdapter = QbittorrentAdapter


def plan_qbittorrent(
    base_url: str = DEFAULT_BASE_URL,
    transport: Any = None,
    **kwargs: Any,
) -> ServicePlan:
    adopt = kwargs.pop("adopt", None)
    fresh = kwargs.pop("fresh", None)
    dry_run = kwargs.pop("dry_run", False)
    return QbittorrentAdapter(base_url, transport, **kwargs).plan(
        adopt=adopt,
        fresh=fresh,
        dry_run=dry_run,
    )


def configure_qbittorrent(
    base_url: str = DEFAULT_BASE_URL,
    transport: Any = None,
    **kwargs: Any,
) -> QbittorrentResult:
    adopt = kwargs.pop("adopt", None)
    fresh = kwargs.pop("fresh", None)
    dry_run = kwargs.pop("dry_run", False)
    return QbittorrentAdapter(base_url, transport, **kwargs).configure(
        adopt=adopt,
        fresh=fresh,
        dry_run=dry_run,
    )


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_LOG_MAX_BYTES",
    "DEFAULT_LOG_MAX_LINES",
    "DEFAULT_SAVE_PATH",
    "QBittorrentAdapter",
    "QBittorrentAuthenticationError",
    "QBittorrentCredentialError",
    "QBittorrentError",
    "QBittorrentPasswordVerificationError",
    "QBittorrentResult",
    "QBittorrentSchemaError",
    "QbittorrentAdapter",
    "QbittorrentAuthError",
    "QbittorrentAuthenticationError",
    "QbittorrentCredentialError",
    "QbittorrentEnvironmentUpdate",
    "QbittorrentError",
    "QbittorrentPasswordVerificationError",
    "QbittorrentResult",
    "QbittorrentSchemaError",
    "QbittorrentSession",
    "configure_qbittorrent",
    "parse_temporary_password",
    "plan_qbittorrent",
    "temporary_password_from_logs",
]
