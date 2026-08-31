"""Network exposure planning for the Linux installer.

This module is deliberately a pure planning boundary.  It does not write the
dotenv file or invoke Compose; callers can inspect the plan and decide when to
apply it.  Only network-owned keys are copied into a plan so an adopted
environment can never leak unrelated credentials through a report.
"""

from __future__ import annotations

import ipaddress
import re
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
_NETWORK_KEYS = (
    JELLYFIN_BIND_ADDRESS,
    MANAGEMENT_BIND_ADDRESS,
    PUBLIC_HOST,
    JELLYFIN_REMOTE_ACCESS,
)
_HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


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


def _validated_host(value: Any, *, field: str = PUBLIC_HOST) -> str:
    if not isinstance(value, str):
        raise InvalidInputError(f"{field} must be a hostname or IP address")
    host = value.strip()
    if not host or host != value:
        raise InvalidInputError(f"{field} must not contain whitespace")
    if any(character.isspace() for character in host):
        raise InvalidInputError(f"{field} must not contain whitespace")
    if any(character in host for character in ("/", "?", "#", "@")) or "://" in host:
        raise InvalidInputError(f"{field} must be a hostname or IP address without a URL")

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        if address.is_unspecified or address.is_multicast:
            raise InvalidInputError(f"{field} must not be a wildcard or multicast address")
        return host

    # Colons are only accepted as part of a parsed IPv6 literal.  This rejects
    # host:port values without making URL parsing part of the Compose contract.
    if ":" in host or len(host) > 253 or host.startswith(".") or host.endswith("."):
        raise InvalidInputError(f"{field} must be a hostname or IP address without a port")
    labels = host.split(".")
    if any(not label or not _HOST_LABEL.fullmatch(label) for label in labels):
        raise InvalidInputError(f"{field} must be a usable hostname or IP address")
    if host.lower() in {"*", "0.0.0.0", "::"}:
        raise InvalidInputError(f"{field} must not be a wildcard address")
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
        ipaddress.ip_address(bind)
        return bind
    except ValueError:
        pass
    if ":" in bind or len(bind) > 253:
        raise InvalidInputError(f"{field} must be an IP address or hostname without a port")
    labels = bind.split(".")
    if any(not label or not _HOST_LABEL.fullmatch(label) for label in labels):
        raise InvalidInputError(f"{field} must be an IP address or hostname")
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
    legacy = adopted and not explicit_jellyfin
    drift: list[dict[str, str]] = []

    existing_jellyfin = (
        _validated_bind(explicit_jellyfin, field=JELLYFIN_BIND_ADDRESS)
        if explicit_jellyfin
        else None
    )
    existing_management = env.get(MANAGEMENT_BIND_ADDRESS)
    if existing_management is not None:
        existing_management = _validated_bind(
            existing_management, field=MANAGEMENT_BIND_ADDRESS
        )
    existing_public = env.get(PUBLIC_HOST)
    if existing_public is not None:
        existing_public = _validated_host(existing_public)
    existing_remote = env.get(JELLYFIN_REMOTE_ACCESS)
    if existing_remote is not None:
        existing_remote = _bool_text(existing_remote, field=JELLYFIN_REMOTE_ACCESS)

    # Validate an explicitly supplied host even when the caller is selecting
    # local exposure.  This keeps externally constructed URLs safe and makes a
    # typo fail before any Compose mutation.
    supplied_public = None
    if public_host is not None:
        supplied_public = _validated_host(public_host)

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
        if mode is None:
            if not interactive:
                raise DriftError(
                    "JELLYFIN_BIND_ADDRESS is missing from an adopted environment; "
                    "choose preserve-LAN or local before Compose mutation"
                )
            selected_mode = "preserve-lan"
            selected = None
        else:
            selected_mode = mode
            selected = mode
    else:
        selected_mode = mode
        selected = mode

    if selected_mode is None:
        effective_jellyfin = existing_jellyfin or LOCAL_BIND_ADDRESS
    elif selected_mode == "local":
        effective_jellyfin = LOCAL_BIND_ADDRESS
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
            if legacy and selected is None:
                # The interactive checkpoint has not selected LAN yet.  Keep
                # the report usable without inventing a remote hostname.
                effective_public = LOCAL_PUBLIC_HOST
            else:
                raise InvalidInputError(
                    "LAN network mode requires a non-wildcard public hostname or IP address"
                )
    else:
        effective_public = supplied_public or existing_public or LOCAL_PUBLIC_HOST

    effective_management = existing_management or LOCAL_BIND_ADDRESS
    if selected_mode is None:
        effective_remote = existing_remote or ("true" if effective_jellyfin == LAN_BIND_ADDRESS else "false")
    else:
        effective_remote = "true" if effective_jellyfin == LAN_BIND_ADDRESS else "false"

    if existing_remote is not None and selected_mode is None and existing_remote != effective_remote:
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
    if legacy:
        decision = {
            "code": "legacy-jellyfin-binding",
            "message": (
                "Adopted environment is missing JELLYFIN_BIND_ADDRESS; "
                "choose whether to preserve its legacy LAN exposure or use local-only access."
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
