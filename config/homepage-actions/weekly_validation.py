"""Tracked, testable diagnostics for the Weekly Validate Final maintenance job.

This module owns the pieces of Weekly Validate that need precise, repeatable
results and regression tests: Jellyfin readiness/authentication/library checks
and the current tracked-documentation contract. The host-local
``scripts/validate-final.ps1`` (git-ignored by repository policy) invokes this
module as a child process and maps its sanitized states to report rows.

No secrets, account identifiers, item identifiers, or raw media history are
ever returned here. ``main()`` prints one compact JSON result to stdout and
returns a nonzero exit code when a hard failure is present.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

EXPECTED_LIBRARIES = ("Movies", "TV Shows")

DOCUMENTATION_PATHS = (
    "README.md",
    "dashboard-app/docs/architecture.md",
    "dashboard-app/docs/quality-gates.md",
)

STATUS_READY = "ready"
STATUS_TIMEOUT = "timeout"
STATUS_UNAVAILABLE = "unavailable"
STATUS_NOT_CHECKED = "not_checked"


def _library_names(payload):
    if not isinstance(payload, list):
        return None
    names = []
    for item in payload:
        if isinstance(item, dict) and isinstance(item.get("Name"), str):
            names.append(item["Name"])
    return names


def validate_jellyfin(base_url, api_key, attempts=6, delay_seconds=5, timeout=10):
    """Probe Jellyfin readiness, authentication, and libraries.

    Retries HTTP 503, connection, and timeout failures up to ``attempts``
    times with ``delay_seconds`` between attempts. Stops immediately on
    HTTP 401/403 (service responded but the API key is rejected).

    Returns only sanitized states:
    - readiness: ready | timeout | unavailable | not_checked
    - authentication: ok | missing_configuration | failed | not_checked
    - libraries: ok | missing | not_checked (with a ``missing`` list of only
      expected library names)
    """
    failure = {
        "readiness": {"status": STATUS_NOT_CHECKED},
        "authentication": {"status": STATUS_NOT_CHECKED},
        "libraries": {"status": STATUS_NOT_CHECKED, "missing": []},
    }
    if not base_url:
        failure["readiness"]["status"] = STATUS_UNAVAILABLE
        return failure
    if not api_key:
        failure["authentication"]["status"] = "missing_configuration"
        return failure

    url = base_url.rstrip("/") + "/Library/VirtualFolders"
    for attempt in range(attempts):
        req = urllib.request.Request(url)
        req.add_header("X-Emby-Token", api_key)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                # Service is up; authentication is rejected.
                return {
                    "readiness": {"status": STATUS_READY},
                    "authentication": {"status": "failed"},
                    "libraries": {"status": STATUS_NOT_CHECKED, "missing": []},
                }
            # Any other HTTP error is transient unreadiness.
            if attempt < attempts - 1:
                time.sleep(delay_seconds)
            continue
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt < attempts - 1:
                time.sleep(delay_seconds)
            continue

        # A 200 response proves readiness and authentication.
        names = None
        try:
            names = _library_names(json.loads(raw.decode("utf-8", errors="replace")))
        except (json.JSONDecodeError, ValueError):
            names = None
        if names is None:
            # Invalid/malformed body: treat as transient unreadiness.
            if attempt < attempts - 1:
                time.sleep(delay_seconds)
            continue
        missing = [name for name in EXPECTED_LIBRARIES if name not in names]
        return {
            "readiness": {"status": STATUS_READY},
            "authentication": {"status": "ok"},
            "libraries": {
                "status": "ok" if not missing else "missing",
                "missing": missing,
            },
        }

    # All transient attempts exhausted without a successful 200.
    return {
        "readiness": {"status": STATUS_TIMEOUT},
        "authentication": {"status": STATUS_NOT_CHECKED},
        "libraries": {"status": STATUS_NOT_CHECKED, "missing": []},
    }


def validate_documentation(project_root):
    """Confirm the current tracked product documents exist.

    Returns ``{ "status": ok|missing, "missing": [relative paths] }``.
    Never requires legacy scripts, credentials, GPU model strings, local
    operations text, or the ignored ``docs/`` directory.
    """
    root = Path(project_root or ".")
    missing = []
    for relative in DOCUMENTATION_PATHS:
        if not (root / relative).is_file():
            missing.append(relative)
    return {
        "status": "ok" if not missing else "missing",
        "missing": missing,
    }


def main():
    base_url = os.environ.get("JELLYFIN_URL", "").strip()
    api_key = os.environ.get("JELLYFIN_API_KEY", "").strip()
    project_root = os.environ.get("PROJECT_ROOT", os.getcwd())
    result = {
        "jellyfin": validate_jellyfin(base_url, api_key),
        "documentation": validate_documentation(project_root),
    }
    print(json.dumps(result, separators=(",", ":"), ensure_ascii=False))

    hard = 0
    jf = result["jellyfin"]
    if jf["readiness"]["status"] in (STATUS_TIMEOUT, STATUS_UNAVAILABLE):
        hard += 1
    if jf["authentication"]["status"] in ("failed", "missing_configuration"):
        hard += 1
    if jf["libraries"]["status"] == "missing":
        hard += 1
    if result["documentation"]["status"] == "missing":
        hard += 1
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
