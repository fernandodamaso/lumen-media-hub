"""Safe Sonarr and Radarr configuration adapters for the Linux installer."""

from __future__ import annotations

import os
import json
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import DriftError, InstallerError, InvalidInputError
from ..http import HttpResponse, HttpStatusError, HttpTransportError
from .base import ServiceCheckpoint, ServiceDrift, ServicePlan, ServiceResult


SONARR_CONFIG_PATH = Path("config/sonarr/config.xml")
RADARR_CONFIG_PATH = Path("config/radarr/config.xml")
_CONFIG_PATHS = {
    "sonarr": SONARR_CONFIG_PATH,
    "radarr": RADARR_CONFIG_PATH,
}


class ServarrError(InstallerError):
    """Base class for sanitized Sonarr/Radarr adapter failures."""

    code = "servarr-error"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        self.code = code or type(self).code
        # Adapter failures never retain caller or response text in their
        # public message.  The optional argument is accepted for compatibility
        # with callers that already have a local diagnostic string.
        InstallerError.__init__(self, self.code)

    @property
    def report(self) -> dict[str, str]:
        return {"error": self.code}

    @property
    def redacted(self) -> dict[str, str]:
        return self.report


class ServarrConfigError(InvalidInputError, ServarrError):
    """The exact bind-mounted service config did not contain a usable key."""

    code = "servarr-config"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, self.code)

    @property
    def report(self) -> dict[str, str]:
        return {"error": self.code}

    @property
    def redacted(self) -> dict[str, str]:
        return self.report


class ServarrCapabilityError(InvalidInputError, ServarrError):
    code = "servarr-capability"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, self.code)


class ServarrSchemaError(InvalidInputError, ServarrError):
    code = "servarr-schema"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, self.code)


class ServarrConflictError(DriftError, ServarrError):
    code = "servarr-conflict"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        DriftError.__init__(self, self.code)


@dataclass(frozen=True)
class ServarrResult(ServiceResult):
    """Operation result whose private API key is never rendered."""

    api_key: str | None = field(default=None, repr=False, compare=False)

    def __repr__(self) -> str:
        return (
            f"ServarrResult(service={self.service!r}, status={self.status!r}, "
            f"actions={self.actions!r}, dry_run={self.dry_run!r})"
        )


def _service_name(value: Any) -> str:
    if not isinstance(value, str) or value.strip().casefold() not in _CONFIG_PATHS:
        raise InvalidInputError("Sonarr or Radarr service is required")
    return value.strip().casefold()


def read_servarr_api_key(service: str, root: os.PathLike[str] | str | None = None) -> str:
    """Read ``ApiKey`` only from the exact host bind-mounted config path."""

    service_name = _service_name(service)
    config_root = Path.cwd() if root is None else Path(root)
    path = config_root / _CONFIG_PATHS[service_name]
    try:
        root_element = ET.parse(path).getroot()
        api_key_element = root_element.find("ApiKey")
        value = api_key_element.text if api_key_element is not None else None
    except (OSError, ET.ParseError, ValueError, TypeError):
        raise ServarrConfigError() from None
    if not isinstance(value, str) or not value.strip():
        raise ServarrConfigError() from None
    return value.strip()


def read_api_key(
    service_or_root: str | os.PathLike[str],
    root_or_service: os.PathLike[str] | str | None = None,
) -> str:
    """Compatibility wrapper for the service-first config key reader."""

    if isinstance(service_or_root, str) and service_or_root.casefold() in _CONFIG_PATHS:
        return read_servarr_api_key(service_or_root, root_or_service)
    if root_or_service is None:
        raise InvalidInputError("Sonarr or Radarr service is required")
    return read_servarr_api_key(str(root_or_service), service_or_root)


parse_api_key = read_api_key


