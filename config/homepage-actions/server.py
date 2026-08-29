"""HTTP server: request dispatch and lifecycle."""
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
from http_support import _reject_mutating, _reject_post, _valid_library_item_id, send_json, send_options
from routes import activity, arr, automation, discover, jellyfin, library, qbittorrent, queue_hygiene, reports, resources, service_links


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
        elif path == "/jellyfin/recently-available":
            jellyfin.handle_jellyfin_recently_available(self, query)
        elif path == "/arr/library":
            arr.handle_arr_library(self)
        elif path == "/activity":
            activity.handle_activity_feed(self, query)
        elif path == "/sonarr/missing-count":
            arr.handle_sonarr_missing_count(self)
        elif path == "/sonarr/series-count":
            arr.handle_sonarr_series_count(self)
        elif path == "/calendar":
            arr.handle_sonarr_calendar(self)
        elif path == "/sonarr/calendar":
            # Compatibility alias retained while Live clients migrate to /calendar.
            arr.handle_sonarr_calendar(self)
        elif path == "/automation/summary":
            automation.handle_automation_summary(self)
        elif path == "/automation/queue-hygiene":
            queue_hygiene.handle_queue_hygiene_get(self)
        elif path == "/system/resources":
            resources.handle_system_resources(self)
        elif path == "/health":
            send_json(self, 200, {"ok": True})
        elif path == "/service-links":
            service_links.handle_service_links(self)
        elif path == "/cron/logs":
            reports.handle_cron_logs(self)
        elif path == "/discover/ai-picks":
            discover.handle_discover_ai_picks_get(self)
        elif path == "/discover/jellyseerr":
            discover.handle_discover_jellyseerr(self, query)
        elif path == "/discover/trakt":
            discover.handle_discover_trakt(self, query)
        elif path.startswith("/library/items/") and path.endswith("/delete-preview"):
            if _reject_mutating(self):
                return
            item_id = urllib.parse.unquote(path[len("/library/items/"):-len("/delete-preview")])
            if not _valid_library_item_id(item_id):
                send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})
                return
            library.handle_library_delete_preview(self, item_id)
        else:
            send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})

    def do_PATCH(self):
        if _reject_mutating(self):
            return
        path = urllib.parse.urlparse(self.path).path
        prefix = "/discover/ai-picks/"
        if path.startswith(prefix):
            item_id = urllib.parse.unquote(path[len(prefix):])
            discover.handle_discover_ai_picks_patch(self, item_id)
            return
        prefix = "/jellyfin/items/"
        suffix = "/played"
        if path.startswith(prefix) and path.endswith(suffix):
            item_id = urllib.parse.unquote(path[len(prefix):-len(suffix)])
            if not _valid_library_item_id(item_id):
                send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})
                return
            jellyfin.handle_jellyfin_item_played(self, item_id)
            return
        send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})

    def do_DELETE(self):
        if _reject_mutating(self):
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        prefix = "/library/items/"
        if path.startswith(prefix):
            if path.endswith("/direct"):
                item_id = urllib.parse.unquote(path[len(prefix):-len("/direct")])
                if not _valid_library_item_id(item_id):
                    send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})
                    return
                library.handle_library_delete_direct(self, item_id)
                return
            item_id = urllib.parse.unquote(path[len(prefix):])
            if not _valid_library_item_id(item_id):
                send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})
                return
            preview_id = (query.get("previewId") or [None])[0]
            library.handle_library_delete_execute(self, item_id, preview_id)
            return
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
        elif path == "/discover/ai-picks/request-more":
            discover.handle_discover_ai_picks_request_more(self)
        elif path == "/internal/ai-picks/jobs/claim":
            discover.handle_ai_picks_job_claim(self)
        elif path.startswith("/internal/ai-picks/jobs/"):
            remainder = path[len("/internal/ai-picks/jobs/"):]
            if remainder.endswith("/complete"):
                job_id = urllib.parse.unquote(remainder[:-len("/complete")])
                discover.handle_ai_picks_job_complete(self, job_id)
            elif remainder.endswith("/fail"):
                job_id = urllib.parse.unquote(remainder[:-len("/fail")])
                discover.handle_ai_picks_job_fail(self, job_id)
            else:
                send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})
        elif path == "/discover/request/reconcile":
            discover.handle_discover_request_reconcile(self)
        elif path == "/discover/request":
            discover.handle_discover_request(self)
        elif path == "/automation/queue-hygiene/run":
            queue_hygiene.handle_queue_hygiene_run(self)
        elif path == "/automation/queue-hygiene/reset":
            queue_hygiene.handle_queue_hygiene_reset(self)
        else:
            send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})


def run_server():
    from reconciliation import (
        migrate_legacy_generation_request,
        start_reconciliation_scheduler,
        stop_reconciliation_scheduler,
    )
    from ai_schedule import AiPicksSchedule, AiPicksScheduleRunner
    from queue_hygiene import start_queue_hygiene_scheduler, stop_queue_hygiene_scheduler

    config.RECOMMENDATIONS_STORE.ensure_current()
    coordinator = discover._generation_coordinator()
    migrate_legacy_generation_request(coordinator, config.AI_PICKS_ON_DEMAND_COUNT)
    ai_schedule = AiPicksScheduleRunner(
        AiPicksSchedule(
            load=config.RECOMMENDATIONS_STORE.load,
            queue=coordinator.queue,
            enabled=lambda: config.AI_ENABLED,
            target=config.AI_PICKS_TARGET_ACTIVE,
            hour=config.AI_PICKS_SCHEDULE_HOUR,
            count_effective=discover.effective_ai_picks_active_count,
        )
    )
    ai_schedule.start()
    start_reconciliation_scheduler()
    start_queue_hygiene_scheduler()
    server = ThreadingHTTPServer(("0.0.0.0", config.PORT), ActionsHandler)
    discover._request_ai_picks_collection_sync()
    print(
        f"Dashboard actions API listening on :{config.PORT} "
        f"(request reconcile every {config.RECONCILE_INTERVAL_SECONDS:g}s; "
        "manual POST /discover/request/reconcile)",
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        ai_schedule.stop()
        stop_queue_hygiene_scheduler()
        stop_reconciliation_scheduler()
        server.server_close()
