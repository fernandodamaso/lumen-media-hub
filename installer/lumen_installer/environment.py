"""Pure planning for the installer-managed portion of ``.env``."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .dotenv import DotEnvDocument
from .secrets import ensure_actions_token


_MISSING = object()
_REDACTED = "<redacted>"
_SECRET_MARKERS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
)
_DISPLAY_SAFE_KEYS = frozenset(
    {
        "PUID",
        "PGID",
        "TZ",
        "ROOT_PATH",
        "DOWNLOADS_PATH",
        "UMASK",
    }
)


def _is_secret_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    return any(marker in normalized for marker in _SECRET_MARKERS)


def _mapping_get(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        if key in source:
            return source[key]
        upper = key.upper()
        if upper in source:
            return source[upper]
        lower = key.lower()
        if lower in source:
            return source[lower]
        return default
    getter = getattr(source, "get", None)
    if callable(getter):
        value = getter(key, default)
        if value is not default:
            return value
        value = getter(key.upper(), default)
        if value is not default:
            return value
    return getattr(source, key, default)


def _present(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip())


def _host_value(host: Any, key: str) -> Any:
    value = _mapping_get(host, key, _MISSING)
    if value is not _MISSING:
        return value
    # HostFacts names these fields in lowercase, while dotenv keys are upper.
    return _mapping_get(host, key.lower(), None)


def _answer_value(answers: Any, key: str) -> Any:
    value = _mapping_get(answers, key, _MISSING)
    if value is not _MISSING:
        return value
    return _mapping_get(answers, key.lower(), None)


def _scalar(value: Any) -> str | None:
    if not _present(value):
        return None
    if isinstance(value, (Mapping, list, tuple, set)):
        # Secret answer references are resolved by Resolver before this plan;
        # never stringify a reference object into an environment file.
        return None
    return str(value)


def _same_fact(key: str, old: Any, new: Any) -> bool:
    if key in {"PUID", "PGID"}:
        try:
            return int(str(old).strip(), 10) == int(str(new).strip(), 10)
        except (TypeError, ValueError):
            return str(old) == str(new)
    return str(old).strip() == str(new).strip()


def _normalise_path(value: Any) -> str | None:
    scalar = _scalar(value)
    if scalar is None:
        return None
    return Path(os.path.expandvars(os.path.expanduser(scalar))).resolve(strict=False).as_posix()


@dataclass(frozen=True)
class EnvironmentChange:
    """One planned edit; actual values are available to the apply layer only."""

    key: str
    previous: Any
    value: Any
    action: str = "update"
    reason: str = ""
    secret: bool = False

    @property
    def old(self) -> Any:
        return self.previous

    @property
    def new(self) -> Any:
        return self.value

    @property
    def before(self) -> Any:
        return self.previous

    @property
    def after(self) -> Any:
        return self.value

    def redacted(self) -> dict[str, Any]:
        if self.previous is _MISSING:
            old = "<unset>"
        else:
            old = (
                _REDACTED
                if self.secret or self.key not in _DISPLAY_SAFE_KEYS
                else self.previous
            )
        new = _REDACTED if self.secret or self.key not in _DISPLAY_SAFE_KEYS else self.value
        return {
            "key": self.key,
            "action": self.action,
            "reason": self.reason,
            "secret": self.secret,
            "old": old,
            "new": new,
        }

    @property
    def display(self) -> dict[str, Any]:
        return self.redacted()

    def __repr__(self) -> str:
        return f"EnvironmentChange(key={self.key!r}, action={self.action!r}, secret={self.secret!r})"


@dataclass
class EnvironmentPlan:
    """Merged dotenv document plus secret-free display/report projections."""

    document: DotEnvDocument
    changes: tuple[EnvironmentChange, ...] = field(default_factory=tuple)
    drift: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    fresh_setup: bool = False

    @property
    def values(self) -> dict[str, str]:
        return self.document.values

    @property
    def env(self) -> dict[str, str]:
        return self.values

    @property
    def change_records(self) -> tuple[EnvironmentChange, ...]:
        return self.changes

    @property
    def display(self) -> dict[str, Any]:
        values = {
            key: (
                value
                if key in _DISPLAY_SAFE_KEYS and not _is_secret_key(key)
                else _REDACTED
            )
            for key, value in self.values.items()
        }
        drift = []
        for record in self.drift:
            key = str(record.get("key", ""))
            if key in _DISPLAY_SAFE_KEYS and not _is_secret_key(key):
                drift.append(
                    {
                        field: record[field]
                        for field in ("key", "kind", "reason", "old", "new")
                        if field in record
                    }
                )
            else:
                drift.append(
                    {
                        "key": key,
                        "kind": record.get("kind", "drift"),
                        "reason": record.get("reason", ""),
                    }
                )
        return {
            "fresh_setup": self.fresh_setup,
            "values": values,
            "changes": [change.redacted() for change in self.changes],
            "drift": drift,
        }

    @property
    def display_projection(self) -> dict[str, Any]:
        return self.display

    @property
    def redacted(self) -> dict[str, Any]:
        return self.display

    @property
    def drift_records(self) -> tuple[dict[str, Any], ...]:
        return self.drift

    @property
    def report(self) -> dict[str, Any]:
        return self.display

    def render(self) -> str:
        return self.document.render()

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def __getitem__(self, key: str) -> str:
        return self.values[key]

    def __contains__(self, key: object) -> bool:
        return key in self.values

    def __repr__(self) -> str:
        return (
            f"EnvironmentPlan(fresh_setup={self.fresh_setup!r}, "
            f"keys={list(self.values)!r}, changes={len(self.changes)}, "
            f"drift={len(self.drift)})"
        )


def _coerce_document(existing: Any) -> DotEnvDocument:
    if isinstance(existing, DotEnvDocument):
        return existing.copy()
    if existing is None:
        return DotEnvDocument.parse("")
    if isinstance(existing, (str, bytes, Path)):
        return DotEnvDocument.parse(existing)
    if isinstance(existing, Mapping):
        document = DotEnvDocument.parse("")
        for key, value in existing.items():
            document.set(str(key), value)
        return document
    raise TypeError("existing environment must be dotenv text, a mapping, or DotEnvDocument")


def plan_environment(existing: Any, host: Any, answers: Any) -> EnvironmentPlan:
    """Plan safe environment migration without logging secret values.

    Existing owner and timezone values are authoritative.  When they differ
    from current host facts the old value remains in the resulting document and
    a drift record is emitted for an interactive caller to decide later.
    """

    document = _coerce_document(existing)
    original_values = document.values
    fresh_setup = not bool(original_values)
    changes: list[EnvironmentChange] = []
    drift: list[dict[str, Any]] = []

    def put(key: str, value: Any, *, secret: bool = False, reason: str = "") -> None:
        scalar = _scalar(value)
        if scalar is None:
            return
        previous = document.get(key, _MISSING)
        if previous is not _MISSING and str(previous) == scalar:
            return
        document.set(key, scalar)
        changes.append(
            EnvironmentChange(
                key=key,
                previous=previous,
                value=scalar,
                action="add" if previous is _MISSING else "update",
                reason=reason,
                secret=secret or _is_secret_key(key),
            )
        )

    # Existing values win.  Missing values are filled from immutable host
    # facts on both fresh and adopted environments.
    for key, host_key in (("PUID", "uid"), ("PGID", "gid"), ("TZ", "timezone")):
        detected = _scalar(_host_value(host, host_key))
        if detected is None:
            continue
        current = document.get(key, _MISSING)
        if current is _MISSING or not _present(current):
            put(key, detected, reason="detected host fact")
        elif not _same_fact(key, current, detected):
            drift.append(
                {
                    "key": key,
                    "kind": "drift",
                    "old": current,
                    "new": detected,
                    "existing": current,
                    "detected": detected,
                    "reason": "existing value preserved",
                }
            )

    for key in ("ROOT_PATH", "DOWNLOADS_PATH"):
        configured = _answer_value(answers, key)
        if not _present(configured):
            configured = document.get(key, None)
        normalized = _normalise_path(configured)
        if normalized is not None:
            put(key, normalized, reason="normalized absolute path")

    # Fresh setup takes one password answer and deliberately writes both names
    # for compatibility.  Adopted installations retain their alias exactly;
    # only a missing authoritative QBT_PASSWORD is backfilled from the legacy
    # alias so the next service adapter can authenticate.
    if fresh_setup:
        password = _answer_value(answers, "QBT_PASSWORD")
        if not _present(password):
            password = _answer_value(answers, "STACK_PASSWORD")
        if _present(password) and _scalar(password) is not None:
            put("QBT_PASSWORD", password, secret=True, reason="fresh setup credential")
            put("STACK_PASSWORD", password, secret=True, reason="fresh setup compatibility alias")
    elif not _present(document.get("QBT_PASSWORD", None)) and _present(document.get("STACK_PASSWORD", None)):
        put(
            "QBT_PASSWORD",
            document.get("STACK_PASSWORD"),
            secret=True,
            reason="legacy compatibility alias",
        )

    token = ensure_actions_token(document.get("ACTIONS_TOKEN", None))
    put("ACTIONS_TOKEN", token, secret=True, reason="generated installer token")

    return EnvironmentPlan(
        document=document,
        changes=tuple(changes),
        drift=tuple(drift),
        fresh_setup=fresh_setup,
    )


__all__ = ["EnvironmentChange", "EnvironmentPlan", "plan_environment"]
