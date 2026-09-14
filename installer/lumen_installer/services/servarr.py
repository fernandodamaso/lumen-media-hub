"""Safe Sonarr and Radarr configuration adapters for the Linux installer."""

from __future__ import annotations

import os
import json
import re
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

QUALITY_PROFILE_4K_NAME = "Lumen 4K WEB"
QUALITY_PROFILE_1080P_NAME = "Lumen 1080p WEB fallback"
QUALITY_MAX_SIZE_MB_PER_MINUTE = {2160: 200, 1080: 100}
CUSTOM_FORMAT_NAME = "Lumen WEB quality exclusions"
CUSTOM_FORMAT_TERMS = (
    "remux",
    "bdmv",
    "bd25",
    "bd50",
    "br-disk",
    "blu-ray disc",
    "uhd disc",
    "upscale",
    "upscaled",
    "ai upscale",
)


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
        qbit_port: int = 8081,
        verify_qbit_client: bool = False,
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
        if isinstance(qbit_port, bool) or not isinstance(qbit_port, int) or not 1 <= qbit_port <= 65535:
            raise InvalidInputError("qBittorrent port is invalid")
        self._qbit_port = qbit_port
        self._verify_qbit_client = bool(verify_qbit_client)

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
    def _quality_name(definition: Mapping[str, Any]) -> str:
        quality = definition.get("quality")
        for value in (
            definition.get("title"),
            definition.get("name"),
            quality.get("name") if isinstance(quality, Mapping) else None,
        ):
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _quality_id(definition: Mapping[str, Any]) -> int | None:
        quality = definition.get("quality")
        values = (
            quality.get("id") if isinstance(quality, Mapping) else None,
            definition.get("id"),
        )
        for value in values:
            if isinstance(value, bool):
                continue
            if isinstance(value, int) and value > 0:
                return value
        return None

    @classmethod
    def _is_web_quality(cls, definition: Mapping[str, Any], resolution: int) -> bool:
        quality = definition.get("quality")
        declared_resolution = (
            quality.get("resolution") if isinstance(quality, Mapping) else None
        )
        if declared_resolution not in (None, resolution):
            return False
        name = re.sub(r"[^a-z0-9]+", "", cls._quality_name(definition).casefold())
        if not (name.endswith(f"{resolution}p") or f"{resolution}p" in name):
            return False
        return "web" in name or "web" in str(
            quality.get("source", "") if isinstance(quality, Mapping) else ""
        ).casefold()

    @classmethod
    def _quality_weight(
        cls,
        definition: Mapping[str, Any],
    ) -> int:
        quality = definition.get("quality")
        value = definition.get("weight")
        if value is None and isinstance(quality, Mapping):
            value = quality.get("weight")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
        return 0

    @classmethod
    def _quality_definitions(cls, payload: Any) -> list[Mapping[str, Any]]:
        return cls._collection(payload, "items")

    @staticmethod
    def _profile_quality_id(item: Mapping[str, Any]) -> int | None:
        quality = item.get("quality")
        value = quality.get("id") if isinstance(quality, Mapping) else None
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None

    @classmethod
    def _profile_items(
        cls,
        items: Any,
        *,
        allowed_ids: set[int],
        weights: Mapping[int, int],
    ) -> list[dict[str, Any]]:
        if not isinstance(items, list) or not all(isinstance(item, Mapping) for item in items):
            raise ServarrSchemaError() from None

        def transform(item: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
            updated = dict(item)
            children = item.get("items")
            if children is not None and not isinstance(children, list):
                raise ServarrSchemaError() from None
            if children:
                if not all(isinstance(child, Mapping) for child in children):
                    raise ServarrSchemaError() from None
                transformed = [transform(child) for child in children]
                transformed.sort(key=lambda value: value[1])
                updated["items"] = [child for child, _ in transformed]
                updated["allowed"] = any(child.get("allowed") for child, _ in transformed)
                return updated, max((rank for _, rank in transformed), default=0)
            quality_id = cls._profile_quality_id(item)
            if quality_id is None:
                raise ServarrSchemaError() from None
            updated["allowed"] = quality_id in allowed_ids
            return updated, weights.get(quality_id or 0, 0)

        return [item for item, _ in sorted((transform(item) for item in items), key=lambda value: value[1])]

    @classmethod
    def _profile_cutoff(
        cls,
        items: list[Mapping[str, Any]],
        *,
        target_ids: set[int],
        weights: Mapping[int, int],
    ) -> int:
        candidates: list[tuple[int, int, int]] = []

        def walk(item: Mapping[str, Any]) -> list[tuple[int, int, int]]:
            children = item.get("items")
            if isinstance(children, list) and children:
                nested: list[tuple[int, int, int]] = []
                for child in children:
                    if not isinstance(child, Mapping):
                        raise ServarrSchemaError() from None
                    nested.extend(walk(child))
                target_weight = max((candidate[0] for candidate in nested), default=None)
                group_id = item.get("id")
                if (
                    target_weight is not None
                    and item.get("allowed") is True
                    and isinstance(group_id, int)
                    and not isinstance(group_id, bool)
                    and group_id > 0
                ):
                    grouped = (target_weight, 1, group_id)
                    candidates.append(grouped)
                return nested

            quality_id = cls._profile_quality_id(item)
            if quality_id in target_ids:
                item_id = item.get("id")
                if not isinstance(item_id, int) or isinstance(item_id, bool) or item_id <= 0:
                    item_id = quality_id
                return [(weights.get(quality_id, 0), 0, item_id)]
            return []

        for item in items:
            candidates.extend(walk(item))
        if not candidates:
            raise ServarrSchemaError() from None
        return max(candidates, key=lambda candidate: (candidate[0], candidate[1]))[2]

    @staticmethod
    def _schema_collection(payload: Any, wrappers: tuple[str, ...]) -> list[Mapping[str, Any]]:
        if isinstance(payload, list):
            values = payload
        elif isinstance(payload, Mapping):
            values = next(
                (payload.get(wrapper) for wrapper in wrappers if isinstance(payload.get(wrapper), list)),
                None,
            )
        else:
            values = None
        if not isinstance(values, list) or not all(isinstance(value, Mapping) for value in values):
            raise ServarrSchemaError() from None
        return list(values)

    @staticmethod
    def _custom_format_comparable(
        payload: Mapping[str, Any],
        identifier: int,
    ) -> dict[str, Any]:
        specifications = payload.get("specifications")
        if isinstance(specifications, list):
            normalized_specifications = []
            for specification in specifications:
                if not isinstance(specification, Mapping):
                    raise ServarrSchemaError() from None
                normalized = dict(specification)
                # Servarr's schema exposes preset choices, but the native
                # resource readback omits them after persistence.
                normalized.pop("presets", None)
                normalized_specifications.append(normalized)
            specifications = normalized_specifications
        comparable = {
            "id": identifier,
            "name": payload.get("name"),
            "includeCustomFormatWhenRenaming": payload.get("includeCustomFormatWhenRenaming"),
            "specifications": specifications,
        }
        return comparable

    @staticmethod
    def _custom_format_payload(schema: Mapping[str, Any]) -> dict[str, Any]:
        fields, _ = SonarrAdapter._field_entries(schema.get("fields"))
        value_field = next(
            (field for _, field in fields if str(field.get("name", "")).casefold() == "value"),
            None,
        )
        if value_field is None:
            raise ServarrSchemaError() from None
        expression = "(?i)(?:" + "|".join(re.escape(term) for term in CUSTOM_FORMAT_TERMS) + ")"
        updated_fields: list[dict[str, Any]] = []
        for _, field in fields:
            updated = dict(field)
            if str(updated.get("name", "")).casefold() == "value":
                updated["value"] = expression
            updated_fields.append(updated)
        specification = dict(schema)
        specification.update(
            {
                "name": CUSTOM_FORMAT_NAME,
                "fields": updated_fields,
                "negate": False,
                "required": False,
            }
        )
        return {
            "name": CUSTOM_FORMAT_NAME,
            "includeCustomFormatWhenRenaming": False,
            "specifications": [specification],
        }

    def _custom_format_context(self) -> tuple[Mapping[str, Any] | None, dict[str, Any]]:
        payload = self._json(self._request("GET", f"{self.api_prefix}/customformat"))
        custom_formats = self._collection(payload, "items")
        existing = next(
            (item for item in custom_formats if item.get("name") == CUSTOM_FORMAT_NAME),
            None,
        )
        if existing is not None and "specifications" not in existing:
            identifier = existing.get("id")
            if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier <= 0:
                raise ServarrSchemaError() from None
            existing_detail = self._json(
                self._request("GET", f"{self.api_prefix}/customformat/{identifier}")
            )
            if not isinstance(existing_detail, Mapping):
                raise ServarrSchemaError() from None
            existing = existing_detail

        schema_payload = self._json(
            self._request("GET", f"{self.api_prefix}/customformat/schema")
        )
        schemas = self._schema_collection(schema_payload, ("items", "specifications", "schemas"))
        schema = next(
            (
                item
                for item in schemas
                if "releasetitle" in str(item.get("implementation", "")).casefold()
                or "release title" in str(item.get("implementationName", "")).casefold()
            ),
            None,
        )
        if schema is None:
            raise ServarrSchemaError() from None
        desired = self._custom_format_payload(schema)
        return existing, desired

    def _custom_format_configuration(
        self,
        context: tuple[Mapping[str, Any] | None, dict[str, Any]] | None = None,
    ) -> tuple[int, str]:
        existing, desired = context or self._custom_format_context()
        if existing is None:
            created = self._json(
                self._request("POST", f"{self.api_prefix}/customformat", body=desired)
            )
            identifier = created.get("id") if isinstance(created, Mapping) else None
            if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier <= 0:
                raise ServarrSchemaError() from None
            return identifier, "create-custom-format"

        identifier = existing.get("id")
        if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier <= 0:
            raise ServarrSchemaError() from None
        comparable = self._custom_format_comparable(desired, identifier)
        if all(existing.get(key) == value for key, value in comparable.items()):
            return identifier, "reuse-custom-format"
        self._request(
            "PUT",
            f"{self.api_prefix}/customformat/{identifier}",
            body={**desired, "id": identifier},
        )
        return identifier, "update-custom-format"

    def _quality_configuration_context(self) -> dict[str, Any]:
        definitions = self._quality_definitions(
            self._json(self._request("GET", f"{self.api_prefix}/qualitydefinition"))
        )
        profiles = self._collection(
            self._json(self._request("GET", f"{self.api_prefix}/qualityprofile")),
            "items",
        )
        if not profiles:
            raise ServarrSchemaError() from None

        profile_schema_payload = self._json(
            self._request("GET", f"{self.api_prefix}/qualityprofile/schema")
        )
        profile_schemas = self._schema_collection(
            profile_schema_payload,
            ("items", "schemas", "qualityProfiles"),
        )
        if not any(isinstance(schema.get("items"), list) for schema in profile_schemas):
            raise ServarrSchemaError() from None

        by_resolution: dict[int, list[Mapping[str, Any]]] = {}
        weights: dict[int, int] = {}
        for definition in definitions:
            quality_id = self._quality_id(definition)
            if quality_id is None:
                raise ServarrSchemaError() from None
            weights[quality_id] = self._quality_weight(definition)
            for resolution in QUALITY_MAX_SIZE_MB_PER_MINUTE:
                if self._is_web_quality(definition, resolution):
                    by_resolution.setdefault(resolution, []).append(definition)
                    break

        missing = [resolution for resolution in QUALITY_MAX_SIZE_MB_PER_MINUTE if not by_resolution.get(resolution)]
        if missing:
            raise ServarrSchemaError() from None

        template = next(
            (
                profile
                for profile in profiles
                if isinstance(profile.get("name"), str)
                and profile["name"].strip().casefold() == "any"
            ),
            None,
        )
        if template is None:
            raise ServarrSchemaError() from None

        targets = {
            QUALITY_PROFILE_4K_NAME: {
                "allowed_ids": {
                    self._quality_id(item)
                    for item in by_resolution[2160] + by_resolution[1080]
                },
                "cutoff_ids": {self._quality_id(item) for item in by_resolution[2160]},
            },
            QUALITY_PROFILE_1080P_NAME: {
                "allowed_ids": {self._quality_id(item) for item in by_resolution[1080]},
                "cutoff_ids": {self._quality_id(item) for item in by_resolution[1080]},
            },
        }
        for target in targets.values():
            if None in target["allowed_ids"] or None in target["cutoff_ids"]:
                raise ServarrSchemaError() from None

        managed = {profile.get("name"): profile for profile in profiles}
        for name, target in targets.items():
            base = managed.get(name) or template
            transformed = self._profile_items(
                base.get("items"),
                allowed_ids={value for value in target["allowed_ids"] if value is not None},
                weights=weights,
            )
            self._profile_cutoff(
                transformed,
                target_ids={value for value in target["cutoff_ids"] if value is not None},
                weights=weights,
            )
            format_items = base.get("formatItems", [])
            if not isinstance(format_items, list) or not all(isinstance(item, Mapping) for item in format_items):
                raise ServarrSchemaError() from None

        custom_format = self._custom_format_context()
        return {
            "definitions": definitions,
            "profiles": profiles,
            "template": template,
            "by_resolution": by_resolution,
            "weights": weights,
            "targets": targets,
            "custom_format": custom_format,
        }

    def _quality_preview_actions(self, context: Mapping[str, Any]) -> tuple[str, ...]:
        actions: list[str] = []
        for resolution, maximum in QUALITY_MAX_SIZE_MB_PER_MINUTE.items():
            if any(definition.get("maxSize") != maximum for definition in context["by_resolution"][resolution]):
                actions.append(f"update-quality-definition-{resolution}p")
        existing, desired = context["custom_format"]
        custom_format_id = existing.get("id") if isinstance(existing, Mapping) else None
        if existing is None:
            actions.append("create-custom-format")
        else:
            identifier = existing.get("id")
            if isinstance(identifier, int) and all(
                existing.get(key) == value
                for key, value in self._custom_format_comparable(desired, identifier).items()
            ):
                actions.append("reuse-custom-format")
            else:
                actions.append("update-custom-format")
        for name in (QUALITY_PROFILE_4K_NAME, QUALITY_PROFILE_1080P_NAME):
            existing_profile = next(
                (profile for profile in context["profiles"] if profile.get("name") == name),
                None,
            )
            if existing_profile is None:
                actions.append(f"create-quality-profile-{name}")
                continue
            if not isinstance(custom_format_id, int) or isinstance(custom_format_id, bool) or custom_format_id <= 0:
                actions.append(f"update-quality-profile-{name}")
                continue
            target = context["targets"][name]
            payload = self._profile_payload(
                existing_profile,
                name=name,
                target_ids={value for value in target["cutoff_ids"] if value is not None},
                allowed_ids={value for value in target["allowed_ids"] if value is not None},
                weights=context["weights"],
                custom_format_id=custom_format_id,
            )
            comparable = dict(payload)
            comparable["id"] = existing_profile.get("id")
            actions.append(
                f"{'reuse' if dict(existing_profile) == comparable else 'update'}-quality-profile-{name}"
            )
        return tuple(actions)

    def _quality_profile_configuration(
        self,
        context: Mapping[str, Any] | None = None,
    ) -> ServarrResult:
        context = context or self._quality_configuration_context()
        actions: list[str] = []
        for resolution, maximum in QUALITY_MAX_SIZE_MB_PER_MINUTE.items():
            for definition in context["by_resolution"][resolution]:
                if definition.get("maxSize") == maximum:
                    continue
                payload = dict(definition)
                definition_id = definition.get("id")
                if not isinstance(definition_id, int) or isinstance(definition_id, bool) or definition_id <= 0:
                    raise ServarrSchemaError() from None
                payload["maxSize"] = maximum
                minimum = payload.get("minSize")
                if isinstance(minimum, (int, float)) and not isinstance(minimum, bool) and minimum > maximum:
                    payload["minSize"] = maximum
                preferred = payload.get("preferredSize")
                if isinstance(preferred, (int, float)) and not isinstance(preferred, bool) and preferred > maximum:
                    payload["preferredSize"] = maximum
                self._request(
                    "PUT",
                    f"{self.api_prefix}/qualitydefinition/{definition_id}",
                    body=payload,
                )
                actions.append(f"update-quality-definition-{resolution}p")

        custom_format_id, custom_format_action = self._custom_format_configuration(context["custom_format"])
        actions.append(custom_format_action)
        for name, target in context["targets"].items():
            existing = next(
                (profile for profile in context["profiles"] if profile.get("name") == name),
                None,
            )
            base = existing or context["template"]
            payload = self._profile_payload(
                base,
                name=name,
                target_ids={value for value in target["cutoff_ids"] if value is not None},
                allowed_ids={value for value in target["allowed_ids"] if value is not None},
                weights=context["weights"],
                custom_format_id=custom_format_id,
            )
            if existing is None:
                payload.pop("id", None)
                self._request("POST", f"{self.api_prefix}/qualityprofile", body=payload)
                actions.append(f"create-quality-profile-{name}")
                continue
            profile_id = existing.get("id")
            if not isinstance(profile_id, int) or isinstance(profile_id, bool) or profile_id <= 0:
                raise ServarrSchemaError() from None
            comparable = dict(payload)
            comparable["id"] = profile_id
            if dict(existing) == comparable:
                actions.append(f"reuse-quality-profile-{name}")
                continue
            self._request(
                "PUT",
                f"{self.api_prefix}/qualityprofile/{profile_id}",
                body=comparable,
            )
            actions.append(f"update-quality-profile-{name}")

        return ServarrResult(service=self.service, status="ok", actions=tuple(actions))

    @classmethod
    def _profile_payload(
        cls,
        template: Mapping[str, Any],
        *,
        name: str,
        target_ids: set[int],
        allowed_ids: set[int],
        weights: Mapping[int, int],
        custom_format_id: int,
    ) -> dict[str, Any]:
        payload = dict(template)
        payload["name"] = name
        payload["upgradeAllowed"] = True
        payload["items"] = cls._profile_items(
            template.get("items"),
            allowed_ids=allowed_ids,
            weights=weights,
        )
        payload["cutoff"] = cls._profile_cutoff(
            payload["items"],
            target_ids=target_ids,
            weights=weights,
        )
        format_items = template.get("formatItems", [])
        if not isinstance(format_items, list) or not all(isinstance(item, Mapping) for item in format_items):
            raise ServarrSchemaError() from None
        payload["formatItems"] = [
            dict(item)
            for item in format_items
            if item.get("format") != custom_format_id
        ] + [
            {"format": custom_format_id, "name": CUSTOM_FORMAT_NAME, "score": -1000000}
        ]
        minimum_score = payload.get("minFormatScore")
        if not isinstance(minimum_score, (int, float)) or isinstance(minimum_score, bool) or minimum_score < 0:
            payload["minFormatScore"] = 0
        return payload

    def configure_quality_profiles(self, *, dry_run: bool = False) -> ServarrResult:
        """Stage the native quality policy without doing any queue work."""

        self._check_capability()
        context = self._quality_configuration_context()
        if dry_run:
            return ServarrResult(
                service=self.service,
                status="dry-run",
                actions=self._quality_preview_actions(context),
                dry_run=True,
            )
        return self._quality_profile_configuration(context)

    configure_quality = configure_quality_profiles

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
            "port": self._qbit_port,
            "username": "admin",
            "password": self._qbit_password,
            self.category_field: self.service,
        }
        payload = dict(schema)
        payload["fields"] = self._set_field_values(fields, field_values)
        if not isinstance(payload.get("name"), str) or not payload["name"].strip():
            payload["name"] = "qBittorrent"
        payload.setdefault("implementation", "QBittorrent")
        payload.setdefault("configContract", "QBittorrentSettings")
        payload["enable"] = True
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
                "port": self._qbit_port,
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
            client_payload = self._client_payload(schema)
            drift: tuple[ServiceDrift, ...] = ()
        else:
            existing_values = self._field_values(existing.get("fields"))
            desired = {
                "host": "qbittorrent",
                "port": self._qbit_port,
                "username": "admin",
                self.category_field: self.service,
            }
            drift = tuple(
                ServiceDrift(
                    resource="download-client",
                    field=name,
                    reason="managed field differs",
                )
                for name, value in desired.items()
                if existing_values.get(name, object()) != value
            )
            client_payload = self._updated_client_payload(existing, schema)
            if drift and not confirm:
                return ServarrResult(
                    service=self.service,
                    status="drift",
                    actions=tuple(actions),
                    drift=drift,
                    error=ServarrConflictError(),
                )

        def test_client(payload: Mapping[str, Any]) -> bool:
            try:
                self._request(
                    "POST",
                    f"{self.api_prefix}/downloadclient/test",
                    body=payload,
                )
            except (HttpStatusError, HttpTransportError, ServarrError):
                return False
            return True

        def guided_test_failure() -> ServarrResult:
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

        if existing is not None and not drift:
            if self._verify_qbit_client:
                # Test the stored resource first. Servarr can keep secrets
                # masked/omitted in GET responses while still resolving them
                # by resource id during the test call.
                if not test_client(dict(existing)):
                    if not test_client(client_payload):
                        return guided_test_failure()
                    client_id = existing.get("id")
                    if client_id is None:
                        raise ServarrSchemaError() from None
                    if not root_exists:
                        self._request(
                            "POST",
                            f"{self.api_prefix}/rootfolder",
                            body={"path": self.root_path},
                        )
                    self._request(
                        "PUT",
                        f"{self.api_prefix}/downloadclient/{client_id}",
                        body=client_payload,
                    )
                    actions[0] = "reuse-root-folder" if root_exists else "create-root-folder"
                    actions.append("update-download-client")
                    return ServarrResult(
                        service=self.service, status="ok", actions=tuple(actions)
                    )
            if not root_exists:
                self._request(
                    "POST",
                    f"{self.api_prefix}/rootfolder",
                    body={"path": self.root_path},
                )
                actions[0] = "create-root-folder"
            actions.append("reuse-download-client")
            return ServarrResult(service=self.service, status="ok", actions=tuple(actions))

        if not test_client(client_payload):
            return guided_test_failure()

        if not root_exists:
            self._request(
                "POST",
                f"{self.api_prefix}/rootfolder",
                body={"path": self.root_path},
            )
        actions[0] = "reuse-root-folder" if root_exists else "create-root-folder"
        if existing is None:
            self._request(
                "POST", f"{self.api_prefix}/downloadclient", body=client_payload
            )
            actions.append("create-download-client")
        else:
            client_id = existing.get("id")
            if client_id is None:
                raise ServarrSchemaError() from None
            self._request(
                "PUT",
                f"{self.api_prefix}/downloadclient/{client_id}",
                body=client_payload,
            )
            actions.append("update-download-client")
        return ServarrResult(service=self.service, status="ok", actions=tuple(actions))


    def configure(
        self,
        *,
        confirm: bool = False,
        dry_run: bool = False,
        quality_profiles: bool = False,
    ) -> ServarrResult:
        if dry_run:
            result = ServarrResult(
                service=self.service,
                status="dry-run",
                actions=("check-capability", "reconcile-root-folder", "reconcile-download-client"),
                dry_run=True,
            )
            if quality_profiles:
                quality = self.configure_quality_profiles(dry_run=True)
                return ServarrResult(
                    service=result.service,
                    status=result.status,
                    actions=result.actions + quality.actions,
                    dry_run=True,
                )
            return result
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
        result = self._configure_from_state(roots, schema, clients, confirm=bool(confirm))
        if result.status != "ok" or not quality_profiles:
            return result
        quality = self._quality_profile_configuration()
        return ServarrResult(
            service=self.service,
            status=quality.status,
            actions=result.actions + quality.actions,
            drift=quality.drift,
            checkpoints=quality.checkpoints,
            error=quality.error,
        )


class RadarrAdapter(SonarrAdapter):
    service = "radarr"
    api_prefix = "/api/v3"
    root_path = "/data/media/movies"
    category_field = "movieCategory"


__all__ = [
    "CUSTOM_FORMAT_NAME",
    "CUSTOM_FORMAT_TERMS",
    "QUALITY_MAX_SIZE_MB_PER_MINUTE",
    "QUALITY_PROFILE_1080P_NAME",
    "QUALITY_PROFILE_4K_NAME",
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
