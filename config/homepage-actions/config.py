"""Environment and shared module settings for homepage-actions."""
import os
import threading

from recommendations_store import RecommendationStore

QBT_URL = os.environ.get("QBT_URL", "http://qbittorrent:8081").rstrip("/")
QBT_USERNAME = os.environ.get("QBT_USERNAME", "admin")
QBT_PASSWORD = os.environ.get("QBT_PASSWORD", "changeme")

JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://jellyfin:8096").rstrip("/")
JELLYFIN_EXTERNAL_URL = os.environ.get("JELLYFIN_EXTERNAL_URL", "http://localhost:8096").rstrip("/")
JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "")
JELLYFIN_USER_ID = os.environ.get("JELLYFIN_USER_ID", "")

SONARR_URL = os.environ.get("SONARR_URL", "http://sonarr:8989").rstrip("/")
SONARR_API_KEY = os.environ.get("SONARR_API_KEY", "")
RADARR_URL = os.environ.get("RADARR_URL", "http://radarr:7878").rstrip("/")
RADARR_API_KEY = os.environ.get("RADARR_API_KEY", "")
PROWLARR_URL = os.environ.get("PROWLARR_URL", "http://prowlarr:9696").rstrip("/")
PROWLARR_API_KEY = os.environ.get("PROWLARR_API_KEY", "")
BAZARR_URL = os.environ.get("BAZARR_URL", "http://bazarr:6767").rstrip("/")
BAZARR_ENABLED = os.environ.get("BAZARR_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
BAZARR_API_KEY = os.environ.get("BAZARR_API_KEY", "")

JELLYSEERR_URL = os.environ.get("JELLYSEERR_URL", "http://jellyseerr:5055").rstrip("/")
JELLYSEERR_ENABLED = os.environ.get("JELLYSEERR_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
JELLYSEERR_API_KEY = os.environ.get("JELLYSEERR_API_KEY", "")

TRAKT_CLIENT_ID = os.environ.get("TRAKT_CLIENT_ID", "")
TRAKT_CLIENT_SECRET = os.environ.get("TRAKT_CLIENT_SECRET", "")
TRAKT_TOKEN_PATH = os.environ.get("TRAKT_TOKEN_PATH", "/state/trakt-token.json")
TRAKT_WATCHED_PATH = os.environ.get("TRAKT_WATCHED_PATH", "/state/trakt-watched.json")

HERMES_COLLECTION_NAME = os.environ.get("HERMES_COLLECTION_NAME", "Hermes Picks")

_cors_raw = os.environ.get("CORS_ORIGINS") or os.environ.get(
    "CORS_ORIGIN", "http://localhost:3000,http://localhost:4200"
)
CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]
ACTIONS_TOKEN = os.environ.get("ACTIONS_TOKEN", "")
PORT = int(os.environ.get("PORT", "8085"))
DATA_PATH = os.environ.get("DATA_PATH", "/data")
RECOMMENDATIONS_PATH = os.environ.get(
    "RECOMMENDATIONS_PATH",
    os.path.join(DATA_PATH, "config", "recommendations", "recommendations.json"),
)
RECOMMENDATIONS_STORE = RecommendationStore(RECOMMENDATIONS_PATH)
RECONCILIATION_PATH = os.environ.get(
    "HERMES_REQUEST_RECONCILIATION_PATH",
    os.path.join(os.path.dirname(RECOMMENDATIONS_PATH), "request-reconciliation.json"),
)
GENERATION_REQUEST_PATH = os.environ.get(
    "HERMES_GENERATION_REQUEST_PATH",
    os.path.join(os.path.dirname(RECOMMENDATIONS_PATH), "generation-request.json"),
)
# Automatic retries: one startup attempt, then a bounded periodic cycle.
# Override with HERMES_RECONCILE_INTERVAL_SECONDS (seconds). Manual recovery
# remains available at POST /discover/request/reconcile.
RECONCILE_INTERVAL_SECONDS = float(
    os.environ.get("HERMES_RECONCILE_INTERVAL_SECONDS", "30")
)
_reconciliation_lock = threading.RLock()
_generation_request_lock = threading.RLock()
_reconcile_cycle_lock = threading.Lock()
_reconcile_stop = threading.Event()
_reconcile_thread = None
_reconcile_thread_lock = threading.Lock()
TMP_DIR = os.path.abspath(os.environ.get("TMP_DIR", os.path.join(DATA_PATH, "tmp")))
TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "10"))
CRON_LOG_FILES = (
    {
        "id": "watchdog",
        "title": "Media Download Watchdog",
        "file": "watch-downloads.log",
        "format": "ndjson",
        "schedule": "every 15m",
        "description": (
            "Finds completed torrents that Sonarr/Radarr should have imported but left stuck "
            "in qBittorrent. Covers the gaps native Completed Download Handling does not age out."
        ),
        "actions": [
            "Import stuck downloads via Sonarr/Radarr when safe",
            "Verify hardlinks into the library",
            "Trigger Bazarr for new imports",
            "Remove the finished qBittorrent row after import",
            "Blocklist hard-rejected releases and re-search a replacement",
        ],
    },
    {
        "id": "stale-metadata",
        "title": "Stale Metadata Cleanup",
        "file": "stale-metadata-cleanup.log",
        "format": "text",
        "schedule": "every 30m",
        "description": (
            "Clears Sonarr/Radarr queue items that are stuck fetching torrent metadata "
            "or sitting in long stalled/error states so a better release can be grabbed."
        ),
        "actions": [
            "Remove metaDL items older than 60 minutes",
            "Remove stalled/error/missing-files items older than 6 hours",
            "Remove the matching qBittorrent torrent",
            "Blocklist the bad release",
            "Queue a replacement episode/movie search",
        ],
    },
    {
        "id": "hardlink-cleanup",
        "title": "Hardlink Staging Cleanup",
        "file": "hardlink-staging-cleanup.log",
        "format": "text",
        "schedule": "Saturday 03:00",
        "description": (
            "Frees leftover staging copies under downloads/torrents if a post-import remove was missed. "
            "Only deletes files that already have a hardlink in the library."
        ),
        "actions": [
            "Scan downloads/torrents for multi-hardlink files",
            "Skip anything still under an active qBittorrent content path",
            "Delete leftover staging copies (library copy stays)",
            "Remove empty directories afterward",
        ],
    },
    {
        "id": "weekly-validate",
        "title": "Weekly Validate Final",
        "file": "weekly-validate-final.log",
        "format": "text",
        "schedule": "Sunday 05:00",
        "description": (
            "Runs the full stack health check: compose, containers, ports, qBit categories, "
            "*arr clients, hardlinks, Prowlarr/Bazarr, Jellyfin libraries, and disk space."
        ),
        "actions": [
            "Validate Docker Compose and running containers",
            "Confirm localhost-only UI ports (Jellyfin LAN allowed)",
            "Check qBittorrent categories and *arr download clients",
            "Verify hardlink config, Prowlarr/Bazarr, and Jellyfin libraries",
            "Flag non-green findings as alerts",
        ],
    },
)
JELLYFIN_CACHE_TTL = float(os.environ.get("JELLYFIN_CACHE_TTL", "45"))
ARR_CACHE_TTL = float(os.environ.get("ARR_CACHE_TTL", "300"))
CALENDAR_CACHE_TTL = float(os.environ.get("CALENDAR_CACHE_TTL", "60"))
AUTOMATION_CACHE_TTL = float(os.environ.get("AUTOMATION_CACHE_TTL", "30"))
ACTIVITY_CACHE_TTL = float(os.environ.get("ACTIVITY_CACHE_TTL", "30"))
RESOURCES_CACHE_TTL = float(os.environ.get("RESOURCES_CACHE_TTL", "5"))
CALENDAR_MAX_EVENTS = int(os.environ.get("CALENDAR_MAX_EVENTS", "10"))
CALENDAR_DAYS = int(os.environ.get("CALENDAR_DAYS", "30"))

