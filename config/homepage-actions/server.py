"""HTTP server: request dispatch and lifecycle."""
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
from http_support import _reject_mutating, _reject_post, send_json, send_options
from routes import activity, arr, automation, discover, jellyfin, qbittorrent, reports, resources, service_links


class ActionsHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Reduce noise; errors still printed by the server.
        pass

    def do_OPTIONS(self):
        send_options(self)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        if path == "/qbt/torrents":
            qbittorrent.handle_qbt_torrents(self)
        elif path == "/jellyfin/movies":
            jellyfin.handle_jellyfin_items(self, "Movie")
        elif path == "/jellyfin/series":
            jellyfin.handle_jellyfin_items(self, "Series")
        elif path == "/jellyfin/watch-next":
            jellyfin.handle_jellyfin_watch_next(self)
        elif path == "/arr/library":
            arr.handle_arr_library(self)
        elif path == "/activity":
            activity.handle_activity_feed(self, query)
        elif path == "/sonarr/missing-count":
            arr.handle_sonarr_missing_count(self)
        elif path == "/sonarr/series-count":
            arr.handle_sonarr_series_count(self)
        elif path == "/sonarr/calendar":
            arr.handle_sonarr_calendar(self)
        elif path == "/automation/summary":
            automation.handle_automation_summary(self)
        elif path == "/system/resources":
            resources.handle_system_resources(self)
        elif path == "/health":
            send_json(self, 200, {"ok": True})
        elif path == "/service-links":
            service_links.handle_service_links(self)
        elif path == "/cron/logs":
            reports.handle_cron_logs(self)
        elif path == "/discover/hermes":
            discover.handle_discover_hermes_get(self)
        elif path == "/internal/discover/hermes":
            discover.handle_discover_hermes_generation_snapshot(self)
        elif path == "/discover/jellyseerr":
            discover.handle_discover_jellyseerr(self, query)
        elif path == "/discover/trakt":
            discover.handle_discover_trakt(self, query)
        else:
            send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})

    def do_PATCH(self):
        if _reject_mutating(self):
            return
        path = urllib.parse.urlparse(self.path).path
        prefix = "/discover/hermes/"
        if path.startswith(prefix):
            item_id = urllib.parse.unquote(path[len(prefix):])
            discover.handle_discover_hermes_patch(self, item_id)
        else:
            send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})

    def do_POST(self):
        if _reject_post(self):
            return
        path = urllib.parse.urlparse(self.path).path
        if path == "/qbt/torrents/stop":
            qbittorrent.handle_qbt_torrent_hash_action(self, "/api/v2/torrents/stop")
        elif path == "/qbt/torrents/start":
            qbittorrent.handle_qbt_torrent_hash_action(self, "/api/v2/torrents/start")
        elif path == "/stop-all":
            qbittorrent.handle_qbt_action(self, "/api/v2/torrents/stop")
        elif path == "/start-all":
            qbittorrent.handle_qbt_action(self, "/api/v2/torrents/start")
        elif path == "/discover/hermes":
            discover.handle_discover_hermes_post(self)
        elif path == "/discover/hermes/generations":
            discover.handle_discover_hermes_generations(self)
        elif path == "/discover/hermes/sync":
            discover.handle_discover_hermes_sync(self)
        elif path == "/discover/hermes/request-more":
            discover.handle_discover_hermes_request_more(self)
        elif path == "/discover/request/reconcile":
            discover.handle_discover_request_reconcile(self)
        elif path == "/discover/request":
            discover.handle_discover_request(self)
        else:
            send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})


def run_server():
    from reconciliation import start_reconciliation_scheduler, stop_reconciliation_scheduler

    start_reconciliation_scheduler()
    server = ThreadingHTTPServer(("0.0.0.0", config.PORT), ActionsHandler)
    print(
        f"Dashboard actions API listening on :{config.PORT} "
        f"(request reconcile every {config.RECONCILE_INTERVAL_SECONDS:g}s; "
        "manual POST /discover/request/reconcile)",
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        stop_reconciliation_scheduler()
        server.server_close()
