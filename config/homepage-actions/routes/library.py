"""Library deletion route handlers."""
import sys

import config as settings
from http_support import send_json
from library_delete import (
    ConflictError,
    MatchError,
    PREVIEW_STORE,
    UpstreamError,
    execute_library_delete,
    resolve_library_target,
)


def handle_library_delete_preview(handler, item_id):
    if not settings.JELLYFIN_API_KEY:
        send_json(handler, 502, {"ok": False, "error": "Unable to prepare deletion"})
        return
    try:
        target = resolve_library_target(item_id)
        preview = PREVIEW_STORE.put(target)
    except MatchError:
        send_json(handler, 409, {"ok": False, "error": "Unable to prepare deletion"})
        return
    except UpstreamError as exc:
        print(f"library delete preview upstream failure: {exc.source}", file=sys.stderr)
        send_json(handler, 502, {"ok": False, "error": "Unable to prepare deletion"})
        return
    except Exception as exc:
        print(f"library delete preview failure: {exc.__class__.__name__}", file=sys.stderr)
        if "404" in str(exc) or "not found" in str(exc).lower():
            send_json(handler, 404, {"ok": False, "error": "Library item not found"})
            return
        send_json(handler, 502, {"ok": False, "error": "Unable to prepare deletion"})
        return
    send_json(handler, 200, {"ok": True, **preview})


def handle_library_delete_execute(handler, item_id, preview_id):
    if not preview_id or not isinstance(preview_id, str):
        send_json(handler, 400, {"ok": False, "error": "Invalid preview"})
        return
    if not settings.JELLYFIN_API_KEY:
        send_json(handler, 502, {"ok": False, "error": "Unable to delete this title"})
        return
    try:
        result = execute_library_delete(item_id, preview_id)
    except ConflictError:
        send_json(handler, 409, {"ok": False, "error": "Library changed. Request a new preview."})
        return
    except UpstreamError:
        send_json(
            handler,
            502,
            {
                "ok": False,
                "error": "Unable to delete this title",
                "steps": {
                    "torrents": "failed",
                    "library": "skipped",
                    "jellyfin": "skipped",
                },
            },
        )
        return
    except Exception as exc:
        print(f"library delete execute failure: {exc.__class__.__name__}", file=sys.stderr)
        send_json(handler, 502, {"ok": False, "error": "Unable to delete this title"})
        return
    status = 200
    send_json(handler, status, result)
