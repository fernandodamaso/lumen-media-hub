import unittest
from unittest.mock import patch

import main


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


if __name__ == "__main__":
    unittest.main()