class SonarrAdapter:
    service = "sonarr"
    api_prefix = "/api/v3"
    root_path = "/data/media/tv"
    category_field = "tvCategory"

    def __init__(
        self,
        base_url: str,
        transport: Any,
        *,
        api_key: str,
        qbit_password: str,
    ) -> None:
        if transport is None or not callable(getattr(transport, "request", None)):
            raise InvalidInputError("Servarr transport is required")
        if not isinstance(base_url, str) or not base_url.strip():
            raise InvalidInputError("Servarr URL is required")
        candidate = base_url.strip().rstrip("/")
        try:
            parsed = urllib.parse.urlsplit(candidate)
            _ = parsed.port
        except (TypeError, ValueError):
            raise InvalidInputError("Servarr URL is invalid") from None
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise InvalidInputError("Servarr URL is invalid")
        if not isinstance(api_key, str) or not api_key.strip():
            raise InvalidInputError("Servarr API key is required")
        if not isinstance(qbit_password, str) or not qbit_password.strip():
            raise InvalidInputError("qBittorrent password is required")
        self.base_url = candidate
        self._transport = transport
        self._api_key = api_key.strip()
        self._qbit_password = qbit_password

    def __repr__(self) -> str:
        return f"{type(self).__name__}(configured=True)"

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, *, body: Any = None) -> Any:
        url = self._url(path)
        kwargs: dict[str, Any] = {
            "headers": {"Accept": "application/json", "X-Api-Key": self._api_key},
        }
        if body is not None:
            kwargs["json_body"] = body
        try:
            response = self._transport.request(method, url, **kwargs)
        except HttpTransportError:
            raise
        except (TimeoutError, OSError):
            request_error = ServarrError(code="servarr-transport")
        except Exception:
            request_error = ServarrError(code="servarr-transport")
        else:
            request_error = None
        if request_error is not None:
            raise request_error from None
        status = getattr(response, "status", None)
        if status is None and isinstance(response, Mapping):
            status = response.get("status", 200)
        try:
            status = int(200 if status is None else status)
        except (TypeError, ValueError):
            raise ServarrSchemaError() from None
        if not 200 <= status < 300:
            raise HttpStatusError(method=method, url=url, status=status)
        return response

    @staticmethod
    def _json(response: Any) -> Any:
        if isinstance(response, Mapping) and not isinstance(response, HttpResponse):
            if "body" not in response:
                return response
            payload = response["body"]
            if isinstance(payload, (Mapping, list)):
                return payload
            if isinstance(payload, bytes):
                decode_error: ServarrSchemaError | None = None
                try:
                    return json.loads(payload.decode("utf-8"))
                except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError):
                    decode_error = ServarrSchemaError()
                if decode_error is not None:
                    raise decode_error from None
            if isinstance(payload, str):
                decode_error = None
                try:
                    return json.loads(payload)
                except (TypeError, ValueError, json.JSONDecodeError):
                    decode_error = ServarrSchemaError()
                if decode_error is not None:
                    raise decode_error from None
            raise ServarrSchemaError() from None
        decoder = getattr(response, "json", None)
        if not callable(decoder):
            raise ServarrSchemaError() from None
        decode_error: ServarrSchemaError | None = None
        try:
            return decoder()
        except Exception:
            decode_error = ServarrSchemaError()
        if decode_error is not None:
            raise decode_error from None
        raise ServarrSchemaError() from None

    @staticmethod
    def _collection(payload: Any, wrapper: str) -> list[Mapping[str, Any]]:
        if isinstance(payload, list):
            values = payload
        elif isinstance(payload, Mapping) and isinstance(payload.get(wrapper), list):
            values = payload[wrapper]
        else:
            raise ServarrSchemaError() from None
        if not all(isinstance(value, Mapping) for value in values):
            raise ServarrSchemaError() from None
        return list(values)

    def _check_capability(self) -> None:
        payload = self._json(self._request("GET", f"{self.api_prefix}/system/status"))
        if not isinstance(payload, Mapping):
            raise ServarrCapabilityError() from None
        version = payload.get("version")
        if not isinstance(version, str) or not version.strip():
            raise ServarrCapabilityError() from None

    @staticmethod
    def _field_entries(fields: Any) -> tuple[list[tuple[Any, dict[str, Any]]], str]:
        if isinstance(fields, Mapping):
            entries: list[tuple[Any, dict[str, Any]]] = []
            for key, value in fields.items():
                if not isinstance(value, Mapping):
                    raise ServarrSchemaError() from None
                field = dict(value)
                name = field.get("name", key)
                if not isinstance(name, str) or not name:
                    raise ServarrSchemaError() from None
                entries.append((key, field))
            return entries, "mapping"
        if isinstance(fields, list):
            entries = []
            for value in fields:
                if not isinstance(value, Mapping):
                    raise ServarrSchemaError() from None
                field = dict(value)
                name = field.get("name")
                if not isinstance(name, str) or not name:
                    raise ServarrSchemaError() from None
                entries.append((None, field))
            return entries, "list"
        raise ServarrSchemaError() from None

    def _qbit_schema(self, payload: Any) -> dict[str, Any]:
        schemas = self._collection(payload, "schemas")
        for candidate in schemas:
            values = (
                candidate.get("implementation"),
                candidate.get("implementationName"),
                candidate.get("name"),
            )
            if not any(isinstance(value, str) and "qbit" in value.casefold() for value in values):
                continue
            fields, _ = self._field_entries(candidate.get("fields"))
            names = {field.get("name") for _, field in fields}
            required = {"host", "port", "username", "password", self.category_field}
            if not required.issubset(names):
                raise ServarrSchemaError() from None
            return dict(candidate)
        raise ServarrSchemaError() from None

    @staticmethod
    def _field_values(fields: Any) -> dict[str, Any]:
        entries, _ = SonarrAdapter._field_entries(fields)
        return {field["name"]: field.get("value") for _, field in entries}

    @staticmethod
    def _set_field_values(fields: Any, values: Mapping[str, Any]) -> Any:
        entries, shape = SonarrAdapter._field_entries(fields)
        if shape == "mapping":
            result: dict[Any, dict[str, Any]] = {}
            for key, field in entries:
                updated = dict(field)
                name = updated["name"]
                if name in values:
                    updated["value"] = values[name]
                result[key] = updated
            return result
        result_list: list[dict[str, Any]] = []
        for _, field in entries:
            updated = dict(field)
            name = updated["name"]
            if name in values:
                updated["value"] = values[name]
            result_list.append(updated)
        return result_list

    @staticmethod
    def _is_qbit_client(client: Mapping[str, Any]) -> bool:
        values = (
            client.get("implementation"),
            client.get("implementationName"),
            client.get("name"),
        )
        return any(isinstance(value, str) and "qbit" in value.casefold() for value in values)

    def _client_payload(self, schema: Mapping[str, Any]) -> dict[str, Any]:
        fields = schema.get("fields")
        field_values = {
            "host": "qbittorrent",
            "port": 8081,
            "username": "admin",
            "password": self._qbit_password,
            self.category_field: self.service,
        }
        payload = dict(schema)
        payload["fields"] = self._set_field_values(fields, field_values)
        payload.setdefault("name", "qBittorrent")
        payload.setdefault("implementation", "QBittorrent")
        payload.setdefault("configContract", "QBittorrentSettings")
        payload.setdefault("enable", True)
        payload.setdefault("protocol", "torrent")
        payload.setdefault("priority", 1)
        payload.pop("id", None)
        return payload

    def _updated_client_payload(
        self,
        existing: Mapping[str, Any],
        schema: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = dict(existing)
        schema_fields = schema.get("fields")
        existing_fields = payload.get("fields")
        if existing_fields is None:
            existing_fields = schema_fields
        existing_values = self._field_values(existing_fields)
        existing_values.update(
            {
                "host": "qbittorrent",
                "port": 8081,
                "username": "admin",
                "password": self._qbit_password,
                self.category_field: self.service,
            }
        )
        payload["fields"] = self._set_field_values(existing_fields, existing_values)
        return payload

    def _configure_from_state(
        self,
        roots: list[Mapping[str, Any]],
        schema: Mapping[str, Any],
        clients: list[Mapping[str, Any]],
        *,
        confirm: bool,
    ) -> ServarrResult:
        root_exists = any(root.get("path") == self.root_path for root in roots)
        actions: list[str] = ["reuse-root-folder" if root_exists else "create-root-folder"]
        existing = next((client for client in clients if self._is_qbit_client(client)), None)
        if existing is None:
            client_action = "create-download-client"
            client_payload = self._client_payload(schema)
            drift: tuple[ServiceDrift, ...] = ()
        else:
            client_action = "reuse-download-client"
            existing_values = self._field_values(existing.get("fields"))
            desired = {
                "host": "qbittorrent",
                "port": 8081,
                "username": "admin",
                self.category_field: self.service,
            }
            drift_records = tuple(
                ServiceDrift(
                    resource="download-client",
                    field=name,
                    reason="managed field differs",
                )
                for name, value in desired.items()
                if existing_values.get(name, object()) != value
            )
            drift = drift_records
            client_payload = self._updated_client_payload(existing, schema)
            if drift:
                client_action = "update-download-client"
                if not confirm:
                    return ServarrResult(
                        service=self.service,
                        status="drift",
                        actions=tuple(actions),
                        drift=drift,
                        error=ServarrConflictError(),
                    )

        if existing is not None and not drift:
            if not root_exists:
                self._request("POST", f"{self.api_prefix}/rootfolder", body={"path": self.root_path})
                actions[0] = "create-root-folder"
            actions.append("reuse-download-client")
            return ServarrResult(service=self.service, status="ok", actions=tuple(actions))

        try:
            self._request("POST", f"{self.api_prefix}/downloadclient/test", body=client_payload)
        except (HttpStatusError, HttpTransportError, ServarrError):
            checkpoint = ServiceCheckpoint(
                code="servarr-download-client-test",
                reason="The qBittorrent download client test failed; review the service and retry.",
                action="retry",
                severity="error",
            )
            return ServarrResult(
                service=self.service,
                status="guided",
                actions=tuple(actions),
                checkpoints=(checkpoint,),
                error=ServarrError(code="servarr-download-client-test"),
            )

        if not root_exists:
            self._request("POST", f"{self.api_prefix}/rootfolder", body={"path": self.root_path})
        actions[0] = "reuse-root-folder" if root_exists else "create-root-folder"
        if existing is None:
            self._request("POST", f"{self.api_prefix}/downloadclient", body=client_payload)
            actions.append("create-download-client")
        else:
            client_id = existing.get("id")
            if client_id is None:
                raise ServarrSchemaError() from None
            self._request("PUT", f"{self.api_prefix}/downloadclient/{client_id}", body=client_payload)
            actions.append("update-download-client")
        return ServarrResult(service=self.service, status="ok", actions=tuple(actions))

    def configure(self, *, confirm: bool = False, dry_run: bool = False) -> ServarrResult:
        if dry_run:
            return ServarrResult(
                service=self.service,
                status="dry-run",
                actions=("check-capability", "reconcile-root-folder", "reconcile-download-client"),
                dry_run=True,
            )
        self._check_capability()
        roots = self._collection(
            self._json(self._request("GET", f"{self.api_prefix}/rootfolder")),
            "items",
        )
        schema = self._qbit_schema(
            self._json(self._request("GET", f"{self.api_prefix}/downloadclient/schema"))
        )
        clients = self._collection(
            self._json(self._request("GET", f"{self.api_prefix}/downloadclient")),
            "items",
        )
        return self._configure_from_state(roots, schema, clients, confirm=bool(confirm))


class RadarrAdapter(SonarrAdapter):
    service = "radarr"
    api_prefix = "/api/v3"
    root_path = "/data/media/movies"
    category_field = "movieCategory"


__all__ = [
    "RADARR_CONFIG_PATH",
    "SONARR_CONFIG_PATH",
    "RadarrAdapter",
    "ServarrCapabilityError",
    "ServarrConfigError",
    "ServarrConflictError",
    "ServarrError",
    "ServarrResult",
    "ServarrSchemaError",
    "SonarrAdapter",
    "parse_api_key",
    "read_api_key",
    "read_servarr_api_key",
]
