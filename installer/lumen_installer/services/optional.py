"""Capability-gated policy for Lumen's optional Compose profiles.

Optional services are deliberately opt-in.  A profile's backend flag and its
internal links are returned as a pending environment update only after an
injected service test and health check both succeed.  The caller owns the
atomic ``.env`` commit and Compose restart boundary.
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..errors import InvalidInputError
from .base import ServiceCheckpoint


OPTIONAL_PROFILES = ("subtitles", "requests", "indexer-tools", "ai", "maintenance")
SUPPORTED_BAZARR_LANGUAGES = frozenset(
    {
        "de",
        "deu",
        "en",
        "eng",
        "es",
        "fra",
        "fr",
        "ita",
        "it",
        "jpn",
        "ja",
        "kor",
        "ko",
        "nld",
        "nl",
        "por",
        "pt",
        "rus",
        "ru",
        "spa",
        "zho",
        "zh",
    }
)
SUPPORTED_AI_PROVIDERS = frozenset({"openai", "anthropic", "google", "openai-compatible"})

BAZARR_BASE_LINKS = {
    "BAZARR_SONARR_URL": "http://sonarr:8989",
    "BAZARR_RADARR_URL": "http://radarr:7878",
    "BAZARR_JELLYFIN_URL": "http://jellyfin:8096",
}
FLARESOLVERR_PROXY_URL = "http://flaresolverr:8191"


class OptionalProfileError(InvalidInputError):
    """A requested optional profile cannot be safely configured."""

    code = "optional-profile"

    def __init__(self, code: str = "optional-profile") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, repr=False)
class AiConfigValidation:
    """Secret-free validation facts for the AI worker environment."""

    status: str
    provider: str | None = None
    model_configured: bool = False
    credential_configured: bool = False
    compatible_base_url_configured: bool = False
    structured_outputs_enabled: bool = False
    reason_code: str | None = None

    @property
    def valid(self) -> bool:
        return self.status == "ok"

    @property
    def report(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider": self.provider,
            "model_configured": self.model_configured,
            "credential_configured": self.credential_configured,
            "compatible_base_url_configured": self.compatible_base_url_configured,
            "structured_outputs_enabled": self.structured_outputs_enabled,
            "reason_code": self.reason_code,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    def __repr__(self) -> str:
        return (
            f"AiConfigValidation(status={self.status!r}, provider={self.provider!r}, "
            f"model_configured={self.model_configured!r}, credential_configured={self.credential_configured!r})"
        )


@dataclass(frozen=True, repr=False)
class OptionalProfileResult:
    """Secret-free result and pending environment update for optional setup."""

    status: str
    enabled_profiles: tuple[str, ...] = ()
    services: Mapping[str, Any] = field(default_factory=dict)
    environment_update: Mapping[str, str] = field(default_factory=dict, repr=False, compare=False)
    checkpoints: tuple[ServiceCheckpoint, ...] = ()
    dry_run: bool = False

    @property
    def report(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "dry_run": self.dry_run,
            "enabled_profiles": list(self.enabled_profiles),
            "services": dict(self.services),
            "environment_update": {key: "<pending>" for key in self.environment_update},
            "checkpoints": [checkpoint.as_dict() for checkpoint in self.checkpoints],
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    def __repr__(self) -> str:
        return (
            f"OptionalProfileResult(status={self.status!r}, enabled_profiles={self.enabled_profiles!r}, "
            f"dry_run={self.dry_run!r})"
        )


def _text(environment: Mapping[str, Any], key: str) -> str:
    value = environment.get(key)
    return value.strip() if isinstance(value, str) else ""


def _enabled(environment: Mapping[str, Any], key: str) -> bool:
    return _text(environment, key).casefold() in {"1", "true", "yes", "on"}


def _safe_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(value)
        _ = parsed.port
    except (TypeError, ValueError):
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and not parsed.query
        and not parsed.fragment
        and parsed.username is None
        and parsed.password is None
    )


def validate_ai_config(environment: Mapping[str, Any]) -> AiConfigValidation:
    """Validate the exact worker provider contract without exposing secrets."""

    if not isinstance(environment, Mapping):
        raise InvalidInputError("AI environment must be a mapping")
    provider = _text(environment, "AI_PROVIDER").casefold() or None
    model_configured = bool(_text(environment, "AI_MODEL"))
    if provider not in SUPPORTED_AI_PROVIDERS:
        return AiConfigValidation(
            status="guided",
            provider=provider,
            model_configured=model_configured,
            reason_code="unsupported-provider",
        )
    if not model_configured:
        return AiConfigValidation(
            status="guided",
            provider=provider,
            reason_code="model-required",
        )

    if provider == "openai":
        credential = bool(_text(environment, "OPENAI_API_KEY"))
        reason = None if credential else "credential-required"
        return AiConfigValidation(
            status="ok" if credential else "guided",
            provider=provider,
            model_configured=True,
            credential_configured=credential,
            reason_code=reason,
        )
    if provider == "anthropic":
        credential = bool(_text(environment, "ANTHROPIC_API_KEY"))
        reason = None if credential else "credential-required"
        return AiConfigValidation(
            status="ok" if credential else "guided",
            provider=provider,
            model_configured=True,
            credential_configured=credential,
            reason_code=reason,
        )
    if provider == "google":
        credential = bool(_text(environment, "GOOGLE_GENERATIVE_AI_API_KEY"))
        reason = None if credential else "credential-required"
        return AiConfigValidation(
            status="ok" if credential else "guided",
            provider=provider,
            model_configured=True,
            credential_configured=credential,
            reason_code=reason,
        )

    credential = bool(_text(environment, "AI_COMPATIBLE_API_KEY"))
    base_url = _text(environment, "AI_COMPATIBLE_BASE_URL")
    base_configured = bool(base_url) and _safe_url(base_url)
    structured = _enabled(environment, "AI_COMPATIBLE_SUPPORTS_STRUCTURED_OUTPUTS")
    reason = None
    if not base_configured:
        reason = "compatible-base-url-required"
    elif not credential:
        reason = "credential-required"
    elif not structured:
        reason = "structured-outputs-required"
    return AiConfigValidation(
        status="ok" if reason is None else "guided",
        provider=provider,
        model_configured=True,
        credential_configured=credential,
        compatible_base_url_configured=base_configured,
        structured_outputs_enabled=structured,
        reason_code=reason,
    )


def _check(callback: Callable[..., Any] | None) -> bool:
    if callback is None:
        return False
    try:
        value = callback()
    except Exception:
        return False
    if isinstance(value, Mapping):
        value = value.get("status", value.get("healthy", value.get("ok", False)))
    else:
        value = getattr(value, "status", value)
    if isinstance(value, str):
        return value.casefold() in {"ok", "healthy", "passed", "success", "true"}
    return value is True


def _pending_links(environment: Mapping[str, Any], values: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in values.items()
        if not _text(environment, key)
    }


def _failure(profile: str, code: str, reason: str) -> ServiceCheckpoint:
    return ServiceCheckpoint(code=code, reason=reason, action="retry", severity="error")


def configure_optional_profiles(
    environment: Mapping[str, Any],
    *,
    requested_profiles: Sequence[str] = (),
    tests: Mapping[str, Callable[..., Any]] | None = None,
    health: Mapping[str, Callable[..., Any]] | None = None,
    configure: Mapping[str, Callable[..., Any]] | None = None,
    bazarr_language: str | None = None,
    dry_run: bool = False,
) -> OptionalProfileResult:
    """Plan optional profile activation after test and health success.

    The function never mutates ``environment``.  Its environment update is a
    pending value set for the configure transaction to commit atomically.
    """

    if not isinstance(environment, Mapping):
        raise InvalidInputError("optional environment must be a mapping")
    if type(dry_run) is not bool:
        raise InvalidInputError("dry_run must be a boolean")
    try:
        profiles = tuple(requested_profiles)
    except TypeError as exc:
        raise InvalidInputError("optional profiles must be a sequence") from exc
    if any(not isinstance(profile, str) or profile not in OPTIONAL_PROFILES for profile in profiles):
        raise InvalidInputError("unknown optional profile")
    if len(set(profiles)) != len(profiles):
        raise InvalidInputError("duplicate optional profile")
    tests = tests or {}
    health = health or {}
    configure = configure or {}
    if not isinstance(tests, Mapping) or not isinstance(health, Mapping) or not isinstance(configure, Mapping):
        raise InvalidInputError("optional checks must be mappings")

    if dry_run:
        services = {
            profile: {"status": "unverified", "actions": ["test", "health", "enable"]}
            for profile in profiles
        }
        return OptionalProfileResult(
            status="dry-run",
            services=services,
            dry_run=True,
        )

    updates: dict[str, str] = {}
    enabled: list[str] = []
    services: dict[str, Any] = {}
    checkpoints: list[ServiceCheckpoint] = []

    for profile in profiles:
        if profile == "maintenance":
            checkpoint = _failure(
                profile,
                "maintenance-guided",
                "Maintenance services remain a guided, non-destructive handoff and stay disabled in Lumen.",
            )
            checkpoints.append(checkpoint)
            services[profile] = {"status": "guided", "actions": ["handoff"]}
            continue

        if profile == "ai":
            validation = validate_ai_config(environment)
            if not validation.valid:
                checkpoints.append(
                    _failure(
                        profile,
                        f"ai-{validation.reason_code or 'configuration'}",
                        "AI provider configuration is unsupported or incomplete; configure it and retry.",
                    )
                )
                services[profile] = {"status": "guided", "validation": validation.report}
                continue

        if profile == "subtitles" and bazarr_language is not None:
            if not isinstance(bazarr_language, str) or bazarr_language.strip().casefold() not in SUPPORTED_BAZARR_LANGUAGES:
                checkpoints.append(
                    _failure(
                        profile,
                        "bazarr-language-guided",
                        "The requested Bazarr language is outside the installer automation policy; configure it in Bazarr.",
                    )
                )
                services[profile] = {"status": "guided", "actions": ["handoff"]}
                continue

        tested = _check(tests.get(profile))
        if not tested:
            checkpoints.append(
                _failure(
                    profile,
                    f"{profile}-test-failed",
                    "The optional service test did not pass; the profile remains disabled.",
                )
            )
            services[profile] = {"status": "guided", "actions": ["test"]}
            continue
        healthy = _check(health.get(profile))
        if not healthy:
            checkpoints.append(
                _failure(
                    profile,
                    f"{profile}-health-failed",
                    "The optional service health check did not pass; the profile remains disabled.",
                )
            )
            services[profile] = {"status": "guided", "actions": ["test", "health"]}
            continue

        apply = configure.get(profile)
        if apply is not None:
            try:
                applied = apply()
            except Exception:
                applied = None
            applied_status = _check(lambda: applied)
            if not applied_status:
                checkpoints.append(
                    _failure(
                        profile,
                        f"{profile}-configure-failed",
                        "The optional service configuration did not complete; the profile remains disabled.",
                    )
                )
                services[profile] = {"status": "guided", "actions": ["test", "health", "configure"]}
                continue

        enabled.append(profile)
        service_update: dict[str, str] = {}
        if profile == "requests":
            service_update["JELLYSEERR_ENABLED"] = "true"
        elif profile == "subtitles":
            service_update["BAZARR_ENABLED"] = "true"
            service_update.update(_pending_links(environment, BAZARR_BASE_LINKS))
        elif profile == "indexer-tools":
            service_update.update(_pending_links(environment, {"FLARESOLVERR_URL": FLARESOLVERR_PROXY_URL}))
        elif profile == "ai":
            service_update["AI_ENABLED"] = "true"
        updates.update(service_update)
        services[profile] = {
            "status": "ok",
            "actions": ["test", "health", "enable"],
        }

    if not profiles:
        return OptionalProfileResult(status="ok")
    if checkpoints:
        status = "guided"
    else:
        status = "ok"
    return OptionalProfileResult(
        status=status,
        enabled_profiles=tuple(enabled),
        services=services,
        environment_update=updates,
        checkpoints=tuple(checkpoints),
    )


configure_optional = configure_optional_profiles
plan_optional_profiles = configure_optional_profiles
OptionalResult = OptionalProfileResult


__all__ = [
    "AiConfigValidation",
    "BAZARR_BASE_LINKS",
    "FLARESOLVERR_PROXY_URL",
    "OPTIONAL_PROFILES",
    "OptionalProfileError",
    "OptionalProfileResult",
    "OptionalResult",
    "SUPPORTED_AI_PROVIDERS",
    "SUPPORTED_BAZARR_LANGUAGES",
    "configure_optional",
    "configure_optional_profiles",
    "plan_optional_profiles",
    "validate_ai_config",
]
