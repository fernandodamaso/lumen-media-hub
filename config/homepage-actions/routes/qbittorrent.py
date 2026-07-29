"""qBittorrent route handlers."""
import http.cookiejar
import json
import urllib.request

from clients.qbittorrent import qbt_get_json, qbt_login, qbt_post
from http_support import (
    _BodyTooLarge,
    _read_json_body,
    _valid_torrent_hash,
    send_json,
)

def handle_qbt_action(handler, action_path):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        qbt_login(opener)
        status, _ = qbt_post(action_path, {"hashes": "all"}, opener)
        send_json(handler, 200, {"ok": status >= 200 and status < 300})
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def handle_qbt_torrent_hash_action(handler, action_path):
    try:
        body = _read_json_body(handler)
    except _BodyTooLarge:
        send_json(handler, 413, {"ok": False, "error": "Request body too large"})
        return
    except json.JSONDecodeError:
        send_json(handler, 400, {"ok": False, "error": "Invalid JSON"})
        return
    if not isinstance(body, dict):
        send_json(handler, 400, {"ok": False, "error": "Invalid torrent id"})
        return
    torrent_id = body.get("id")
    if not _valid_torrent_hash(torrent_id):
        send_json(handler, 400, {"ok": False, "error": "Invalid torrent id"})
        return

    torrent_hash = torrent_id.strip().lower()
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        qbt_login(opener)
        status, _ = qbt_post(action_path, {"hashes": torrent_hash}, opener)
        send_json(handler, 200, {"ok": status >= 200 and status < 300})
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def handle_qbt_torrents(handler):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        qbt_login(opener)
        torrents = qbt_get_json("/api/v2/torrents/info", opener)
        send_json(handler, 200, torrents)
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})
