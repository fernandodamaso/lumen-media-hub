"""Network exposure planning for the Linux installer.

This module is deliberately a pure planning boundary.  It does not write the
dotenv file or invoke Compose; callers can inspect the plan and decide when to
apply it.  Only network-owned keys are copied into a plan so an adopted
environment can never leak unrelated credentials through a report.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dotenv import DotEnvDocument
from .errors import DriftError, InvalidInputError


JELLYFIN_BIND_ADDRESS = "JELLYFIN_BIND_ADDRESS"
MANAGEMENT_BIND_ADDRESS = "MANAGEMENT_BIND_ADDRESS"
PUBLIC_HOST = "PUBLIC_HOST"
JELLYFIN_REMOTE_ACCESS = "JELLYFIN_REMOTE_ACCESS"

LOCAL_BIND_ADDRESS = "127.0.0.1"
LAN_BIND_ADDRESS = "0.0.0.0"
LOCAL_PUBLIC_HOST = "127.0.0.1"
_HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_NUMERIC_HOST = re.compile(r"^[0-9.]+$")


def _default_host_resolver(host: str) -> list[str]:
    """Resolve a hostname to address strings for safety validation.

    The resolver is deliberately a tiny boundary so tests and callers can
    inject deterministic answers.  DNS failures are handled by the caller as
    an unresolved-but-syntactically-valid hostname.
    """

    return [
        result[4][0]
        for result in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    ]


def _is_noncanonical_numeric_host(host: str) -> bool:
    """Identify legacy numeric forms that URL/DNS parsers interpret as IPs."""

    if host.isdigit():
        return True
    if not _NUMERIC_HOST.fullmatch(host):
        return False
    parts = host.split(".")
    if len(parts) != 4:
        return True
    return any(
        not part
        or (len(part) > 1 and part.startswith("0"))
        or int(part) > 255
        for part in parts
    )


def _is_loopback_alias(host: str) -> bool:
    """Recognize hostnames that encode a loopback IPv4 prefix."""

    parts = host.split(".")
    if len(parts) < 4 or not all(part.isdigit() for part in parts[:4]):
        return False
    prefix = parts[:4]
    if any(len(part) > 1 and part.startswith("0") for part in prefix):
        return prefix[0] == "127"
    try:
        address = ipaddress.ip_address(".".join(prefix))
    except ValueError:
        return False
    return address.is_loopback


def _resolved_addresses(results: Any) -> list[str]:
    """Extract address strings from common resolver/getaddrinfo results."""

    if results is None:
        return []
    if isinstance(results, str):
        return [results]
    addresses: list[str] = []
    for result in results:
        if isinstance(result, str):
            addresses.append(result)
        elif isinstance(result, Mapping):
            address = result.get("address")
            if isinstance(address, str):
                addresses.append(address)
        elif isinstance(result, (tuple, list)):
            # socket.getaddrinfo returns (..., sockaddr), where sockaddr's
            # first item is the address.  Also accept a simple (address, ...)
            # tuple from lightweight test resolvers.
            candidate = result[0] if result and isinstance(result[0], str) else None
            if candidate is None and result and isinstance(result[-1], (tuple, list)):
                candidate = result[-1][0] if result[-1] else None
            if isinstance(candidate, str):
                addresses.append(candidate)
    return addresses


def _validate_resolved_addresses(host: str, resolver: Any) -> None:
    try:
        results = resolver(host)
    except (OSError, socket.gaierror):
        # An unavailable DNS server must not make a syntactically valid host
        # unusable.  If it later resolves to an unsafe address, the next
        # explicit LAN planning attempt will reject it.
        return

    for value in _resolved_addresses(results):
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise InvalidInputError(
                f"{PUBLIC_HOST} resolver returned an invalid address for {host}"
            ) from exc
        broadcast = address.version == 4 and (
            int(address) == 0xFFFFFFFF or int(address) & 0xFF == 0xFF
        )
        if address.is_loopback:
            reason = "loopback"
        elif address.is_unspecified:
            reason = "unspecified"
        elif address.is_multicast:
            reason = "multicast"
        elif address.is_reserved:
            reason = "reserved"
        elif address.is_link_local:
            reason = "link-local"
        elif broadcast:
            reason = "broadcast"
        else:
            reason = None
        if reason is not None:
            raise InvalidInputError(
                f"{PUBLIC_HOST} hostname {host!r} resolves to an unsafe {reason} address"
            )


def _coerce_env(existing_env: Any) -> dict[str, str]:
    if existing_env is None:
        return {}
    if isinstance(existing_env, DotEnvDocument):
        values = existing_env.values
    elif isinstance(existing_env, Mapping):
        values = dict(existing_env)
    elif isinstance(existing_env, (str, bytes, Path)):
        values = DotEnvDocument.parse(existing_env).values
    else:
        raise TypeError("existing environment must be dotenv text, a mapping, or DotEnvDocument")

    result: dict[str, str] = {}
    for key, value in values.items():
        if value is None:
            continue
        result[str(key)] = str(value)
    return result


def _normalise_mode(requested_mode: Any) -> str | None:
    if requested_mode is None:
        return None
    if not isinstance(requested_mode, str):
        raise InvalidInputError("network mode must be local or lan")
    mode = requested_mode.strip().lower().replace("_", "-")
    if not mode:
        return None
    aliases = {"preserve": "preserve-lan", "legacy": "preserve-lan"}
    mode = aliases.get(mode, mode)
    if mode not in {"local", "lan", "preserve-lan"}:
        raise InvalidInputError("network mode must be local or lan")
    return mode


def _validated_host(
    value: Any,
    *,
    field: str = PUBLIC_HOST,
    allow_local: bool = False,
    resolver: Any = None,
) -> str:
    if not isinstance(value, str):
        raise InvalidInputError(f"{field} must be a hostname or IP address")
    host = value.strip()
    if not host or host != value:
        raise InvalidInputError(f"{field} must not contain whitespace")
    if any(character.isspace() for character in host):
        raise InvalidInputError(f"{field} must not contain whitespace")
    if any(character in host for character in ("/", "?", "#", "@")) or "://" in host:
        raise InvalidInputError(f"{field} must be a hostname or IP address without a URL")
    if _is_noncanonical_numeric_host(host):
        raise InvalidInputError(f"{field} must use a canonical IPv4 literal")
    if not allow_local and _is_loopback_alias(host):
        raise InvalidInputError(f"{field} must be reachable from the LAN, not localhost")

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        if address.version == 6:
            raise InvalidInputError(
                f"{field} IPv6 literals are not supported in v1 public URLs"
            )
        if address.is_loopback and not allow_local:
            raise InvalidInputError(f"{field} must not be a loopback address")
        # A v1 installer cannot know the user's subnet, so reject the
        # conventional directed-broadcast suffix as well as limited
        # broadcast.  It is never a usable destination for a public URL.
        if (
            address.is_unspecified
            or address.is_multicast
            or int(address) == 0xFFFFFFFF
            or int(address) & 0xFF == 0xFF
        ):
            raise InvalidInputError(f"{field} must not be wildcard, multicast, or broadcast")
        return host

    # Colons are only accepted as part of a parsed IPv6 literal.  This rejects
    # host:port values without making URL parsing part of the Compose contract.
    if ":" in host or len(host) > 253 or host.startswith(".") or host.endswith("."):
        raise InvalidInputError(f"{field} must be a hostname or IP address without a port")
    labels = host.split(".")
    if any(not label or not _HOST_LABEL.fullmatch(label) for label in labels):
        raise InvalidInputError(f"{field} must be a usable hostname or IP address")
    lowered = host.lower()
    local_alias = (
        lowered == "localhost"
        or lowered.startswith("localhost.")
        or lowered.endswith(".localhost")
        or lowered.endswith(".localdomain")
        or lowered in {"localhost6", "ip6-localhost", "ip6-loopback"}
    )
    if lowered == "*" or (not allow_local and local_alias):
        raise InvalidInputError(f"{field} must be reachable from the LAN, not localhost")
    if not allow_local and resolver is not None:
        _validate_resolved_addresses(host, resolver)
    return host


def _validated_bind(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise InvalidInputError(f"{field} must be a bind address")
    bind = value.strip()
    if not bind or bind != value or any(character.isspace() for character in bind):
        raise InvalidInputError(f"{field} must be a bind address without whitespace")
    if any(character in bind for character in ("/", "?", "#", "@")) or "://" in bind:
        raise InvalidInputError(f"{field} must be a bind address, not a URL")
    try:
        address = ipaddress.ip_address(bind)
    except ValueError as exc:
        raise InvalidInputError(
            f"{field} must be a Compose-compatible IPv4 literal"
        ) from exc
    if address.version != 4:
        raise InvalidInputError(f"{field} IPv6 literals are not supported in v1 bindings")
    return bind


def _bool_text(value: Any, *, field: str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str) and value.strip().lower() in {"true", "1", "yes", "on"}:
        return "true"
    if isinstance(value, str) and value.strip().lower() in {"false", "0", "no", "off"}:
        return "false"
    raise InvalidInputError(f"{field} must be true or false")


@dataclass(frozen=True)
class NetworkPlan:
    """Secret-safe network values and any migration decision required."""

    values: dict[str, str]
    drift: tuple[dict[str, str], ...] = ()
    decision: dict[str, Any] | None = None
    requested_mode: str | None = None

    @property
    def remote_access(self) -> bool:
        return self.values[JELLYFIN_REMOTE_ACCESS] == "true"

    @property
    def jellyfin_remote_access(self) -> bool:
        return self.remote_access

    @property
    def drift_records(self) -> tuple[dict[str, str], ...]:
        return self.drift

    @property
    def display(self) -> dict[str, Any]:
        return {
            "values": dict(self.values),
            "drift": [dict(record) for record in self.drift],
            "decision": dict(self.decision) if self.decision is not None else None,
        }

    @property
    def report(self) -> dict[str, Any]:
        return self.display

    @property
    def redacted(self) -> dict[str, Any]:
        return self.display

    @property
    def warning(self) -> str | None:
        """Human-visible adoption warning, when legacy drift is present."""

        if self.decision is None:
            return None
        message = self.decision.get("message")
        return str(message) if message else None

    def __getitem__(self, key: str) -> str:
        return self.values[key]


def _record(key: str, old: Any, new: Any, *, kind: str, reason: str) -> dict[str, str]:
    return {
        "key": key,
        "kind": kind,
        "old": "<unset>" if old is None else str(old),
        "new": str(new),
        "reason": reason,
    }


def plan_network(
    existing_env: Any,
    requested_mode: str | None,
    public_host: str | None,
    interactive: bool,
    *,
    resolver: Any = None,
) -> NetworkPlan:
    """Plan local/LAN exposure and explicit legacy Jellyfin adoption.

    ``requested_mode=None`` means no reconciliation choice was supplied.  On
    a fresh environment this safely means local; on an adopted environment
    missing ``JELLYFIN_BIND_ADDRESS`` it is an unresolved legacy-LAN decision.
    Interactive callers receive a plan preserving LAN exposure plus a
    preserve-LAN/local choice record.  Noninteractive callers receive the
    stable exit-code-3 :class:`DriftError` before any values are returned.
    """

    env = _coerce_env(existing_env)
    mode = _normalise_mode(requested_mode)
    adopted = bool(env)
    explicit_jellyfin = env.get(JELLYFIN_BIND_ADDRESS)
    legacy = adopted and not (isinstance(explicit_jellyfin, str) and explicit_jellyfin.strip())
    drift: list[dict[str, str]] = []

    existing_jellyfin = (
        _validated_bind(explicit_jellyfin, field=JELLYFIN_BIND_ADDRESS)
        if not legacy and explicit_jellyfin is not None
        else None
    )
    existing_management = env.get(MANAGEMENT_BIND_ADDRESS)
    management_legacy = adopted and not (
        isinstance(existing_management, str) and existing_management.strip()
    )
    if not management_legacy and existing_management is not None:
        existing_management = _validated_bind(
            existing_management, field=MANAGEMENT_BIND_ADDRESS
        )
    else:
        existing_management = None
    existing_remote = env.get(JELLYFIN_REMOTE_ACCESS)
    if isinstance(existing_remote, str) and existing_remote.strip():
        existing_remote = _bool_text(existing_remote, field=JELLYFIN_REMOTE_ACCESS)
    else:
        existing_remote = None

    legacy_network = legacy or management_legacy
    if legacy_network and mode is None:
        if not interactive:
            missing = " and ".join(
                key
                for key, is_missing in (
                    (JELLYFIN_BIND_ADDRESS, legacy),
                    (MANAGEMENT_BIND_ADDRESS, management_legacy),
                )
                if is_missing
            )
            raise DriftError(
                f"{missing} is missing from an adopted environment; "
                "choose preserve-LAN or local before Compose mutation"
            )
        # Select the effective mode before validating PUBLIC_HOST.  An
        # adopted interactive plan is a preserve-LAN checkpoint, so a
        # loopback host must not slip through as if the plan were local.
        selected_mode = "preserve-lan"
        selected = None
    else:
        selected_mode = mode
        selected = mode

    # Existing and supplied hosts are validated against the effective mode,
    # including the implicit preserve-LAN choice above.  DNS resolution is
    # intentionally limited to LAN validation; local planning never performs
    # a surprising network lookup.
    allow_local_host = selected_mode not in {"lan", "preserve-lan"}
    host_resolver = resolver if resolver is not None else _default_host_resolver
    existing_public = env.get(PUBLIC_HOST)
    if isinstance(existing_public, str) and existing_public.strip():
        existing_public = _validated_host(
            existing_public,
            allow_local=allow_local_host,
            resolver=host_resolver,
        )
    else:
        existing_public = None

    # Validate an explicitly supplied host even when the caller is selecting
    # local exposure.  This keeps externally constructed URLs safe and makes a
    # typo fail before any Compose mutation.
    supplied_public = None
    if public_host is not None:
        supplied_public = _validated_host(
            public_host,
            allow_local=allow_local_host,
            resolver=host_resolver,
        )

    if legacy:
        drift.append(
            _record(
                JELLYFIN_BIND_ADDRESS,
                None,
                LAN_BIND_ADDRESS,
                kind="legacy-lan",
                reason=(
                    "adopted environment predates explicit Jellyfin binding; "
                    "the previous Compose publication was all-interface"
                ),
            )
        )
    if management_legacy:
        drift.append(
            _record(
                MANAGEMENT_BIND_ADDRESS,
                None,
                LAN_BIND_ADDRESS,
                kind="legacy-lan",
                reason=(
                    "adopted environment predates an explicit management bind; "
                    "preserve its prior all-interface publication"
                ),
            )
        )

    if selected_mode is None:
        effective_jellyfin = existing_jellyfin or LOCAL_BIND_ADDRESS
    elif selected_mode == "local":
        effective_jellyfin = LOCAL_BIND_ADDRESS
    elif selected_mode == "preserve-lan" and selected is None and not legacy:
        # A management-only legacy checkpoint must not rewrite an explicit
        # Jellyfin bind while preserving the missing management publication.
        effective_jellyfin = existing_jellyfin or LAN_BIND_ADDRESS
    else:
        # Explicit LAN is intentionally all-interface for Jellyfin.  The
        # management bind remains an independent safety control and defaults
        # to loopback unless an adopted value already set it otherwise.
        effective_jellyfin = LAN_BIND_ADDRESS

    if explicit_jellyfin and selected_mode is not None and effective_jellyfin != existing_jellyfin:
        drift.append(
            _record(
                JELLYFIN_BIND_ADDRESS,
                existing_jellyfin,
                effective_jellyfin,
                kind="reconciliation",
                reason=f"requested {selected_mode} network exposure",
            )
        )

    if legacy and selected_mode == "local":
        drift.append(
            _record(
                JELLYFIN_BIND_ADDRESS,
                None,
                LOCAL_BIND_ADDRESS,
                kind="reconciliation",
                reason="legacy adoption explicitly changed to local exposure",
            )
        )

    # LAN and preserve-LAN both need a reachable public host.  An already
    # configured host is accepted after the same strict validation.
    if selected_mode in {"lan", "preserve-lan"}:
        effective_public = supplied_public or existing_public
        if effective_public is None:
            if legacy_network and selected is None:
                # The interactive checkpoint has not selected LAN yet.  Keep
                # the report usable without inventing a remote hostname.
                effective_public = LOCAL_PUBLIC_HOST
            else:
                raise InvalidInputError(
                    "LAN network mode requires a non-wildcard public hostname or IP address"
                )
    else:
        effective_public = supplied_public or existing_public or LOCAL_PUBLIC_HOST

    effective_management = existing_management or (
        LAN_BIND_ADDRESS
        if legacy_network and selected_mode != "local"
        else LOCAL_BIND_ADDRESS
    )
    if selected_mode is None:
        inferred_remote = "true" if effective_jellyfin == LAN_BIND_ADDRESS else "false"
        effective_remote = existing_remote or inferred_remote
    else:
        effective_remote = "true" if effective_jellyfin == LAN_BIND_ADDRESS else "false"

    if (
        existing_remote is not None
        and selected_mode is None
        and existing_remote != effective_remote
    ):
        drift.append(
            _record(
                JELLYFIN_REMOTE_ACCESS,
                existing_remote,
                effective_remote,
                kind="inconsistent-intent",
                reason="remote-access intent does not match the existing Jellyfin bind",
            )
        )

    decision: dict[str, Any] | None = None
    if legacy_network:
        code = "legacy-jellyfin-binding" if legacy else "legacy-management-binding"
        missing = " and ".join(
            key
            for key, is_missing in (
                (JELLYFIN_BIND_ADDRESS, legacy),
                (MANAGEMENT_BIND_ADDRESS, management_legacy),
            )
            if is_missing
        )
        decision = {
            "code": code,
            "message": (
                f"Adopted environment is missing {missing}; "
                "choose whether to preserve its legacy LAN exposure or use local-only access. "
                "An absent MANAGEMENT_BIND_ADDRESS is also preserved as all-interface exposure."
            ),
            "options": ("preserve-lan", "local"),
            "selected": selected,
            "default": "preserve-lan",
            "severity": "warning",
        }

    return NetworkPlan(
        values={
            JELLYFIN_BIND_ADDRESS: effective_jellyfin,
            MANAGEMENT_BIND_ADDRESS: effective_management,
            PUBLIC_HOST: effective_public,
            JELLYFIN_REMOTE_ACCESS: effective_remote,
        },
        drift=tuple(drift),
        decision=decision,
        requested_mode=mode,
    )


__all__ = [
    "JELLYFIN_BIND_ADDRESS",
    "JELLYFIN_REMOTE_ACCESS",
    "LAN_BIND_ADDRESS",
    "LOCAL_BIND_ADDRESS",
    "LOCAL_PUBLIC_HOST",
    "MANAGEMENT_BIND_ADDRESS",
    "NetworkPlan",
    "PUBLIC_HOST",
    "plan_network",
]