CORS_ALLOW_HEADERS = "Content-Type, X-Actions-Token"
CORS_ALLOW_METHODS = "GET, POST, PATCH, OPTIONS"

AUTOMATION_PREVIEW_LIMIT = int(os.environ.get("AUTOMATION_PREVIEW_LIMIT", "3"))
AUTOMATION_MISSING_LIMIT = int(os.environ.get("AUTOMATION_MISSING_LIMIT", "50"))
SONARR_EXTERNAL_URL = os.environ.get("SONARR_EXTERNAL_URL", "http://localhost:8989").rstrip("/")
RADARR_EXTERNAL_URL = os.environ.get("RADARR_EXTERNAL_URL", "http://localhost:7878").rstrip("/")
PROWLARR_EXTERNAL_URL = os.environ.get("PROWLARR_EXTERNAL_URL", "http://localhost:9696").rstrip("/")
QBITTORRENT_EXTERNAL_URL = os.environ.get(
    "QBITTORRENT_EXTERNAL_URL", "http://127.0.0.1:8081"
).rstrip("/")
BAZARR_EXTERNAL_URL = os.environ.get("BAZARR_EXTERNAL_URL", "http://localhost:6767").rstrip("/")


def service_link_bases():
    """Browser-facing service base URLs (host-published ports)."""
    return {
        "jellyfin": JELLYFIN_EXTERNAL_URL,
        "sonarr": SONARR_EXTERNAL_URL,
        "radarr": RADARR_EXTERNAL_URL,
        "prowlarr": PROWLARR_EXTERNAL_URL,
        "qbittorrent": QBITTORRENT_EXTERNAL_URL,
        "bazarr": BAZARR_EXTERNAL_URL,
    }

_jellyfin_cache = {}
_jellyfin_locks = {}
_jellyfin_cache_lock = threading.Lock()
_jellyfin_user_id = None
_jellyfin_user_id_lock = threading.Lock()

_arr_cache = {}
_arr_cache_lock = threading.Lock()

_cpu_prev = None
_cpu_prev_lock = threading.Lock()


