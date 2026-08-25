import unittest
import json
from io import BytesIO
from unittest.mock import patch

import config
import clients.jellyseerr as jellyseerr_client
import routes.automation as automation_routes
import routes.discover as discover_routes


class _CaptureHandler:
    def __init__(self):
        self.headers = {}
        self.status = None
        self.wfile = BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers[name] = value

    def end_headers(self):
        pass


class TestQueueSnapshot(unittest.TestCase):
    def test_sonarr_snapshot_fetches_full_queue_with_nested_entities(self):
        with patch("config.SONARR_URL", "http://sonarr"), patch(
            "routes.automation._arr_get", return_value={"totalRecords": 4, "records": []}
        ) as arr_get:
            snapshot = automation_routes._fetch_queue_snapshot("http://sonarr", "key")

        self.assertEqual(snapshot["totalRecords"], 4)
        path = arr_get.call_args.args[2]
        self.assertIn("pageSize=1000", path)
        self.assertIn("includeUnknownSeriesItems=true", path)
        self.assertIn("includeSeries=true", path)
        self.assertIn("includeEpisode=true", path)

    def test_queue_preview_caps_items_but_keeps_total_and_derives_error(self):
        snapshot = {
            "totalRecords": 5,
            "records": [
                {"title": "One", "statusMessages": [{"messages": ["Not an upgrade"]}]},
                {"title": "Two", "errorMessage": "explicit"},
                {"title": "Three"},
            ],
        }
        with patch("config.AUTOMATION_PREVIEW_LIMIT", 2):
            count, items = automation_routes._queue_preview(snapshot)

        self.assertEqual(count, 5)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["error"], "Not an upgrade")
        self.assertTrue(items[0]["warning"])
        self.assertEqual(items[1]["error"], "explicit")


class TestQueueHygieneSummary(unittest.TestCase):
    def test_maps_bounded_state_and_preserves_cleanup(self):
        state = {
            "mode": "observe",
            "circuitOpen": True,
            "counts": {"eligible": 4, "blocked": 3},
            "eligibleItems": [{"queueIds": [1]}] * 5,
            "blockedItems": [{"queueId": 2}] * 5,
            "lastCycleAt": "2026-08-23T12:00:00Z",
            "lastCleanup": {"queueIds": [9]},
            "verification": {"queueIdsGone": True, "hashesPreserved": True, "missingHashes": []},
        }
        with patch("routes.automation._read_state", return_value=state), patch(
            "config.AUTOMATION_PREVIEW_LIMIT", 2
        ):
            result = automation_routes._queue_hygiene_summary()
        self.assertEqual(result["eligibleCount"], 4)
        self.assertEqual(result["blockedCount"], 3)
        self.assertTrue(result["circuitOpen"])
        self.assertEqual(len(result["eligibleItems"]), 2)
        self.assertEqual(result["lastCleanup"], {"queueIds": [9]})
        self.assertEqual(result["verification"]["hashesPreserved"], True)

    def test_state_read_failure_returns_safe_empty_block(self):
        with patch("routes.automation._read_state", side_effect=OSError("unavailable")):
            result = automation_routes._queue_hygiene_summary()
        self.assertEqual(result["eligibleCount"], 0)
        self.assertEqual(result["blockedCount"], 0)
        self.assertFalse(result["circuitOpen"])


