"""Safe Prowlarr integrations for the Linux installer.

Prowlarr exposes the same broad schema-driven API shape as the other *arr
services, but its schemas and returned field containers vary between
versions.  This adapter only changes resources it can identify and validate:
one qBittorrent download client, the configured Sonarr/Radarr applications,
and one installer-owned Generic Torznab indexer.  Every create or update is
tested first; unsupported indexer definitions are handed back to the
Prowlarr UI instead of being guessed at.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import DriftError, InstallerError, InvalidInputError, PartialError
from ..http import HttpResponse, HttpStatusError, HttpTransportError
from .base import ServiceCheckpoint, ServiceDrift, ServicePlan, ServiceResult


SERVICE_NAME = "prowlarr"
DEFAULT_BASE_URL = "http://127.0.0.1:9696"
DEFAULT_QBIT_HOST = "qbittorrent"
DEFAULT_QBIT_PORT = 8081
DEFAULT_QBIT_USERNAME = "admin"
DEFAULT_SONARR_URL = "http://sonarr:8989"
DEFAULT_RADARR_URL = "http://radarr:7878"
GENERIC_TORZNAB_NAME = "Lumen Generic Torznab"
PROWLARR_CONFIG_PATH = Path("config/prowlarr/config.xml")

_MISSING = object()

_QBIT_IDENTITY = {
    "name": "qbittorrent",
    "implementation": "qbittorrent",
    "implementationName": "qbittorrent",
    "configContract": "qbittorrentsettings",
}
_APPLICATION_IDENTITIES = {
    "sonarr": {
        "name": "sonarr",
        "implementation": "sonarr",
        "implementationName": "sonarr",
        "configContract": "sonarrsettings",
    },
    "radarr": {
        "name": "radarr",
        "implementation": "radarr",
        "implementationName": "radarr",
        "configContract": "radarrsettings",
    },
}
_GENERIC_TORZNAB_IDENTITY = {
    "name": "generic torznab",
    "implementation": "torznab",
    "implementationName": "generic torznab",
    "configContract": "torznabsettings",
}
_GENERIC_TORZNAB_TYPE_IDENTITY = {
    "implementation": "torznab",
    "implementationName": "generic torznab",
    "configContract": "torznabsettings",
}


class ProwlarrError(InstallerError):
    """Base class for sanitized Prowlarr adapter failures."""

    code = "prowlarr-error"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        self.code = code or type(self).code
        # Do not retain the supplied text: it may have come from a response,
        # request body, or a caller-provided secret.
        InstallerError.__init__(self, self.code)

    @property
    def report(self) -> dict[str, str]:
        return {"error": self.code}

    @property
    def redacted(self) -> dict[str, str]:
        return self.report


class ProwlarrConfigError(InvalidInputError, ProwlarrError):
    code = "prowlarr-config"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, self.code)

    @property
    def report(self) -> dict[str, str]:
        return {"error": self.code}

    @property
    def redacted(self) -> dict[str, str]:
        return self.report


class ProwlarrCapabilityError(InvalidInputError, ProwlarrError):
    code = "prowlarr-capability"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, self.code)


class ProwlarrSchemaError(InvalidInputError, ProwlarrError):
    code = "prowlarr-schema"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, self.code)


class ProwlarrConflictError(DriftError, ProwlarrError):
    code = "prowlarr-conflict"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        DriftError.__init__(self, self.code)


class ProwlarrGuidedError(PartialError, ProwlarrError):
    code = "prowlarr-guided"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        self.code = code or type(self).code
        PartialError.__init__(self, self.code)


class ProwlarrTestError(ProwlarrGuidedError):
    code = "prowlarr-test"


class ProwlarrTransportError(ProwlarrError):
    code = "prowlarr-transport"


@dataclass(frozen=True)
class ProwlarrResult(ServiceResult):
    """Operation result with the Prowlarr API key kept private."""

    api_key: str | None = field(default=None, repr=False, compare=False)

    @property
    def exit_code(self) -> int:
        return int(getattr(self.error, "exit_code", 0) or 0)

    def __repr__(self) -> str:
        return (
            f"ProwlarrResult(service={self.service!r}, status={self.status!r}, "
            f"actions={self.actions!r}, dry_run={self.dry_run!r})"
        )


def _service_text(value: Any) -> str:
    return value.strip().casefold() if isinstance(value, str) else ""


def _secret(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _base_url(value: Any, label: str = "Prowlarr URL") -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"{label} is required")
    candidate = value.strip().rstrip("/")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in candidate):
        raise InvalidInputError(f"{label} is invalid")
    url_error: InvalidInputError | None = None
    try:
        parsed = urllib.parse.urlsplit(candidate)
        _ = parsed.port
    except (TypeError, ValueError):
        url_error = InvalidInputError(f"{label} is invalid")
    if url_error is not None:
        raise url_error from None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise InvalidInputError(f"{label} is invalid")
    return candidate


def read_prowlarr_api_key(root: os.PathLike[str] | str | None = None) -> str:
    """Read ``ApiKey`` only from the exact host bind-mounted config path."""

    config_root = Path.cwd() if root is None else Path(root)
    path = config_root / PROWLARR_CONFIG_PATH
    config_error: ProwlarrConfigError | None = None
    try:
        root_element = ET.parse(path).getroot()
        api_key_element = root_element.find("ApiKey")
        value = api_key_element.text if api_key_element is not None else None
    except (OSError, ET.ParseError, ValueError, TypeError):
        config_error = ProwlarrConfigError()
    if config_error is not None:
        raise config_error from None
    if not isinstance(value, str) or not value.strip():
        raise ProwlarrConfigError() from None
    return value.strip()


def read_api_key(root: os.PathLike[str] | str | None = None) -> str:
    """Compatibility alias for callers shared with the other *arr adapters."""

    return read_prowlarr_api_key(root)


parse_api_key = read_api_key


def _normalized_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(char for char in value.casefold() if char.isalnum())


def _field_entries(fields: Any) -> tuple[list[tuple[Any, dict[str, Any]]], str]:
    if isinstance(fields, Mapping):
        entries: list[tuple[Any, dict[str, Any]]] = []
        for key, value in fields.items():
            if not isinstance(value, Mapping):
                raise ProwlarrSchemaError() from None
            field = dict(value)
            name = field.get("name", key)
            if not isinstance(name, str) or not name.strip():
                raise ProwlarrSchemaError() from None
            field["name"] = name
            entries.append((key, field))
        return entries, "mapping"
    if isinstance(fields, list):
        entries = []
        for value in fields:
            if not isinstance(value, Mapping):
                raise ProwlarrSchemaError() from None
            field = dict(value)
            name = field.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ProwlarrSchemaError() from None
            entries.append((None, field))
        return entries, "list"
    raise ProwlarrSchemaError() from None


def _field_name(field: Mapping[str, Any]) -> str:
    return str(field.get("name", ""))


def _field_values(fields: Any) -> dict[str, Any]:
    entries, _ = _field_entries(fields)
    return {_normalized_name(_field_name(field)): field.get("value") for _, field in entries}


def _field_actual_name(fields: Any, aliases: tuple[str, ...]) -> str | None:
    entries, _ = _field_entries(fields)
    wanted = {_normalized_name(alias) for alias in aliases}
    for _, field in entries:
        actual = _field_name(field)
        if _normalized_name(actual) in wanted:
            return actual
    return None


def _field_value(fields: Any, aliases: tuple[str, ...]) -> Any:
    values = _field_values(fields)
    for alias in aliases:
        if _normalized_name(alias) in values:
            return values[_normalized_name(alias)]
    return _MISSING


def _set_field_values(fields: Any, desired: Mapping[tuple[str, ...], Any]) -> Any:
    entries, shape = _field_entries(fields)
    aliases_to_value = {
        _normalized_name(alias): value
        for aliases, value in desired.items()
        for alias in aliases
    }
    if shape == "mapping":
        result: dict[Any, dict[str, Any]] = {}
        for key, field in entries:
            updated = dict(field)
            value_key = _normalized_name(_field_name(updated))
            if value_key in aliases_to_value:
                updated["value"] = aliases_to_value[value_key]
            result[key] = updated
        return result
    result_list: list[dict[str, Any]] = []
    for _, field in entries:
        updated = dict(field)
        value_key = _normalized_name(_field_name(updated))
        if value_key in aliases_to_value:
            updated["value"] = aliases_to_value[value_key]
        result_list.append(updated)
    return result_list


def _collection(payload: Any, wrapper: str) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, Mapping) and isinstance(payload.get(wrapper), list):
        values = payload[wrapper]
    else:
        raise ProwlarrSchemaError() from None
    if not all(isinstance(value, Mapping) for value in values):
        raise ProwlarrSchemaError() from None
    return list(values)


def _exact_identity_matches(
    candidate: Mapping[str, Any],
    identity: Mapping[str, str],
    *,
    required: tuple[str, ...],
) -> bool:
    if not isinstance(candidate, Mapping):
        return False
    for field in required:
        if _service_text(candidate.get(field)) != identity[field]:
            return False
    for field, expected in identity.items():
        if field in required or field not in candidate:
            continue
        if _service_text(candidate.get(field)) != expected:
            return False
    return True


def _kind_matches(candidate: Mapping[str, Any], *needles: str) -> bool:
    normalized_needles = tuple(_service_text(needle) for needle in needles)
    if normalized_needles in {("qbit",), ("qbittorrent",)}:
        return _exact_identity_matches(candidate, _QBIT_IDENTITY, required=tuple(_QBIT_IDENTITY))
    if normalized_needles in {("sonarr",), ("radarr",)}:
        identity = _APPLICATION_IDENTITIES[normalized_needles[0]]
        return _exact_identity_matches(candidate, identity, required=tuple(identity))
    if set(normalized_needles) == {"generic", "torznab"} and len(normalized_needles) == 2:
        return _exact_identity_matches(
            candidate,
            _GENERIC_TORZNAB_IDENTITY,
            required=tuple(_GENERIC_TORZNAB_IDENTITY),
        )
    return False


def _is_service_application(candidate: Mapping[str, Any], service: str) -> bool:
    identity = _APPLICATION_IDENTITIES.get(_service_text(service))
    return identity is not None and _exact_identity_matches(
        candidate,
        identity,
        required=("name", "implementation"),
    )


def _is_service_application_schema(candidate: Mapping[str, Any], service: str) -> bool:
    identity = _APPLICATION_IDENTITIES.get(_service_text(service))
    return identity is not None and _exact_identity_matches(
        candidate,
        identity,
        required=tuple(identity),
    )


def _is_qbit(candidate: Mapping[str, Any]) -> bool:
    return _exact_identity_matches(candidate, _QBIT_IDENTITY, required=("name", "implementation"))


def _is_qbit_schema(candidate: Mapping[str, Any]) -> bool:
    return _exact_identity_matches(candidate, _QBIT_IDENTITY, required=tuple(_QBIT_IDENTITY))


def _is_generic_torznab(candidate: Mapping[str, Any]) -> bool:
    return _exact_identity_matches(
        candidate,
        _GENERIC_TORZNAB_IDENTITY,
        required=("name", "implementation"),
    )


def _is_managed_generic_torznab(candidate: Mapping[str, Any]) -> bool:
    return (
        _service_text(candidate.get("name")) == _service_text(GENERIC_TORZNAB_NAME)
        and _exact_identity_matches(
            candidate,
            _GENERIC_TORZNAB_TYPE_IDENTITY,
            required=("implementation",),
        )
    )


def _is_generic_torznab_schema(candidate: Mapping[str, Any]) -> bool:
    return _exact_identity_matches(
        candidate,
        _GENERIC_TORZNAB_IDENTITY,
        required=tuple(_GENERIC_TORZNAB_IDENTITY),
    )


def _is_generic_torznab_type(candidate: Mapping[str, Any]) -> bool:
    return _exact_identity_matches(
        candidate,
        _GENERIC_TORZNAB_TYPE_IDENTITY,
        required=("implementation",),
    )


def _response_status(response: Any) -> int:
    status = getattr(response, "status", None)
    if status is None and isinstance(response, Mapping):
        status = response.get("status", 200)
    if status is None:
        status = 200
    try:
        normalized = int(status)
    except (TypeError, ValueError):
        error = ProwlarrSchemaError()
    else:
        return normalized
    raise error from None


def _response_json(response: Any) -> Any:
    if isinstance(response, Mapping) and not isinstance(response, HttpResponse):
        if "body" not in response:
            return response
        body = response.get("body")
        if isinstance(body, (Mapping, list)):
            return body
        if isinstance(body, bytes):
            try:
                return json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, TypeError, ValueError):
                error = ProwlarrSchemaError()
            raise error from None
        if isinstance(body, str):
            try:
                return json.loads(body)
            except (TypeError, ValueError):
                error = ProwlarrSchemaError()
            raise error from None
        raise ProwlarrSchemaError() from None
    decoder = getattr(response, "json", None)
    if not callable(decoder):
        raise ProwlarrSchemaError() from None
    try:
        payload = decoder()
    except Exception:
        error = ProwlarrSchemaError()
    else:
        return payload
    raise error from None


@dataclass(frozen=True)
class _ResourcePlan:
    resource: str
    create_path: str
    test_path: str
    update_path: str | None
    payload: dict[str, Any]
    action: str
    drift: tuple[ServiceDrift, ...] = ()
    existing_id: Any = None

    @property
    def mutating(self) -> bool:
        return self.action.startswith(("create-", "update-"))


class ProwlarrAdapter:
    """Reconcile supported Prowlarr core resources without generic guessing."""

    api_prefix = "/api/v1"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        transport: Any = None,
        *,
        api_key: str | None = None,
        config_root: os.PathLike[str] | str | None = None,
        root: os.PathLike[str] | str | None = None,
        qbit_password: str | None = None,
        password: str | None = None,
        sonarr_api_key: str | None = None,
        radarr_api_key: str | None = None,
        sonarr_key: str | None = None,
        radarr_key: str | None = None,
        application_api_keys: Mapping[str, Any] | None = None,
        app_api_keys: Mapping[str, Any] | None = None,
        sonarr_url: str = DEFAULT_SONARR_URL,
        radarr_url: str = DEFAULT_RADARR_URL,
        sonarr_base_url: str | None = None,
        radarr_base_url: str | None = None,
        application_urls: Mapping[str, Any] | None = None,
        generic_torznab_url: str | None = None,
        generic_torznab_api_key: str | None = None,
        generic_indexer_url: str | None = None,
        generic_indexer_api_key: str | None = None,
        generic_url: str | None = None,
        generic_api_key: str | None = None,
        torznab_url: str | None = None,
        torznab_api_key: str | None = None,
        torznab_base_url: str | None = None,
        torznab_key: str | None = None,
        indexer_url: str | None = None,
        indexer_api_key: str | None = None,
        indexer_definitions: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None = None,
        unsupported_definitions: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None = None,
    ) -> None:
        if transport is None or not callable(getattr(transport, "request", None)):
            raise InvalidInputError("Prowlarr transport is required")
        self.base_url = _base_url(base_url)
        self._transport = transport

        selected_config_root = config_root if config_root is not None else root
        if api_key is None:
            api_key = read_prowlarr_api_key(selected_config_root)
        selected_api_key = _secret(api_key)
        if selected_api_key is None:
            raise InvalidInputError("Prowlarr API key is required")
        self._api_key = selected_api_key

        selected_qbit_password = qbit_password if qbit_password is not None else password
        self._qbit_password = _secret(selected_qbit_password)
        if self._qbit_password is None:
            raise InvalidInputError("qBittorrent password is required")

        key_sources = [application_api_keys, app_api_keys]
        for source in key_sources:
            if source is not None and not isinstance(source, Mapping):
                raise InvalidInputError("Prowlarr application API keys must be a mapping")
        merged_keys: dict[str, Any] = {}
        for source in key_sources:
            if isinstance(source, Mapping):
                merged_keys.update(source)
        selected_sonarr_key = sonarr_api_key if sonarr_api_key is not None else sonarr_key
        selected_radarr_key = radarr_api_key if radarr_api_key is not None else radarr_key
        if selected_sonarr_key is None:
            selected_sonarr_key = merged_keys.get("sonarr")
        if selected_radarr_key is None:
            selected_radarr_key = merged_keys.get("radarr")
        self._application_keys = {
            "sonarr": _secret(selected_sonarr_key),
            "radarr": _secret(selected_radarr_key),
        }

        if application_urls is not None and not isinstance(application_urls, Mapping):
            raise InvalidInputError("Prowlarr application URLs must be a mapping")
        selected_urls = dict(application_urls or {})
        selected_sonarr_url = selected_urls.get(
            "sonarr",
            sonarr_base_url if sonarr_base_url is not None else sonarr_url,
        )
        selected_radarr_url = selected_urls.get(
            "radarr",
            radarr_base_url if radarr_base_url is not None else radarr_url,
        )
        self._application_urls = {
            "sonarr": _base_url(selected_sonarr_url, "Sonarr URL"),
            "radarr": _base_url(selected_radarr_url, "Radarr URL"),
        }

        torznab_values = (
            generic_torznab_url,
            generic_indexer_url,
            generic_url,
            torznab_url,
            torznab_base_url,
            indexer_url,
        )
        torznab_keys = (
            generic_torznab_api_key,
            generic_indexer_api_key,
            generic_api_key,
            torznab_api_key,
            torznab_key,
            indexer_api_key,
        )
        selected_torznab_url = next((value for value in torznab_values if value is not None), None)
        selected_torznab_key = next((value for value in torznab_keys if value is not None), None)
        if (selected_torznab_url is None) != (selected_torznab_key is None):
            raise InvalidInputError("Generic Torznab URL and API key are both required")
        self._generic_torznab_url = (
            _base_url(selected_torznab_url, "Generic Torznab URL")
            if selected_torznab_url is not None
            else None
        )
        self._generic_torznab_api_key = _secret(selected_torznab_key)
        if selected_torznab_url is not None and self._generic_torznab_api_key is None:
            raise InvalidInputError("Generic Torznab URL and API key are both required")

        definitions = unsupported_definitions if unsupported_definitions is not None else indexer_definitions
        if definitions is not None:
            if not isinstance(definitions, (list, tuple)) or not all(
                isinstance(value, Mapping) for value in definitions
            ):
                raise InvalidInputError("Prowlarr indexer definitions are invalid")
            self._indexer_definitions = tuple(dict(value) for value in definitions)
        else:
            self._indexer_definitions = ()

    def __repr__(self) -> str:
        return "ProwlarrAdapter(configured=True)"

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, *, body: Any = None) -> Any:
        url = self._url(path)
        kwargs: dict[str, Any] = {
            "headers": {"Accept": "application/json", "X-Api-Key": self._api_key},
        }
        if body is not None:
            kwargs["json_body"] = body
        request_error: ProwlarrTransportError | None = None
        try:
            response = self._transport.request(method, url, **kwargs)
        except HttpTransportError:
            raise
        except (TimeoutError, OSError):
            request_error = ProwlarrTransportError()
        except Exception:
            request_error = ProwlarrTransportError()
        if request_error is not None:
            raise request_error from None
        status = _response_status(response)
        if not 200 <= status < 300:
            raise HttpStatusError(method=method, url=url, status=status)
        return response

    def _check_capability(self) -> None:
        payload = _response_json(self._request("GET", f"{self.api_prefix}/system/status"))
        if not isinstance(payload, Mapping):
            raise ProwlarrCapabilityError() from None
        version = payload.get("version")
        if not isinstance(version, str) or not version.strip():
            raise ProwlarrCapabilityError() from None

    def _schema(self, path: str, *needles: str) -> dict[str, Any]:
        payload = _response_json(self._request("GET", path))
        schemas = _collection(payload, "schemas")
        for candidate in schemas:
            if _kind_matches(candidate, *needles):
                fields = candidate.get("fields")
                _field_entries(fields)
                return dict(candidate)
        raise ProwlarrSchemaError() from None

    def _schemas(self, path: str) -> list[Mapping[str, Any]]:
        return _collection(_response_json(self._request("GET", path)), "schemas")

    def _items(self, path: str) -> list[Mapping[str, Any]]:
        return _collection(_response_json(self._request("GET", path)), "items")

    @staticmethod
    def _require_fields(fields: Any, requirements: Mapping[str, tuple[str, ...]]) -> None:
        for aliases in requirements.values():
            if _field_actual_name(fields, aliases) is None:
                raise ProwlarrSchemaError() from None

    @classmethod
    def _qbit_schema(cls, schemas: list[Mapping[str, Any]]) -> dict[str, Any]:
        for candidate in schemas:
            if not _is_qbit_schema(candidate):
                continue
            fields = candidate.get("fields")
            cls._require_fields(
                fields,
                {
                    "host": ("host", "hostname", "server"),
                    "port": ("port",),
                    "username": ("username", "user"),
                    "password": ("password", "pass"),
                },
            )
            return dict(candidate)
        raise ProwlarrSchemaError() from None

    @classmethod
    def _application_schema(cls, schemas: list[Mapping[str, Any]], service: str) -> dict[str, Any]:
        for candidate in schemas:
            if not _is_service_application_schema(candidate, service):
                continue
            fields = candidate.get("fields")
            cls._require_fields(
                fields,
                {
                    "url": ("baseUrl", "url"),
                    "api_key": ("apiKey", "apikey", "key"),
                },
            )
            return dict(candidate)
        raise ProwlarrSchemaError() from None

    @classmethod
    def _generic_schema(cls, schemas: list[Mapping[str, Any]]) -> dict[str, Any]:
        for candidate in schemas:
            if not _is_generic_torznab_schema(candidate):
                continue
            fields = candidate.get("fields")
            cls._require_fields(
                fields,
                {
                    "url": ("baseUrl", "url"),
                    "api_key": ("apiKey", "apikey", "key"),
                },
            )
            return dict(candidate)
        raise ProwlarrSchemaError() from None

    @staticmethod
    def _is_supported_definition(definition: Mapping[str, Any]) -> bool:
        return _is_generic_torznab(definition)

    @staticmethod
    def _payload_from_schema(
        schema: Mapping[str, Any],
        desired: Mapping[tuple[str, ...], Any],
        *,
        default_name: str,
        defaults: Mapping[str, Any],
    ) -> dict[str, Any]:
        fields = schema.get("fields")
        payload = dict(schema)
        payload["fields"] = _set_field_values(fields, desired)
        payload.setdefault("name", default_name)
        for key, value in defaults.items():
            payload.setdefault(key, value)
        payload.pop("id", None)
        return payload

    @staticmethod
    def _payload_from_existing(
        existing: Mapping[str, Any],
        schema: Mapping[str, Any],
        desired: Mapping[tuple[str, ...], Any],
    ) -> dict[str, Any]:
        payload = dict(existing)
        fields = payload.get("fields")
        if fields is None:
            fields = schema.get("fields")
        payload["fields"] = _set_field_values(fields, desired)
        return payload

    @staticmethod
    def _find_qbit(items: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
        return next((item for item in items if _is_qbit(item)), None)

    @staticmethod
    def _find_application(items: list[Mapping[str, Any]], service: str) -> Mapping[str, Any] | None:
        return next((item for item in items if _is_service_application(item, service)), None)

    def _find_managed_indexer(self, items: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
        named = next(
            (
                item
                for item in items
                if _is_managed_generic_torznab(item)
            ),
            None,
        )
        if named is not None:
            return named
        for item in items:
            if not _is_generic_torznab_type(item):
                continue
            fields = item.get("fields")
            if fields is None or self._generic_torznab_url is None:
                continue
            current_url = _field_value(fields, ("baseUrl", "url"))
            if current_url == self._generic_torznab_url:
                return item
        return None

    @staticmethod
    def _resource_drift(
        resource: str,
        fields: Any,
        desired: Mapping[tuple[str, ...], Any],
        *,
        ignore_unknown: tuple[str, ...] = (),
    ) -> tuple[ServiceDrift, ...]:
        drift: list[ServiceDrift] = []
        ignored = {_normalized_name(value) for value in ignore_unknown}
        for aliases, target in desired.items():
            actual = _field_actual_name(fields, aliases)
            if actual is None:
                raise ProwlarrSchemaError() from None
            current = _field_value(fields, aliases)
            if _normalized_name(actual) in ignored and (current is _MISSING or not _secret(current)):
                continue
            if current is _MISSING:
                drift.append(ServiceDrift(resource=resource, field=actual, reason="managed field is missing"))
            elif current != target:
                drift.append(ServiceDrift(resource=resource, field=actual, reason="managed field differs"))
        return tuple(drift)

    def _qbit_plan(self, schema: Mapping[str, Any], existing: Mapping[str, Any] | None) -> _ResourcePlan:
        desired = {
            ("host", "hostname", "server"): DEFAULT_QBIT_HOST,
            ("port",): DEFAULT_QBIT_PORT,
            ("username", "user"): DEFAULT_QBIT_USERNAME,
            ("password", "pass"): self._qbit_password,
        }
        if existing is None:
            payload = self._payload_from_schema(
                schema,
                desired,
                default_name="qBittorrent",
                defaults={"implementation": "QBittorrent", "configContract": "QBittorrentSettings", "enable": True},
            )
            return _ResourcePlan(
                resource="download-client",
                create_path=f"{self.api_prefix}/downloadclient",
                test_path=f"{self.api_prefix}/downloadclient/test",
                update_path=None,
                payload=payload,
                action="create-download-client",
            )
        fields = existing.get("fields")
        # Prowlarr commonly masks or omits an existing password.  Do not turn
        # that unknown value into a conflict; a known non-empty value is still
        # protected by the normal managed-field confirmation gate.
        drift = self._resource_drift(
            "download-client",
            fields,
            desired,
            ignore_unknown=("password", "pass"),
        )
        payload = self._payload_from_existing(existing, schema, desired)
        if not drift:
            action = "reuse-download-client"
        else:
            action = "update-download-client"
        return _ResourcePlan(
            resource="download-client",
            create_path=f"{self.api_prefix}/downloadclient",
            test_path=f"{self.api_prefix}/downloadclient/test",
            update_path=(
                f"{self.api_prefix}/downloadclient/{existing.get('id')}"
                if existing.get("id") is not None
                else None
            ),
            payload=payload,
            action=action,
            drift=drift,
            existing_id=existing.get("id"),
        )

    def _application_plan(
        self,
        service: str,
        schema: Mapping[str, Any],
        existing: Mapping[str, Any] | None,
    ) -> _ResourcePlan:
        api_key = self._application_keys[service]
        if api_key is None:
            raise AssertionError("application plan requested without an API key")
        desired = {
            ("baseUrl", "url"): self._application_urls[service],
            ("apiKey", "apikey", "key"): api_key,
        }
        sync_actual = _field_actual_name(schema.get("fields"), ("syncLevel",))
        if sync_actual is not None:
            desired[("syncLevel",)] = "fullSync"
        resource = f"{service}-application"
        action_prefix = f"{service}-application"
        if existing is None:
            payload = self._payload_from_schema(
                schema,
                desired,
                default_name=service.title(),
                defaults={
                    "implementation": service.title(),
                    "configContract": f"{service.title()}Settings",
                    "enable": True,
                },
            )
            return _ResourcePlan(
                resource=resource,
                create_path=f"{self.api_prefix}/applications",
                test_path=f"{self.api_prefix}/applications/test",
                update_path=None,
                payload=payload,
                action=f"create-{action_prefix}",
            )
        existing_fields = existing.get("fields")
        drift = self._resource_drift(
            resource,
            existing_fields,
            desired,
            ignore_unknown=("apiKey", "apikey", "key"),
        )
        payload = self._payload_from_existing(existing, schema, desired)
        return _ResourcePlan(
            resource=resource,
            create_path=f"{self.api_prefix}/applications",
            test_path=f"{self.api_prefix}/applications/test",
            update_path=(
                f"{self.api_prefix}/applications/{existing.get('id')}"
                if existing.get("id") is not None
                else None
            ),
            payload=payload,
            action=(f"reuse-{action_prefix}" if not drift else f"update-{action_prefix}"),
            drift=drift,
            existing_id=existing.get("id"),
        )

    def _generic_plan(self, schema: Mapping[str, Any], existing: Mapping[str, Any] | None) -> _ResourcePlan:
        if self._generic_torznab_url is None or self._generic_torznab_api_key is None:
            raise AssertionError("Generic Torznab plan requested without credentials")
        desired = {
            ("baseUrl", "url"): self._generic_torznab_url,
            ("apiKey", "apikey", "key"): self._generic_torznab_api_key,
        }
        if existing is None:
            payload = self._payload_from_schema(
                schema,
                desired,
                default_name=GENERIC_TORZNAB_NAME,
                defaults={"implementation": "Torznab", "configContract": "TorznabSettings", "enable": True},
            )
            return _ResourcePlan(
                resource="generic-torznab",
                create_path=f"{self.api_prefix}/indexer",
                test_path=f"{self.api_prefix}/indexer/test",
                update_path=None,
                payload=payload,
                action="create-generic-torznab",
            )
        existing_fields = existing.get("fields")
        drift = self._resource_drift(
            "generic-torznab",
            existing_fields,
            desired,
            ignore_unknown=("apiKey", "apikey", "key"),
        )
        payload = self._payload_from_existing(existing, schema, desired)
        return _ResourcePlan(
            resource="generic-torznab",
            create_path=f"{self.api_prefix}/indexer",
            test_path=f"{self.api_prefix}/indexer/test",
            update_path=(
                f"{self.api_prefix}/indexer/{existing.get('id')}"
                if existing.get("id") is not None
                else None
            ),
            payload=payload,
            action=("reuse-generic-torznab" if not drift else "update-generic-torznab"),
            drift=drift,
            existing_id=existing.get("id"),
        )

    def _guided(
        self,
        *,
        code: str,
        reason: str,
        action: str,
        error: ProwlarrError,
        actions: tuple[str, ...] = (),
    ) -> ProwlarrResult:
        return ProwlarrResult(
            service=SERVICE_NAME,
            status="guided",
            actions=actions,
            checkpoints=(
                ServiceCheckpoint(
                    code=code,
                    reason=reason,
                    action=action,
                    severity="error",
                ),
            ),
            error=error,
            api_key=self._api_key,
        )

    def _generic_plans(self) -> tuple[_ResourcePlan, ...] | ProwlarrResult:
        if self._generic_torznab_url is None:
            return ()
        indexer_schemas = self._schemas(f"{self.api_prefix}/indexer/schema")
        indexer_existing = self._items(f"{self.api_prefix}/indexer")
        if any(not self._is_supported_definition(definition) for definition in self._indexer_definitions):
            return self._guided(
                code="prowlarr-indexer-guided",
                reason="Configure the unsupported indexer definition in the Prowlarr UI, then retry.",
                action="open-prowlarr-ui",
                error=ProwlarrGuidedError(code="prowlarr-indexer-guided"),
            )
        try:
            generic_schema = self._generic_schema(indexer_schemas)
        except ProwlarrSchemaError:
            return self._guided(
                code="prowlarr-indexer-guided",
                reason="Configure the requested indexer in the Prowlarr UI, then retry.",
                action="open-prowlarr-ui",
                error=ProwlarrGuidedError(code="prowlarr-indexer-guided"),
            )
        generic_existing = self._find_managed_indexer(indexer_existing)
        return (self._generic_plan(generic_schema, generic_existing),)

    def _load_state(
        self,
        *,
        include_generic_torznab: bool = True,
    ) -> tuple[_ResourcePlan, ...] | ProwlarrResult:
        qbit_schema = self._qbit_schema(self._schemas(f"{self.api_prefix}/downloadclient/schema"))
        qbit_existing = self._find_qbit(self._items(f"{self.api_prefix}/downloadclient"))

        application_targets = tuple(service for service, key in self._application_keys.items() if key is not None)
        application_schemas: list[Mapping[str, Any]] = []
        application_existing: list[Mapping[str, Any]] = []
        if application_targets:
            application_schemas = self._schemas(f"{self.api_prefix}/applications/schema")
            application_existing = self._items(f"{self.api_prefix}/applications")

        plans: list[_ResourcePlan] = [self._qbit_plan(qbit_schema, qbit_existing)]
        for service in application_targets:
            schema = self._application_schema(application_schemas, service)
            existing = self._find_application(application_existing, service)
            plans.append(self._application_plan(service, schema, existing))
        if include_generic_torznab:
            generic = self._generic_plans()
            if isinstance(generic, ProwlarrResult):
                return generic
            plans.extend(generic)
        return tuple(plans)

    def _apply_plan(self, resource_plan: _ResourcePlan) -> None:
        if not resource_plan.mutating:
            return
        path = resource_plan.create_path
        method = "POST"
        if resource_plan.action.startswith("update-"):
            if resource_plan.update_path is None:
                raise ProwlarrSchemaError() from None
            path = resource_plan.update_path
            method = "PUT"
        test_error: ProwlarrTestError | None = None
        try:
            self._request("POST", resource_plan.test_path, body=resource_plan.payload)
        except (HttpStatusError, HttpTransportError, ProwlarrError):
            test_error = ProwlarrTestError(code=f"prowlarr-{resource_plan.resource}-test")
        if test_error is not None:
            raise test_error from None
        self._request(method, path, body=resource_plan.payload)

    def _apply_plans(
        self,
        plans: tuple[_ResourcePlan, ...],
        *,
        confirm: bool,
    ) -> ProwlarrResult:
        drift = tuple(record for resource_plan in plans for record in resource_plan.drift)
        actions = tuple(resource_plan.action for resource_plan in plans)
        if drift and not confirm:
            return ProwlarrResult(
                service=SERVICE_NAME,
                status="drift",
                actions=actions,
                drift=drift,
                error=ProwlarrConflictError(),
                api_key=self._api_key,
            )

        completed: list[str] = []
        for resource_plan in plans:
            if not resource_plan.mutating:
                completed.append(resource_plan.action)
                continue
            try:
                self._apply_plan(resource_plan)
            except ProwlarrTestError as error:
                checkpoint_code = error.code
                return self._guided(
                    code=checkpoint_code,
                    reason="The Prowlarr resource test failed; review the service and retry.",
                    action="retry",
                    error=ProwlarrTestError(code=checkpoint_code),
                    actions=tuple(completed),
                )
            completed.append(resource_plan.action)
        return ProwlarrResult(
            service=SERVICE_NAME,
            status="ok",
            actions=tuple(completed),
            api_key=self._api_key,
        )

    def configure(
        self,
        *,
        confirm: bool = False,
        dry_run: bool = False,
        include_generic_torznab: bool = True,
    ) -> ProwlarrResult:
        if dry_run:
            actions = [
                "check-capability",
                "reconcile-download-client",
                "reconcile-applications",
            ]
            if include_generic_torznab:
                actions.append("reconcile-generic-torznab")
            return ProwlarrResult(
                service=SERVICE_NAME,
                status="dry-run",
                actions=tuple(actions),
                dry_run=True,
                api_key=self._api_key,
            )

        self._check_capability()
        loaded = self._load_state(include_generic_torznab=include_generic_torznab)
        if isinstance(loaded, ProwlarrResult):
            return loaded
        return self._apply_plans(loaded, confirm=confirm)

    def configure_generic_torznab(
        self,
        *,
        confirm: bool = False,
        dry_run: bool = False,
    ) -> ProwlarrResult:
        if dry_run:
            return ProwlarrResult(
                service=SERVICE_NAME,
                status="dry-run",
                actions=("reconcile-generic-torznab",),
                dry_run=True,
                api_key=self._api_key,
            )
        self._check_capability()
        loaded = self._generic_plans()
        if isinstance(loaded, ProwlarrResult):
            return loaded
        return self._apply_plans(loaded, confirm=confirm)

    def plan(self, *, dry_run: bool = False) -> ServicePlan:
        return ServicePlan(
            service=SERVICE_NAME,
            actions=(
                "check-capability",
                "reconcile-download-client",
                "reconcile-applications",
                "reconcile-generic-torznab",
            ),
            dry_run=bool(dry_run),
        )


def plan_prowlarr(
    base_url: str = DEFAULT_BASE_URL,
    transport: Any = None,
    **kwargs: Any,
) -> ServicePlan:
    dry_run = kwargs.pop("dry_run", False)
    return ProwlarrAdapter(base_url, transport, **kwargs).plan(dry_run=dry_run)


def configure_prowlarr(
    base_url: str = DEFAULT_BASE_URL,
    transport: Any = None,
    **kwargs: Any,
) -> ProwlarrResult:
    dry_run = kwargs.pop("dry_run", False)
    confirm = kwargs.pop("confirm", False)
    return ProwlarrAdapter(base_url, transport, **kwargs).configure(confirm=confirm, dry_run=dry_run)


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_RADARR_URL",
    "DEFAULT_QBIT_HOST",
    "DEFAULT_QBIT_PORT",
    "DEFAULT_QBIT_USERNAME",
    "DEFAULT_SONARR_URL",
    "GENERIC_TORZNAB_NAME",
    "PROWLARR_CONFIG_PATH",
    "ProwlarrAdapter",
    "ProwlarrCapabilityError",
    "ProwlarrConfigError",
    "ProwlarrConflictError",
    "ProwlarrError",
    "ProwlarrGuidedError",
    "ProwlarrResult",
    "ProwlarrSchemaError",
    "ProwlarrTestError",
    "ProwlarrTransportError",
    "configure_prowlarr",
    "parse_api_key",
    "plan_prowlarr",
    "read_api_key",
    "read_prowlarr_api_key",
]
