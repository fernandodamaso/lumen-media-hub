"""Storage Guardian read-only cleanup preview route."""
import json
from datetime import datetime, timezone

import config as settings
from http_support import _BodyTooLarge, _read_json_body, send_json
from routes.resources import _disk_stats
from storage_cleanup import (
    CleanupInventoryError,
    CleanupValidationError,
    evaluate_cleanup_preview,
    fetch_jellyfin_cleanup_inventory,
    validate_cleanup_request,
)


def handle_cleanup_preview(handler):
    try:
        raw = _read_json_body(handler)
    except (_BodyTooLarge, UnicodeDecodeError, json.JSONDecodeError):
        send_json(handler, 400, {"ok": False, "error": "Invalid JSON"})
        return

    try:
        policy = validate_cleanup_request(raw)
    except CleanupValidationError as error:
        send_json(handler, 400, {"ok": False, "error": str(error)})
        return

    disk = _disk_stats()
    if not isinstance(disk, dict):
        send_json(handler, 503, {"ok": False, "error": "Storage capacity is unavailable"})
        return

    try:
        inventory = fetch_jellyfin_cleanup_inventory()
        preview = evaluate_cleanup_preview(
            inventory,
            {
                "total": disk.get("total"),
                "used": disk.get("used"),
                "free": disk.get("free"),
            },
            policy,
            evaluated_at=datetime.now(timezone.utc),
            jellyfin_external_url=settings.JELLYFIN_EXTERNAL_URL,
        )
    except CleanupInventoryError as error:
        send_json(handler, 502, {"ok": False, "error": str(error)})
        return
    except Exception:
        # Fail closed without reflecting private upstream payloads or paths.
        send_json(handler, 502, {"ok": False, "error": "Storage cleanup preview is temporarily unavailable"})
        return

    send_json(handler, 200, preview)
