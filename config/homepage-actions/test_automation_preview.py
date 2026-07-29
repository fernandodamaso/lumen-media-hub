import unittest
import json
from io import BytesIO
from unittest.mock import patch

import main


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
            patch("main.SONARR_API_KEY", "sk"),
            patch("main.SONARR_EXTERNAL_URL", "http://sonarr:8989"),
            patch("main._arr_get", side_effect=mock_get),
        ):
            _count, items = main._sonarr_missing_preview()
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
            patch("main.SONARR_API_KEY", "sk"),
            patch("main.SONARR_EXTERNAL_URL", "http://sonarr:8989"),
            patch("main._arr_get", side_effect=mock_get),
        ):
            _count, items = main._sonarr_missing_preview()
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
            patch("main.RADARR_API_KEY", "rk"),
            patch("main.RADARR_EXTERNAL_URL", "http://radarr:7878"),
            patch("main._arr_get", side_effect=mock_get),
        ):
            _count, items = main._radarr_missing_preview()
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
            patch("main.RADARR_API_KEY", "rk"),
            patch("main.RADARR_EXTERNAL_URL", "http://radarr:7878"),
            patch("main._arr_get", side_effect=mock_get),
        ):
            _count, items = main._radarr_missing_preview()
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
            patch("main.SONARR_API_KEY", "super-secret-sonarr-key"),
            patch("main.RADARR_API_KEY", "super-secret-radarr-key"),
            patch("main.SONARR_EXTERNAL_URL", "http://sonarr:8989"),
            patch("main.RADARR_EXTERNAL_URL", "http://radarr:7878"),
            patch("main._arr_get", side_effect=mock_get),
        ):
            _cs, items_s = main._sonarr_missing_preview()
            _cr, items_r = main._radarr_missing_preview()

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
            main,
            SONARR_API_KEY="",
            RADARR_API_KEY="",
            PROWLARR_API_KEY="",
            BAZARR_ENABLED=False,
            BAZARR_API_KEY="configured-key",
        ), patch("main._arr_get") as arr_get:
            summary = main._build_automation_summary()

        self.assertNotIn("bazarr", summary)
        arr_get.assert_not_called()

    def test_enabled_unreachable_bazarr_is_down(self):
        with patch.multiple(
            main,
            SONARR_API_KEY="",
            RADARR_API_KEY="",
            PROWLARR_API_KEY="",
            BAZARR_ENABLED=True,
            BAZARR_API_KEY="configured-key",
        ), patch("main._arr_get", side_effect=ConnectionError("connection refused")):
            summary = main._build_automation_summary()

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
            main,
            SONARR_API_KEY="",
            RADARR_API_KEY="",
            PROWLARR_API_KEY="",
            BAZARR_ENABLED=True,
            BAZARR_API_KEY="configured-key",
        ), patch("main._arr_get", side_effect=arr_get):
            summary = main._build_automation_summary()

        self.assertEqual(summary["bazarr"]["ok"], False)
        self.assertEqual(summary["bazarr"]["wantedEpisodes"], 1)
        self.assertEqual(summary["bazarr"]["wantedMovies"], 0)
        self.assertEqual(summary["bazarr"]["wantedItems"], [{"label": "Example S01E01"}])
        self.assertIn("movies: movie wanted unavailable", summary["bazarr"]["error"])

    def test_enabled_bazarr_without_key_is_explicitly_unavailable(self):
        with patch.multiple(
            main,
            SONARR_API_KEY="",
            RADARR_API_KEY="",
            PROWLARR_API_KEY="",
            BAZARR_ENABLED=True,
            BAZARR_API_KEY="",
        ), patch("main._arr_get") as arr_get:
            summary = main._build_automation_summary()

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
        with patch.multiple(main, JELLYSEERR_ENABLED=False, JELLYSEERR_API_KEY="configured-key"):
            main.handle_discover_jellyseerr(handler, {})

        self.assertEqual(handler.status, 200)
        self.assertEqual(
            json.loads(handler.wfile.getvalue()),
            {"ok": True, "enabled": False, "items": []},
        )

    def test_jellyseerr_disabled_request_error_is_distinct(self):
        with patch.multiple(main, JELLYSEERR_ENABLED=False, JELLYSEERR_API_KEY=""):
            with self.assertRaisesRegex(RuntimeError, "Jellyseerr is disabled"):
                main._jellyseerr_get("/api/v1/movie/1")

    def test_jellyseerr_missing_key_request_error_is_distinct(self):
        with patch.multiple(main, JELLYSEERR_ENABLED=True, JELLYSEERR_API_KEY=""):
            with self.assertRaisesRegex(RuntimeError, "JELLYSEERR_API_KEY not configured"):
                main._jellyseerr_get("/api/v1/movie/1")


if __name__ == "__main__":
    unittest.main()
