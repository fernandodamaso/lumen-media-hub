"""Interactive terminal prompts for the Linux installer."""

from __future__ import annotations

import getpass
import re
from typing import Any

_SECRET_FIELD = re.compile(
    r"(?:password|secret|token|api[_-]?key|credential|cookie|private[_-]?key|oauth)",
    re.IGNORECASE,
)


def terminal_prompt(name: str, default: Any = None) -> Any:
    """Read one installer value, hiding credential-like fields from the TTY."""

    field = str(name).strip()
    if not field:
        raise ValueError("prompt field is required")
    label = field.replace("_", " ").title()
    if _SECRET_FIELD.search(field):
        value = getpass.getpass(f"{label}: ")
    else:
        suffix = f" [{default}]" if default is not None else ""
        value = input(f"{label}{suffix}: ")
    return value if value != "" else default


__all__ = ["terminal_prompt"]
