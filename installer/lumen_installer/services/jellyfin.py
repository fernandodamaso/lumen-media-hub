"""Safe Jellyfin startup, authentication, and API-key adapter.

This slice owns the public startup capability check, authentication, the
single named API key needed by ``homepage-actions``, and the two approved
managed libraries.  It deliberately does not reconcile plugins, networking,
or encoding.  Credentials and response identities remain private to the
adapter/session and never enter plans, results, reports, or errors.
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
    HttpTransportError,
)
from .base import ServiceCheckpoint, ServiceDrift, ServicePlan, ServiceResult


SERVICE_NAME = "jellyfin"
_STARTUP_FIELDS = frozenset(
    {"ServerName", "UICulture", "MetadataCountryCode", "PreferredMetadataLanguage"}
)
_STARTUP_ACTIONS = frozenset(
    {"configure-startup", "create-administrator", "complete-startup"}
)
_MANAGED_LIBRARIES = (
    ("Movies", "movies", "/data/media/movies"),
    ("Shows", "tvshows", "/data/media/tv"),
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


class JellyfinSessionError(PartialError, JellyfinError):
    """An authenticated Jellyfin session is required for admin operations."""

    code = "jellyfin-session"

    def __init__(self) -> None:
        self.code = type(self).code
        PartialError.__init__(self, "Jellyfin authenticated session is required; authenticate and retry")


class JellyfinApiKeySchemaError(JellyfinCapabilityError):
    """The runtime API-key endpoint does not match its supported contract."""

    code = "jellyfin-api-key-schema"

    def __init__(self) -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, "Jellyfin API-key response schema is unsupported")


class JellyfinLibrarySchemaError(JellyfinCapabilityError):
    """The runtime virtual-folder endpoint does not match its contract."""

    code = "jellyfin-library-schema"

    def __init__(self) -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, "Jellyfin library response schema is unsupported")


class JellyfinApiKeyHandoff:
    """Private in-memory handoff for the selected key.

    The key can only be obtained by an explicit :meth:`consume` call.  All
    ordinary object and report surfaces intentionally describe availability,
    never the secret itself.
    """

    __slots__ = ("_value",)
    env_key_name = "JELLYFIN_API_KEY"

    def __init__(self, value: str) -> None:
        if not _nonempty_text(value):
            raise ValueError("Jellyfin API key handoff requires a value")
        self._value = value

    def consume(self) -> str:
        """Explicitly release the private value to the next orchestrator."""

        return self._value

    @property
    def report(self) -> dict[str, object]:
        return {"env_key_name": self.env_key_name, "available": True}

    def __repr__(self) -> str:
        return "JellyfinApiKeyHandoff(available=True)"

    def __str__(self) -> str:
        return "Jellyfin API key handoff (available)"

    def __eq__(self, other: object) -> bool:
        # Equality is intentionally identity-only.  A value comparison would
        # turn this wrapper into a secret equality oracle for callers that can
        # guess candidate keys, while the handoff's only value-bearing
        # operation is the explicit ``consume`` call owned by Task 13.
        return self is other

    __hash__ = None


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


def _detach_exception(error: BaseException) -> BaseException:
    """Drop foreign exception links before exposing a typed service error."""

    # Exceptions raised by an injected transport can already carry a cause or
    # context.  Exception links are mutable, and clearing them here prevents a
    # caller from reaching raw response/credential detail through the typed
    # error even when the injected boundary was careless.
    try:
        error.__cause__ = None
        error.__context__ = None
        error.__suppress_context__ = True
    except Exception:
        # Built-in exception objects permit these assignments; retain the
        # typed object if a custom exception does not.
        pass
    return error


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _safe_mapping_value(mapping: Mapping[str, Any], key: str) -> Any:
    """Read injected response mappings without retaining foreign exceptions."""

    mapping_error: JellyfinApiKeySchemaError | None = None
    try:
        value = mapping.get(key)
    except Exception:
        mapping_error = JellyfinApiKeySchemaError()
    if mapping_error is not None:
        raise mapping_error from None
    return value


def _safe_library_mapping_value(mapping: Mapping[str, Any], key: str) -> Any:
    """Read library response mappings without retaining foreign exceptions."""

    mapping_error: JellyfinLibrarySchemaError | None = None
    try:
        value = mapping.get(key)
    except Exception:
        mapping_error = JellyfinLibrarySchemaError()
    if mapping_error is not None:
        raise mapping_error from None
    return value


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
    """Plan and apply supported Jellyfin startup, auth, and library operations."""

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
        self._api_key_handoff: JellyfinApiKeyHandoff | None = None

    @property
    def session(self) -> JellyfinSession | None:
        return self._session

    @property
    def capability(self) -> JellyfinCapability | None:
        return self._capability

    @property
    def api_key_handoff(self) -> JellyfinApiKeyHandoff | None:
        """Return the redacted private handoff for the selected API key."""

        return self._api_key_handoff

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
        request_error: BaseException | None = None
        try:
            response = self._transport.request(method, url, **kwargs)
        except HttpStatusError as error:
            if operation == "authenticate" and error.status in {401, 403}:
                request_error = JellyfinAuthenticationError(error.status)
            else:
                request_error = _detach_exception(error)
        except HttpTransportError as error:
            # The standard transport already reduces response/request detail;
            # removing any injected cause here keeps this adapter boundary
            # equally safe for deterministic transports.
            request_error = _detach_exception(error)
        except TimeoutError:
            request_error = HttpTimeoutError(method=method, url=url)
        except OSError:
            request_error = HttpConnectionError(method=method, url=url)
        except Exception:
            # An injected transport is an external boundary.  Do not retain
            # arbitrary exception text, which may contain a response body,
            # token, or service identity.
            request_error = HttpConnectionError(method=method, url=url)
        if request_error is not None:
            # Raise after leaving the catch block so ``__context__`` cannot
            # retain an arbitrary injected exception alongside the sanitized
            # typed failure.
            raise request_error from None
        response_error: JellyfinSchemaError | None = None
        try:
            status = getattr(response, "status", 200)
            status = int(status)
        except Exception:
            response_error = JellyfinSchemaError()
        if response_error is not None:
            raise response_error from None
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
            mapping_error: JellyfinSchemaError | None = None
            try:
                if "body" not in response:
                    return response
                raw = response.get("body")
            except Exception:
                mapping_error = JellyfinSchemaError()
            if mapping_error is not None:
                raise mapping_error from None
            if isinstance(raw, (bytes, str)):
                decode_error: JellyfinSchemaError | None = None
                try:
                    return json.loads(raw)
                except Exception:
                    decode_error = JellyfinSchemaError()
                if decode_error is not None:
                    raise decode_error from None
        decoder_error: JellyfinSchemaError | None = None
        try:
            decoder = getattr(response, "json", None)
        except Exception:
            decoder = None
            decoder_error = JellyfinSchemaError()
        if decoder_error is not None:
            raise decoder_error from None
        if callable(decoder):
            decode_error = None
            try:
                return decoder()
            except Exception:
                decode_error = JellyfinSchemaError()
            if decode_error is not None:
                raise decode_error from None
        body_error: JellyfinSchemaError | None = None
        try:
            body = getattr(response, "body", None)
        except Exception:
            body = None
            body_error = JellyfinSchemaError()
        if body_error is not None:
            raise body_error from None
        if isinstance(body, (bytes, str)):
            decode_error = None
            try:
                return json.loads(body)
            except Exception:
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

    @staticmethod
    def _library_items(payload: Any) -> list[Mapping[str, Any]]:
        if not isinstance(payload, list):
            raise JellyfinLibrarySchemaError()
        items: list[Mapping[str, Any]] = []
        for item in payload:
            if not isinstance(item, Mapping):
                raise JellyfinLibrarySchemaError()
            name = _safe_library_mapping_value(item, "Name")
            collection_type = _safe_library_mapping_value(item, "CollectionType")
            locations = _safe_library_mapping_value(item, "Locations")
            if not _nonempty_text(name) or not _nonempty_text(collection_type):
                raise JellyfinLibrarySchemaError()
            if not isinstance(locations, list) or any(
                not _nonempty_text(location) for location in locations
            ):
                raise JellyfinLibrarySchemaError()
            items.append(
                {
                    "Name": name,
                    "CollectionType": collection_type,
                    "Locations": tuple(locations),
                }
            )
        return items

    def _read_libraries(self) -> list[Mapping[str, Any]]:
        if self._session is None:
            raise JellyfinSessionError()
        return self._library_items(
            self._decode_json(
                self._request(
                    "GET",
                    "/Library/VirtualFolders",
                    authenticated=True,
                    operation="libraries",
                ),
                operation="libraries",
            )
        )

    def plan_libraries(self, *, dry_run: bool = False) -> ServicePlan:
        """Inventory and plan only the two approved managed libraries."""

        items = self._read_libraries()
        actions: list[str] = []
        drifts: list[ServiceDrift] = []
        checkpoints: list[ServiceCheckpoint] = []
        for name, collection_type, path in _MANAGED_LIBRARIES:
            matches = [
                item
                for item in items
                if item["Name"].strip().casefold() == name.casefold()
            ]
            slug = name.casefold()
            if not matches:
                actions.append(f"create-library-{slug}")
                continue
            if len(matches) > 1:
                actions.append(f"review-library-{slug}")
                checkpoints.append(
                    ServiceCheckpoint(
                        code="jellyfin-library-conflict",
                        reason="Multiple managed Jellyfin libraries match; resolve the duplicate manually and retry.",
                        action="review",
                        severity="error",
                    )
                )
                continue
            if (
                matches[0]["Name"] == name
                and matches[0]["CollectionType"] == collection_type
                and matches[0]["Locations"] == (path,)
            ):
                actions.append(f"adopt-library-{slug}")
                continue
            actions.append(f"review-library-{slug}")
            drifts.append(
                ServiceDrift(
                    resource=name,
                    field="definition",
                    reason="Managed Jellyfin library differs from the approved definition.",
                    action="confirm",
                )
            )
            checkpoints.append(
                ServiceCheckpoint(
                    code="jellyfin-library-drift",
                    reason="A managed Jellyfin library differs from the approved definition; confirm explicitly before changing it.",
                    action="confirm",
                    severity="error",
                )
            )
        plan = ServicePlan(
            service=SERVICE_NAME,
            status="conflict" if checkpoints else "planned",
            actions=tuple(actions),
            drift=tuple(drifts),
            checkpoints=tuple(checkpoints),
            dry_run=bool(dry_run),
            mode="libraries",
        )
        return plan

    @staticmethod
    def _library_create_url(name: str, collection_type: str, path: str) -> str:
        query = urllib.parse.urlencode(
            {
                "name": name,
                "collectionType": collection_type,
                "paths": path,
            }
        )
        return f"/Library/VirtualFolders?{query}"

    @staticmethod
    def _library_definition(action: str) -> tuple[str, str, str] | None:
        for name, collection_type, path in _MANAGED_LIBRARIES:
            action_name = action.removeprefix("create-library-").removeprefix("adopt-library-")
            if action_name == name.casefold():
                return name, collection_type, path
        return None

    def _library_guided(
        self,
        *,
        actions: tuple[str, ...],
        code: str,
        reason: str,
        drift: tuple[ServiceDrift, ...] = (),
        error: BaseException | None = None,
        checkpoint_action: str = "review",
    ) -> JellyfinResult:
        return JellyfinResult(
            service=SERVICE_NAME,
            status="guided",
            actions=actions,
            drift=drift,
            checkpoints=(
                ServiceCheckpoint(
                    code=code,
                    reason=reason,
                    action=checkpoint_action,
                    severity="error",
                ),
            ),
            error=error,
            mode="libraries",
        )

    def apply_libraries(
        self,
        plan: ServicePlan,
        *,
        confirm_drift: bool = False,
        dry_run: bool | None = None,
        _inventory_checked: bool = False,
    ) -> JellyfinResult:
        if not isinstance(plan, ServicePlan) or plan.service != SERVICE_NAME or plan.mode != "libraries":
            raise InvalidInputError("Jellyfin library plan is invalid")
        if self._session is None:
            raise JellyfinSessionError()
        selected_dry_run = plan.dry_run if dry_run is None else bool(dry_run)
        if not _inventory_checked:
            plan = self.plan_libraries(dry_run=selected_dry_run)
        if selected_dry_run:
            return JellyfinResult(
                service=SERVICE_NAME,
                status="dry-run",
                actions=plan.actions,
                drift=plan.drift,
                checkpoints=plan.checkpoints,
                dry_run=True,
                mode="libraries",
            )

        if plan.checkpoints and not plan.drift:
            return JellyfinResult(
                service=SERVICE_NAME,
                status="guided",
                actions=(),
                checkpoints=plan.checkpoints,
                mode="libraries",
            )

        if plan.drift:
            reason = (
                "A managed Jellyfin library differs from the approved definition; "
                "confirm explicitly before changing it."
            )
            if confirm_drift and self._interactive:
                reason = (
                    "Managed Jellyfin library drift was confirmed, but this slice "
                    "does not modify existing library definitions; resolve it manually."
                )
            return self._library_guided(
                actions=(),
                code="jellyfin-library-drift",
                reason=reason,
                drift=plan.drift,
                checkpoint_action="confirm",
            )

        completed: list[str] = []
        created: list[str] = []
        for action in plan.actions:
            definition = self._library_definition(action)
            if definition is None:
                raise InvalidInputError("Jellyfin library plan contains an unsupported action")
            if action.startswith("adopt-library-"):
                completed.append(action)
                continue
            name, collection_type, path = definition
            try:
                self._request(
                    "POST",
                    self._library_create_url(name, collection_type, path),
                    authenticated=True,
                    operation="mutation",
                )
            except HttpStatusError as error:
                if error.status in {401, 403}:
                    return self._library_guided(
                        actions=tuple(completed),
                        code="jellyfin-authentication",
                        reason="Verify the current Jellyfin administrator credentials and retry.",
                    )
                raise
            completed.append(action)
            created.append(action)

        if created:
            try:
                readback = self._read_libraries()
            except HttpStatusError as error:
                if error.status not in {401, 403}:
                    raise
                auth_error = JellyfinAuthenticationError(error.status)
                return self._library_guided(
                    actions=tuple(completed),
                    code="jellyfin-authentication",
                    reason="Verify the current Jellyfin administrator credentials and retry.",
                    error=auth_error,
                )
            for name, collection_type, path in _MANAGED_LIBRARIES:
                matches = [item for item in readback if item["Name"] == name]
                if len(matches) != 1 or (
                    matches[0]["CollectionType"] != collection_type
                    or matches[0]["Locations"] != (path,)
                ):
                    return self._library_guided(
                        actions=tuple(completed),
                        code="jellyfin-library-readback-conflict",
                        reason="Managed Jellyfin library readback is incomplete or does not match the approved definition.",
                    )

        return JellyfinResult(
            service=SERVICE_NAME,
            status="ok",
            actions=tuple(completed),
            mode="libraries",
        )

    def reconcile_libraries(
        self,
        *,
        confirm_drift: bool = False,
        dry_run: bool = False,
    ) -> JellyfinResult:
        """Create missing approved libraries and guide all existing drift."""

        try:
            plan = self.plan_libraries(dry_run=dry_run)
        except HttpStatusError as error:
            if error.status not in {401, 403}:
                raise
            auth_error = JellyfinAuthenticationError(error.status)
            return self._library_guided(
                actions=(),
                code="jellyfin-authentication",
                reason="Verify the current Jellyfin administrator credentials and retry.",
                error=auth_error,
            )
        return self.apply_libraries(
            plan,
            confirm_drift=confirm_drift,
            _inventory_checked=True,
        )

    @staticmethod
    def _api_key_items(payload: Any) -> list[Mapping[str, Any]]:
        """Validate only the stable fields used by API-key reconciliation."""

        if not isinstance(payload, Mapping):
            raise JellyfinApiKeySchemaError()
        raw_items = _safe_mapping_value(payload, "Items")
        if not isinstance(raw_items, list):
            raise JellyfinApiKeySchemaError()
        total_record_count = _safe_mapping_value(payload, "TotalRecordCount")
        start_index = _safe_mapping_value(payload, "StartIndex")
        if (
            type(total_record_count) is not int
            or type(start_index) is not int
            or total_record_count < 0
            or start_index < 0
            or start_index != 0
            or total_record_count != len(raw_items)
        ):
            raise JellyfinApiKeySchemaError()
        items: list[Mapping[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, Mapping):
                raise JellyfinApiKeySchemaError()
            app_name = _safe_mapping_value(item, "AppName")
            access_token = _safe_mapping_value(item, "AccessToken")
            is_active = _safe_mapping_value(item, "IsActive")
            date_revoked = _safe_mapping_value(item, "DateRevoked")
            # AppName is required for safe classification.  In particular,
            # accepting an item without it would silently classify a malformed
            # response as "no Lumen key" and create another key.
            if not _nonempty_text(app_name):
                raise JellyfinApiKeySchemaError()
            # Some Jellyfin versions omit a token on an unrelated item, which
            # this slice never consumes.  A Lumen item must always provide a
            # usable token, while any present unrelated token is type-checked
            # without being copied into a public value.
            if access_token is not None and not isinstance(access_token, str):
                raise JellyfinApiKeySchemaError()
            if is_active is not None and not isinstance(is_active, bool):
                raise JellyfinApiKeySchemaError()
            if date_revoked is not None and not isinstance(date_revoked, str):
                raise JellyfinApiKeySchemaError()
            if app_name == "Lumen" and not _nonempty_text(access_token):
                raise JellyfinApiKeySchemaError()
            # Keep only the validated fields needed by this slice.  The full
            # server response (including unrelated key metadata) never enters
            # a result, checkpoint, or public report surface.
            items.append(
                {
                    "AppName": app_name,
                    "AccessToken": access_token,
                    "IsActive": is_active,
                    "DateRevoked": date_revoked,
                }
            )
        return items

    def _read_api_keys(self) -> list[Mapping[str, Any]]:
        if self._session is None:
            raise JellyfinSessionError()
        return self._api_key_items(
            self._decode_json(
                self._request("GET", "/Auth/Keys", authenticated=True, operation="api-keys"),
                operation="api-keys",
            )
        )

    @staticmethod
    def _api_key_matches(items: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        return [item for item in items if item.get("AppName") == "Lumen"]

    @staticmethod
    def _api_key_checkpoint(code: str, reason: str) -> ServiceCheckpoint:
        return ServiceCheckpoint(
            code=code,
            reason=reason,
            action="review",
            severity="error",
        )

    def _api_key_guided(
        self,
        *,
        actions: tuple[str, ...],
        checkpoint: ServiceCheckpoint,
        error: BaseException | None = None,
    ) -> JellyfinResult:
        return JellyfinResult(
            service=SERVICE_NAME,
            status="guided",
            actions=actions,
            checkpoints=(checkpoint,),
            dry_run=False,
            error=error,
            mode="adopted",
        )

    def reconcile_api_key(self, *, dry_run: bool = False) -> JellyfinResult:
        """Reuse or create exactly one admin API key named ``Lumen``.

        This method requires the session produced by :meth:`authenticate` or
        :meth:`configure`; it never authenticates implicitly and never writes
        environment or state files.
        """

        if self._session is None:
            raise JellyfinSessionError()
        self._api_key_handoff = None
        try:
            items = self._read_api_keys()
        except HttpStatusError as error:
            if error.status in {401, 403}:
                auth_error = JellyfinAuthenticationError(error.status)
                checkpoint = self._api_key_checkpoint(
                    "jellyfin-authentication",
                    "Verify the current Jellyfin administrator credentials and retry.",
                )
                return self._api_key_guided(
                    actions=(), checkpoint=checkpoint, error=auth_error
                )
            raise

        matches = self._api_key_matches(items)
        if len(matches) > 1:
            return self._api_key_guided(
                actions=(),
                checkpoint=self._api_key_checkpoint(
                    "jellyfin-api-key-conflict",
                    "Multiple Lumen API keys exist; resolve the duplicate manually and retry.",
                ),
            )
        if len(matches) == 1:
            match = matches[0]
            if match.get("DateRevoked") is not None:
                return self._api_key_guided(
                    actions=(),
                    checkpoint=self._api_key_checkpoint(
                        "jellyfin-api-key-revoked",
                        "The existing Lumen API key is revoked; resolve it manually and retry.",
                    ),
                )
            if match.get("IsActive") is False:
                return self._api_key_guided(
                    actions=(),
                    checkpoint=self._api_key_checkpoint(
                        "jellyfin-api-key-inactive",
                        "The existing Lumen API key is inactive; resolve it manually and retry.",
                    ),
                )
            access_token = match.get("AccessToken")
            if dry_run:
                return JellyfinResult(
                    service=SERVICE_NAME,
                    status="dry-run",
                    actions=("reuse-api-key",),
                    dry_run=True,
                    mode="adopted",
                )
            # _api_key_items guarantees this is a non-empty string for a
            # matching item; retain this guard as a defense at the handoff.
            if not _nonempty_text(access_token):
                raise JellyfinApiKeySchemaError()
            self._api_key_handoff = JellyfinApiKeyHandoff(access_token)
            return JellyfinResult(
                service=SERVICE_NAME,
                status="ok",
                actions=("reuse-api-key",),
                dry_run=bool(dry_run),
                mode="adopted",
            )

        if dry_run:
            return JellyfinResult(
                service=SERVICE_NAME,
                status="dry-run",
                actions=("create-api-key",),
                dry_run=True,
                mode="adopted",
            )

        create_path = "/Auth/Keys?" + urllib.parse.urlencode({"app": "Lumen"})
        try:
            self._request("POST", create_path, authenticated=True, operation="api-keys")
        except HttpStatusError as error:
            if error.status in {401, 403}:
                auth_error = JellyfinAuthenticationError(error.status)
                checkpoint = self._api_key_checkpoint(
                    "jellyfin-authentication",
                    "Verify the current Jellyfin administrator credentials and retry.",
                )
                return self._api_key_guided(
                    actions=("create-api-key",), checkpoint=checkpoint, error=auth_error
                )
            raise

        try:
            readback = self._read_api_keys()
        except HttpStatusError as error:
            if error.status in {401, 403}:
                auth_error = JellyfinAuthenticationError(error.status)
                checkpoint = self._api_key_checkpoint(
                    "jellyfin-authentication",
                    "Verify the current Jellyfin administrator credentials and retry.",
                )
                return self._api_key_guided(
                    actions=("create-api-key",), checkpoint=checkpoint, error=auth_error
                )
            raise

        readback_matches = self._api_key_matches(readback)
        if not readback_matches:
            return self._api_key_guided(
                actions=("create-api-key",),
                checkpoint=self._api_key_checkpoint(
                    "jellyfin-api-key-readback-missing",
                    "The created Lumen API key was not visible in readback; verify Jellyfin and retry.",
                ),
            )
        if len(readback_matches) > 1:
            return self._api_key_guided(
                actions=("create-api-key",),
                checkpoint=self._api_key_checkpoint(
                    "jellyfin-api-key-readback-ambiguous",
                    "Readback contains multiple Lumen API keys; resolve the duplicate manually.",
                ),
            )
        readback_match = readback_matches[0]
        if readback_match.get("DateRevoked") is not None:
            return self._api_key_guided(
                actions=("create-api-key",),
                checkpoint=self._api_key_checkpoint(
                    "jellyfin-api-key-revoked",
                    "The created Lumen API key is revoked; resolve it manually and retry.",
                ),
            )
        if readback_match.get("IsActive") is False:
            return self._api_key_guided(
                actions=("create-api-key",),
                checkpoint=self._api_key_checkpoint(
                    "jellyfin-api-key-inactive",
                    "The created Lumen API key is inactive; resolve it manually and retry.",
                ),
            )
        access_token = readback_match.get("AccessToken")
        if not _nonempty_text(access_token):
            raise JellyfinApiKeySchemaError()
        self._api_key_handoff = JellyfinApiKeyHandoff(access_token)
        return JellyfinResult(
            service=SERVICE_NAME,
            status="ok",
            actions=("create-api-key",),
            dry_run=False,
            mode="adopted",
        )

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
    "JellyfinApiKeyHandoff",
    "JellyfinApiKeySchemaError",
    "JellyfinLibrarySchemaError",
    "JellyfinCapability",
    "JellyfinCapabilityError",
    "JellyfinError",
    "JellyfinResult",
    "JellyfinSchemaError",
    "JellyfinSession",
    "JellyfinSessionError",
    "configure_jellyfin",
    "plan_jellyfin",
]
