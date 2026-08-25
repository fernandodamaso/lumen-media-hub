"""Authenticated queue-hygiene status and manual-run routes."""
import json

import config as settings
from http_support import _BodyTooLarge, _read_json_body, send_json
from queue_hygiene import _read_state, _write_state, normalized_state, run_queue_hygiene_cycle


def handle_queue_hygiene_get(handler):
    send_json(handler, 200, {"ok": True, **normalized_state(_read_state())})


def handle_queue_hygiene_run(handler):
    try:
        body = _read_json_body(handler)
    except (_BodyTooLarge, UnicodeDecodeError, json.JSONDecodeError):
        send_json(handler, 400, {"ok": False, "error": "Invalid JSON"})
        return
    if not isinstance(body, dict) or set(body) != {"mode"} or body.get("mode") not in {"observe", "auto"}:
        send_json(handler, 400, {"ok": False, "error": "Body must contain only mode=observe or mode=auto"})
        return
    try:
        result = run_queue_hygiene_cycle(mode=body["mode"])
    except Exception as error:
        send_json(handler, 502, {"ok": False, "error": str(error)})
        return
    state = normalized_state(_read_state())
    payload = {
        **state,
        **result,
        "eligibleItems": result.get("eligibleGroups", state["eligibleItems"]),
        "blockedItems": result.get("blockedItems", state["blockedItems"]),
        "eligibleCount": result.get("counts", {}).get("eligible", state["eligibleCount"]),
        "blockedCount": result.get("counts", {}).get("blocked", state["blockedCount"]),
    }
    send_json(handler, 200, {"ok": True, **payload})


def handle_queue_hygiene_reset(handler):
    try:
        body = _read_json_body(handler)
    except (_BodyTooLarge, UnicodeDecodeError, json.JSONDecodeError):
        send_json(handler, 400, {"ok": False, "error": "Invalid JSON"})
        return
    if not isinstance(body, dict) or set(body) != {"confirm"} or body.get("confirm") != "reset-circuit":
        send_json(handler, 400, {"ok": False, "error": "Body must contain only confirm=reset-circuit"})
        return
    state = _read_state()
    state.pop("error", None)
    state["circuitOpen"] = False
    _write_state(state)
    settings._arr_cache.pop("automation", None)
    settings._arr_cache.pop("automation_ts", None)
    send_json(handler, 200, {"ok": True, **normalized_state(state)})
