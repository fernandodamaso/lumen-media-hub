"""Safe Jellyfin startup and administrator authentication adapter.

This slice owns only the public startup capability check and authentication.
It deliberately does not inspect or reconcile libraries, plugins, networking,
encoding, or API keys.  Credentials and response identities remain private to
the adapter/session and never enter plans, results, reports, or errors.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..errors import InstallerError, InvalidInputError, PartialError
from ..http import (
    HttpConnectionError,
    HttpResponse,
    HttpStatusError,
    HttpTimeoutError,
    MalformedJsonError,
)
from .base import ServiceCheckpoint, ServicePlan, ServiceResult


SERVICE_NAME = "jellyfin"
_STARTUP_FIELDS = frozenset(
    {"ServerName", "UICulture", "MetadataCountryCode", "PreferredMetadataLanguage"}
)
_STARTUP_ACTIONS = frozenset(
    {"configure-startup", "create-administrator", "complete-startup"}
)
class JellyfinError(InstallerError):
    """Base class for sanitized Jellyfin adapter failures."""

    code = "jellyfin-error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        self.code = code or self.code
        super().__init__(message)


class JellyfinCapabilityError(InvalidInputError, JellyfinError):
    """Jellyfin does not expose a supported, validated startup contract."""

    code = "jellyfin-capability"

    def __init__(self, message: str = "Jellyfin startup capability is unsupported") -> None:
        self.code = type(self).code
        # Keep this text fixed: endpoint response data is never included.
        InvalidInputError.__init__(self, message)


class JellyfinSchemaError(JellyfinCapabilityError):
    """A startup or authentication response is malformed."""

    code = "jellyfin-schema"

    def __init__(self, message: str = "Jellyfin response schema is unsupported") -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, message)


class JellyfinAuthenticationError(PartialError, JellyfinError):
    """Credentials were refused; the caller receives a guided handoff."""

    code = "jellyfin-authentication"

    def __init__(self, status: int | None = None) -> None:
        self.status = status
        self.status_code = status
        self.code = type(self).code
        PartialError.__init__(
            self,
            "Jellyfin authentication was refused; verify the current administrator credentials",
        )


JellyfinAuthError = JellyfinAuthenticationError


@dataclass(frozen=True)
class JellyfinCapability:
    """Validated non-sensitive capability facts used by planning."""

    initialized: bool
    version: str | None = None

    @property
    def startup_completed(self) -> bool:
        return self.initialized


class JellyfinSession:
    """In-memory authenticated session; its token is never rendered."""

    __slots__ = ("_token", "_user_id")

    def __init__(self, token: str, user_id: str | None = None) -> None:
        self._token = token
        self._user_id = user_id

    @property
    def token(self) -> str:
        """Return the private token for adapter-owned follow-up requests."""

        return self._token

    @property
    def user_id(self) -> str | None:
        """Return the private user identity for adapter-owned follow-up work."""

        return self._user_id

    @property
    def authorization(self) -> str:
        return (
            f"MediaBrowser Token={_quote_header_value(self._token)}, "
            f"Client={_quote_header_value('Lumen Installer')}, "
            f"Device={_quote_header_value('installer')}, "
            f"DeviceId={_quote_header_value('lumen-installer')}, "
            f"Version={_quote_header_value('1.0')}"
        )

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": self.authorization}

    def __repr__(self) -> str:
        return "JellyfinSession(authenticated=True)"


class JellyfinResult(ServiceResult):
    """Jellyfin-specific result alias with secret-free inherited reporting."""


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _base_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError("Jellyfin URL is required")
    candidate = value.strip().rstrip("/")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in candidate):
        raise InvalidInputError("Jellyfin URL is invalid")
    try:
        parsed = urllib.parse.urlsplit(candidate)
        _ = parsed.port
    except (TypeError, ValueError):
        raise InvalidInputError("Jellyfin URL is invalid") from None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise InvalidInputError("Jellyfin URL is invalid")
    if parsed.username is not None or parsed.password is not None:
        raise InvalidInputError("Jellyfin URL is invalid")
    return candidate


def _safe_public_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value) if _nonempty_text(value) else None


def _quote_header_value(value: str) -> str:
    """Quote a MediaBrowser header value without allowing escapes through."""

    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class JellyfinAdapter:
    """Plan and apply supported Jellyfin startup/authentication operations."""

    def __init__(
        self,
        base_url: str,
        transport: Any,
        *,
        admin_name: str | None = None,
        admin_password: str | None = None,
        username: str | None = None,
        password: str | None = None,
        server_name: str = "Lumen Media Hub",
        interactive: bool = True,
    ) -> None:
        if transport is None or not callable(getattr(transport, "request", None)):
            raise InvalidInputError("Jellyfin transport is required")
        self.base_url = _base_url(base_url)
        self._transport = transport
        self._admin_name = admin_name if admin_name is not None else username
        self._admin_password = admin_password if admin_password is not None else password
        self._server_name = server_name
        self._interactive = bool(interactive)
        self._session: JellyfinSession | None = None
        self._capability: JellyfinCapability | None = None
        self._startup_configuration: dict[str, str] | None = None

    @property
    def session(self) -> JellyfinSession | None:
        return self._session

    @property
    def capability(self) -> JellyfinCapability | None:
        return self._capability

    def __repr__(self) -> str:
        return "JellyfinAdapter(configured=True)"

    def _validate_credentials(self) -> None:
        missing = not _nonempty_text(self._admin_name) or not _nonempty_text(self._admin_password)
        if missing:
            # Interactive prompting is intentionally owned by the later CLI
            # orchestration layer; never begin an HTTP mutation with missing
            # decisions in this adapter.
            raise InvalidInputError("Jellyfin administrator credentials are required")
        if not isinstance(self._server_name, str) or not self._server_name.strip():
            raise InvalidInputError("Jellyfin server name is required")

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _headers(self, *, authenticated: bool = False) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if authenticated and self._session is not None:
            headers.update(self._session.headers)
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        authenticated: bool = False,
        operation: str = "read",
    ) -> Any:
        url = self._url(path)
        kwargs: dict[str, Any] = {"headers": self._headers(authenticated=authenticated)}
        if body is not None:
            kwargs["json_body"] = body
        try:
            response = self._transport.request(method, url, **kwargs)
        except HttpStatusError as error:
            if operation == "authenticate" and error.status in {401, 403}:
                raise JellyfinAuthenticationError(error.status) from None
            raise
        except TimeoutError:
            raise HttpTimeoutError(method=method, url=url) from None
        except OSError:
            raise HttpConnectionError(method=method, url=url) from None
        status = getattr(response, "status", 200)
        try:
            status = int(status)
        except (TypeError, ValueError):
            raise JellyfinSchemaError() from None
        if not 200 <= status < 300:
            if operation == "authenticate" and status in {401, 403}:
                raise JellyfinAuthenticationError(status) from None
            raise HttpStatusError(method=method, url=url, status=status)
        return response

    @staticmethod
    def _decode_json(response: Any, *, operation: str) -> Any:
        if isinstance(response, Mapping) and not isinstance(response, HttpResponse):
            # Lightweight deterministic transports may return an already
            # decoded payload.  A mapping with a body key is treated as a raw
            # response only when that is the sole explicit response value.
            if "body" not in response:
                return response
            raw = response.get("body")
            if isinstance(raw, (bytes, str)):
                decode_error: JellyfinSchemaError | None = None
                try:
                    return json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                    decode_error = JellyfinSchemaError()
                if decode_error is not None:
                    raise decode_error from None
        decoder = getattr(response, "json", None)
        if callable(decoder):
            decode_error = None
            try:
                return decoder()
            except (MalformedJsonError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                decode_error = JellyfinSchemaError()
            if decode_error is not None:
                raise decode_error from None
        body = getattr(response, "body", None)
        if isinstance(body, (bytes, str)):
            decode_error = None
            try:
                return json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                decode_error = JellyfinSchemaError()
            if decode_error is not None:
                raise decode_error from None
        raise JellyfinSchemaError()

    @classmethod
    def _system_capability(cls, payload: Any) -> JellyfinCapability:
        if not isinstance(payload, Mapping):
            raise JellyfinCapabilityError()
        completed = payload.get("StartupWizardCompleted")
        if not isinstance(completed, bool):
            raise JellyfinCapabilityError()
        version = payload.get("Version")
        if version is not None and not _nonempty_text(version):
            raise JellyfinCapabilityError()
        return JellyfinCapability(completed, _safe_public_text(version))

    @classmethod
    def _startup_capability(cls, payload: Any) -> dict[str, str]:
        if not isinstance(payload, Mapping):
            raise JellyfinCapabilityError()
        values: dict[str, str] = {}
        for field in _STARTUP_FIELDS:
            value = payload.get(field)
            if value is not None and not isinstance(value, str):
                raise JellyfinCapabilityError()
            values[field] = value or ""
        return values

    @staticmethod
    def _startup_user_capability(payload: Any) -> None:
        if not isinstance(payload, Mapping) or not _nonempty_text(payload.get("Name")):
            raise JellyfinCapabilityError()

    def _check_capability(self) -> JellyfinCapability:
        system = self._decode_json(
            self._request("GET", "/System/Info/Public"),
            operation="system",
        )
        capability = self._system_capability(system)
        self._startup_configuration = None
        if not capability.initialized:
            self._startup_configuration = self._startup_capability(
                self._decode_json(
                    self._request("GET", "/Startup/Configuration"),
                    operation="startup",
                )
            )
        self._capability = capability
        return capability

    def plan(
        self,
        *,
        adopt: bool | None = None,
        fresh: bool | None = None,
        dry_run: bool = False,
    ) -> ServicePlan:
        self._validate_credentials()
        if adopt is not None and fresh is not None and bool(adopt) == bool(fresh):
            raise InvalidInputError("Jellyfin startup mode is conflicting")
        capability = self._check_capability()
        wants_fresh = not capability.initialized if fresh is None and adopt is None else bool(fresh)
        if adopt:
            wants_fresh = False
        if capability.initialized:
            wants_fresh = False
        actions = (
            ("configure-startup", "create-administrator", "complete-startup", "authenticate")
            if wants_fresh
            else ("authenticate",)
        )
        return ServicePlan(
            service=SERVICE_NAME,
            status="planned",
            actions=actions,
            dry_run=bool(dry_run),
            mode="fresh" if wants_fresh else "adopted",
        )

    def _authenticate(self) -> JellyfinSession:
        self._validate_credentials()
        payload = {"Username": self._admin_name, "Pw": self._admin_password}
        response = self._request(
            "POST",
            "/Users/AuthenticateByName",
            body=payload,
            operation="authenticate",
        )
        auth = self._decode_json(response, operation="authenticate")
        if not isinstance(auth, Mapping) or not _nonempty_text(auth.get("AccessToken")):
            raise JellyfinSchemaError("Jellyfin authentication response is unsupported")
        token = str(auth["AccessToken"])
        user = auth.get("User")
        user_id = user.get("Id") if isinstance(user, Mapping) and _nonempty_text(user.get("Id")) else None
        self._session = JellyfinSession(token, user_id)
        return self._session

    def authenticate(self) -> JellyfinSession:
        """Authenticate directly using current credentials.

        Normal configure flows call :meth:`plan` first.  This direct helper is
        useful to later adapters after startup and does not mutate config.
        """

        return self._authenticate()

    def apply(self, plan: ServicePlan, *, dry_run: bool | None = None) -> JellyfinResult:
        if not isinstance(plan, ServicePlan) or plan.service != SERVICE_NAME:
            raise InvalidInputError("Jellyfin plan is invalid")
        # ``apply`` is public and may receive a plan not produced by this
        # adapter.  Validate decisions before any mutation, then bind an
        # unbound plan to a fresh capability check.  An already initialized
        # server must never receive startup actions from a stale/foreign plan.
        self._validate_credentials()
        selected_dry_run = plan.dry_run if dry_run is None else bool(dry_run)
        if selected_dry_run:
            return JellyfinResult(
                service=SERVICE_NAME,
                status="dry-run",
                actions=plan.actions,
                drift=plan.drift,
                checkpoints=plan.checkpoints,
                dry_run=True,
                mode=plan.mode,
            )

        actions = plan.actions
        mode = plan.mode
        if _STARTUP_ACTIONS.intersection(actions):
            capability = self._check_capability()
            if capability.initialized:
                actions = tuple(action for action in actions if action not in _STARTUP_ACTIONS)
                mode = "adopted"

        completed: list[str] = []
        try:
            if "configure-startup" in actions:
                startup_configuration = dict(self._startup_configuration or {})
                startup_configuration["ServerName"] = self._server_name
                for field in _STARTUP_FIELDS:
                    startup_configuration.setdefault(field, "")
                self._request(
                    "POST",
                    "/Startup/Configuration",
                    body=startup_configuration,
                    operation="mutation",
                )
                completed.append("configure-startup")
            if "create-administrator" in actions:
                initial_user = self._decode_json(
                    self._request("GET", "/Startup/User", operation="startup"),
                    operation="startup",
                )
                self._startup_user_capability(initial_user)
                self._request(
                    "POST",
                    "/Startup/User",
                    body={"Name": self._admin_name, "Password": self._admin_password},
                    operation="mutation",
                )
                completed.append("create-administrator")
            if "complete-startup" in actions:
                self._request("POST", "/Startup/Complete", operation="mutation")
                completed.append("complete-startup")
            if "authenticate" in actions:
                self._authenticate()
                completed.append("authenticate")
        except JellyfinAuthenticationError as error:
            checkpoint = ServiceCheckpoint(
                code="jellyfin-authentication",
                reason="Verify the current Jellyfin administrator credentials and retry.",
                action="authenticate",
                severity="error",
            )
            return JellyfinResult(
                service=SERVICE_NAME,
                status="guided",
                actions=tuple(completed),
                checkpoints=(checkpoint,),
                dry_run=False,
                error=error,
                mode=mode,
            )
        return JellyfinResult(
            service=SERVICE_NAME,
            status="ok",
            actions=tuple(completed),
            dry_run=False,
            mode=mode,
        )

    def configure(
        self,
        *,
        adopt: bool | None = None,
        fresh: bool | None = None,
        dry_run: bool = False,
    ) -> JellyfinResult:
        plan = self.plan(adopt=adopt, fresh=fresh, dry_run=dry_run)
        return self.apply(plan)


def plan_jellyfin(
    base_url: str,
    transport: Any,
    *,
    admin_name: str | None = None,
    admin_password: str | None = None,
    username: str | None = None,
    password: str | None = None,
    server_name: str = "Lumen Media Hub",
    adopt: bool | None = None,
    fresh: bool | None = None,
    dry_run: bool = False,
    interactive: bool = True,
) -> ServicePlan:
    return JellyfinAdapter(
        base_url,
        transport,
        admin_name=admin_name,
        admin_password=admin_password,
        username=username,
        password=password,
        server_name=server_name,
        interactive=interactive,
    ).plan(adopt=adopt, fresh=fresh, dry_run=dry_run)


def configure_jellyfin(
    base_url: str,
    transport: Any,
    *,
    admin_name: str | None = None,
    admin_password: str | None = None,
    username: str | None = None,
    password: str | None = None,
    server_name: str = "Lumen Media Hub",
    adopt: bool | None = None,
    fresh: bool | None = None,
    dry_run: bool = False,
    interactive: bool = True,
) -> JellyfinResult:
    return JellyfinAdapter(
        base_url,
        transport,
        admin_name=admin_name,
        admin_password=admin_password,
        username=username,
        password=password,
        server_name=server_name,
        interactive=interactive,
    ).configure(adopt=adopt, fresh=fresh, dry_run=dry_run)


__all__ = [
    "JellyfinAdapter",
    "JellyfinAuthError",
    "JellyfinAuthenticationError",
    "JellyfinCapability",
    "JellyfinCapabilityError",
    "JellyfinError",
    "JellyfinResult",
    "JellyfinSchemaError",
    "JellyfinSession",
    "configure_jellyfin",
    "plan_jellyfin",
]
