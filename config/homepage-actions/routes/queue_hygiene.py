"""Authenticated queue-hygiene status and manual-run routes."""
import json

from http_support import _BodyTooLarge, _read_json_body, send_json
from queue_hygiene import _read_state, run_queue_hygiene_cycle


def handle_queue_hygiene_get(handler):
    state = _read_state()
    send_json(handler, 200, {"ok": True, **state})


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
    send_json(handler, 200, {"ok": True, **result})