class TestMissingPreviewPosterUrls(unittest.TestCase):
    """posterUrl emission for Sonarr/Radarr missing-item previews."""

    # ------------------------------------------------------------------
    # Sonarr
    # ------------------------------------------------------------------

    def test_sonarr_series_id_13_creates_poster_url(self):
        def mock_get(_base, _key, _path):
            return {
                "totalRecords": 1,
                "records": [{
                    "title": "Ep 1",
                    "seasonNumber": 1,
                    "episodeNumber": 1,
                    "airDateUtc": "2024-01-01T00:00:00Z",
                    "seriesId": 13,
                    "series": {"id": 13, "title": "S", "titleSlug": "s"},
                }],
            }

        with (
            patch("config.SONARR_API_KEY", "sk"),
            patch("config.SONARR_EXTERNAL_URL", "http://sonarr:8989"),
            patch("routes.automation._arr_get", side_effect=mock_get),
        ):
            _count, items = automation_routes._sonarr_missing_preview()
            self.assertEqual(
                items[0]["posterUrl"],
                "http://sonarr:8989/MediaCover/13/poster-250.jpg",
            )

    def test_sonarr_missing_id_returns_none(self):
        def mock_get(_base, _key, _path):
            return {
                "totalRecords": 1,
                "records": [{
                    "title": "Ep 1",
                    "seasonNumber": 1,
                    "episodeNumber": 1,
                    "airDateUtc": "2024-01-01T00:00:00Z",
                    "seriesId": None,
                    "series": {},
                }],
            }

        with (
            patch("config.SONARR_API_KEY", "sk"),
            patch("config.SONARR_EXTERNAL_URL", "http://sonarr:8989"),
            patch("routes.automation._arr_get", side_effect=mock_get),
        ):
            _count, items = automation_routes._sonarr_missing_preview()
            self.assertIsNone(items[0]["posterUrl"])

    # ------------------------------------------------------------------
    # Radarr — wanted / missing branch
    # ------------------------------------------------------------------

    def test_radarr_wanted_id_27_creates_poster_url(self):
        def mock_get(_base, _key, path):
            if "/api/v3/wanted/missing" in path:
                return {
                    "totalRecords": 1,
                    "records": [{
                        "title": "M",
                        "year": 2024,
                        "titleSlug": "m",
                        "id": 27,
                    }],
                }
            return []

        with (
            patch("config.RADARR_API_KEY", "rk"),
            patch("config.RADARR_EXTERNAL_URL", "http://radarr:7878"),
            patch("routes.automation._arr_get", side_effect=mock_get),
        ):
            _count, items = automation_routes._radarr_missing_preview()
            self.assertEqual(
                items[0]["posterUrl"],
                "http://radarr:7878/MediaCover/27/poster-250.jpg",
            )

    # ------------------------------------------------------------------
    # Radarr — fallback branch
    # ------------------------------------------------------------------

    def test_radarr_fallback_id_29_creates_poster_url(self):
        call_n = [0]

        def mock_get(_base, _key, _path):
            call_n[0] += 1
            if call_n[0] == 1:
                raise Exception("boom")
            return [{
                "title": "F",
                "year": 2024,
                "titleSlug": "f",
                "monitored": True,
                "hasFile": False,
                "id": 29,
            }]

        with (
            patch("config.RADARR_API_KEY", "rk"),
            patch("config.RADARR_EXTERNAL_URL", "http://radarr:7878"),
            patch("routes.automation._arr_get", side_effect=mock_get),
        ):
            _count, items = automation_routes._radarr_missing_preview()
            self.assertEqual(
                items[0]["posterUrl"],
                "http://radarr:7878/MediaCover/29/poster-250.jpg",
            )

    # ------------------------------------------------------------------
    # Security: no API-key leakage in posterUrl
    # ------------------------------------------------------------------

    def test_poster_urls_contain_no_secrets(self):
        """posterUrl must never carry apiKey, token, or the raw key value."""

        def mock_get(_base, _key, path):
            if "sonarr" in _base.lower() and "/api/v3/wanted/missing" in path:
                return {
                    "totalRecords": 1,
                    "records": [{
                        "title": "E",
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "seriesId": 13,
                        "series": {"id": 13,
                                   "title": "S", "titleSlug": "s"},
                    }],
                }
            if "/api/v3/wanted/missing" in path:
                return {
                    "totalRecords": 1,
                    "records": [{
                        "title": "M",
                        "year": 2024,
                        "titleSlug": "m",
                        "id": 27,
                    }],
                }
            return []

        with (
            patch("config.SONARR_API_KEY", "super-secret-sonarr-key"),
            patch("config.RADARR_API_KEY", "super-secret-radarr-key"),
            patch("config.SONARR_EXTERNAL_URL", "http://sonarr:8989"),
            patch("config.RADARR_EXTERNAL_URL", "http://radarr:7878"),
            patch("routes.automation._arr_get", side_effect=mock_get),
        ):
            _cs, items_s = automation_routes._sonarr_missing_preview()
            _cr, items_r = automation_routes._radarr_missing_preview()

            for items, label in [(items_s, "sonarr"), (items_r, "radarr")]:
                for item in items:
                    url = item.get("posterUrl") or ""
                    self.assertNotIn("apiKey", url, f"{label} leaks apiKey")
                    self.assertNotIn("apikey", url, f"{label} leaks apikey")
                    self.assertNotIn("token", url.lower(), f"{label} leaks token")
                    self.assertNotIn("super-secret", url,
                                     f"{label} leaks raw key")


