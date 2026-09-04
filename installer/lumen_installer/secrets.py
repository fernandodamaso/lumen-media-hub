"""Secret-safe generation helpers for installer-owned environment values."""

from __future__ import annotations

import re
import secrets as _stdlib_secrets
from typing import Any


# Keep the standard-library module available under its conventional name and
# expose a thin function wrapper so either dependency-injection seam remains
# useful to callers.  The wrapper never records or prints its return value.
secrets = _stdlib_secrets


def token_hex(nbytes: int | None = None) -> str:
    return secrets.token_hex(nbytes)

_PLACEHOLDER_VALUES = frozenset(
    {
        "",
        "changeme",
        "change-me",
        "change_me",
        "your-actions-token",
        "your_actions_token",
        "your actions token",
        "actions-token",
        "actions_token",
        "your-token",
        "your_token",
        "replace-me",
        "replace_me",
        "placeholder",
        "token",
        "<actions-token>",
        "<your-actions-token>",
        "${actions_token}",
        "${actions-token}",
    }
)


def _is_placeholder(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    lowered = candidate.lower()
    if lowered in _PLACEHOLDER_VALUES:
        return True
    if lowered.startswith(("your-", "your_", "replace-", "replace_")):
        return True
    if re.fullmatch(r"<[^>]+>", candidate):
        return True
    if re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}", candidate):
        return True
    return False


def ensure_actions_token(existing: Any = None) -> str:
    """Preserve a configured token or generate 32 random bytes for placeholders."""

    if not _is_placeholder(existing):
        return str(existing)
    return token_hex(32)


__all__ = ["ensure_actions_token", "secrets", "token_hex"]