class TestOptionalCapabilities(unittest.TestCase):
    def test_disabled_bazarr_is_omitted_even_when_key_exists(self):
        with patch.multiple(
            config,
            SONARR_API_KEY="",
            RADARR_API_KEY="",
            PROWLARR_API_KEY="",
            BAZARR_ENABLED=False,
            BAZARR_API_KEY="configured-key",
        ), patch("clients.arr._arr_get") as arr_get:
            summary = automation_routes._build_automation_summary()

        self.assertNotIn("bazarr", summary)
        arr_get.assert_not_called()

    def test_enabled_unreachable_bazarr_is_down(self):
        with patch.multiple(
            config,
            SONARR_API_KEY="",
            RADARR_API_KEY="",
            PROWLARR_API_KEY="",
            BAZARR_ENABLED=True,
            BAZARR_API_KEY="configured-key",
        ), patch("clients.arr._arr_get", side_effect=ConnectionError("connection refused")):
            summary = automation_routes._build_automation_summary()

        self.assertEqual(summary["bazarr"]["ok"], False)
        self.assertIn("connection refused", summary["bazarr"]["error"])

    def test_bazarr_preserves_episode_results_when_movie_wanted_fails(self):
        def arr_get(_url, _key, path):
            if "/episodes/wanted" in path:
                return {
                    "total": 1,
                    "data": [{"seriesTitle": "Example", "episode_number": "S01E01"}],
                }
            raise ConnectionError("movie wanted unavailable")

        with patch.multiple(
            config,
            SONARR_API_KEY="",
            RADARR_API_KEY="",
            PROWLARR_API_KEY="",
            BAZARR_ENABLED=True,
            BAZARR_API_KEY="configured-key",
        ), patch("clients.arr._arr_get", side_effect=arr_get):
            summary = automation_routes._build_automation_summary()

        self.assertEqual(summary["bazarr"]["ok"], False)
        self.assertEqual(summary["bazarr"]["wantedEpisodes"], 1)
        self.assertEqual(summary["bazarr"]["wantedMovies"], 0)
        self.assertEqual(summary["bazarr"]["wantedItems"], [{"label": "Example S01E01"}])
        self.assertIn("movies: movie wanted unavailable", summary["bazarr"]["error"])

    def test_enabled_bazarr_without_key_is_explicitly_unavailable(self):
        with patch.multiple(
            config,
            SONARR_API_KEY="",
            RADARR_API_KEY="",
            PROWLARR_API_KEY="",
            BAZARR_ENABLED=True,
            BAZARR_API_KEY="",
        ), patch("clients.arr._arr_get") as arr_get:
            summary = automation_routes._build_automation_summary()

        self.assertEqual(
            summary["bazarr"],
            {
                "ok": False,
                "enabled": True,
                "configured": False,
                "error": "BAZARR_API_KEY not configured",
            },
        )
        arr_get.assert_not_called()

    def test_disabled_jellyseerr_returns_empty_success_payload(self):
        handler = _CaptureHandler()
        with patch.multiple(config, JELLYSEERR_ENABLED=False, JELLYSEERR_API_KEY="configured-key"), \
                patch.object(discover_routes, "_trakt_watched_snapshot") as watched_snapshot:
            discover_routes.handle_discover_jellyseerr(handler, {})

        self.assertEqual(handler.status, 200)
        self.assertEqual(
            json.loads(handler.wfile.getvalue()),
            {"ok": True, "enabled": False, "items": []},
        )
        watched_snapshot.assert_not_called()

    def test_jellyseerr_disabled_request_error_is_distinct(self):
        with patch.multiple(config, JELLYSEERR_ENABLED=False, JELLYSEERR_API_KEY=""):
            with self.assertRaisesRegex(RuntimeError, "Jellyseerr is disabled"):
                jellyseerr_client._jellyseerr_get("/api/v1/movie/1")

    def test_jellyseerr_missing_key_request_error_is_distinct(self):
        with patch.multiple(config, JELLYSEERR_ENABLED=True, JELLYSEERR_API_KEY=""):
            with self.assertRaisesRegex(RuntimeError, "JELLYSEERR_API_KEY not configured"):
                jellyseerr_client._jellyseerr_get("/api/v1/movie/1")


if __name__ == "__main__":
    unittest.main()
