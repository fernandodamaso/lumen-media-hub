#!/usr/bin/env python3
"""Activity feed (merged Sonarr/Radarr history) contract tests."""

import json
import unittest
from io import BytesIO
from unittest import mock

import config
import clients.arr as arr_client
import routes.activity as activity_routes


def _sonarr_record(record_id, event_type, date, title="The Shōgun Court", season=1, number=7, slug="the-shogun-court", quality="1080p WEB-DL"):
    return {
        "id": record_id,
        "eventType": event_type,
        "date": date,
        "series": {"title": title, "titleSlug": slug},
        "episode": {"seasonNumber": season, "episodeNumber": number},
        "quality": {"quality": {"name": quality}},
    }


def _radarr_record(record_id, event_type, date, title="Dune", year=2021, slug="dune-2021", quality="2160p WEB-DL"):
    return {
        "id": record_id,
        "eventType": event_type,
        "date": date,
        "movie": {"title": title, "year": year, "titleSlug": slug},
        "quality": {"quality": {"name": quality}},
    }


class ActivityMappingTests(unittest.TestCase):
    def test_event_type_mapping(self):
        expected = {
            "grabbed": "grabbed",
            "downloadFolderImported": "imported",
            "seriesFolderImported": "imported",
            "movieFolderImported": "imported",
            "episodeFileDeleted": "deleted",
            "movieFileDeleted": "deleted",
            "downloadFailed": "failed",
        }
        for event_type, kind in expected.items():
            record = _radarr_record(1, event_type, "2026-07-30T00:18:41Z")
            mapped = arr_client._map_activity_record("radarr", record)
            self.assertIsNotNone(mapped, event_type)
            self.assertEqual(mapped["kind"], kind)

    def test_unknown_event_types_are_skipped(self):
        for event_type in ("episodeFileRenamed", "movieFileRenamed", "downloadIgnored"):
            mapped = arr_client._map_activity_record(
                "radarr", _radarr_record(1, event_type, "2026-07-30T00:18:41Z")
            )
            self.assertIsNone(mapped, event_type)

    def test_sonarr_record_shapes_item(self):
        mapped = arr_client._map_activity_record(
            "sonarr", _sonarr_record(48211, "grabbed", "2026-07-30T00:18:41Z")
        )
        self.assertEqual(
            mapped,
            {
                "id": "sonarr:48211",
                "source": "sonarr",
                "kind": "grabbed",
                "title": "The Shōgun Court",
                "subtitle": "S01E07 · 1080p WEB-DL",
                "timestamp": "2026-07-30T00:18:41Z",
                "href": f"{config.SONARR_EXTERNAL_URL}/series/the-shogun-court",
            },
        )

    def test_radarr_record_shapes_item(self):
        mapped = arr_client._map_activity_record(
            "radarr", _radarr_record(9021, "downloadFolderImported", "2026-07-30T00:05:00Z")
        )
        self.assertEqual(mapped["id"], "radarr:9021")
        self.assertEqual(mapped["kind"], "imported")
        self.assertEqual(mapped["subtitle"], "2021 · 2160p WEB-DL")
        self.assertEqual(mapped["href"], f"{config.RADARR_EXTERNAL_URL}/movie/dune-2021")

    def test_sonarr_nested_series_episode_titles_preferred(self):
        record = {
            "id": 99,
            "eventType": "grabbed",
            "date": "2026-07-30T00:02:00Z",
            "series": {"title": "Nested Show", "titleSlug": "nested-show"},
            "episode": {"seasonNumber": 2, "episodeNumber": 5},
            "sourceTitle": "Nested.Show.S02E05.1080p",
            "quality": {"quality": {"name": "720p HDTV"}},
        }
        mapped = arr_client._map_activity_record("sonarr", record)
        self.assertEqual(mapped["title"], "Nested Show")
        self.assertEqual(mapped["subtitle"], "S02E05 · 720p HDTV")
        self.assertEqual(mapped["href"], f"{config.SONARR_EXTERNAL_URL}/series/nested-show")

    def test_radarr_nested_movie_title_preferred(self):
        record = {
            "id": 88,
            "eventType": "grabbed",
            "date": "2026-07-30T00:03:00Z",
            "movie": {"title": "Nested Film", "year": 1999, "titleSlug": "nested-film-1999"},
            "sourceTitle": "Nested.Film.1999.1080p",
            "quality": {"quality": {"name": "1080p BluRay"}},
        }
        mapped = arr_client._map_activity_record("radarr", record)
        self.assertEqual(mapped["title"], "Nested Film")
        self.assertEqual(mapped["subtitle"], "1999 · 1080p BluRay")
        self.assertEqual(mapped["href"], f"{config.RADARR_EXTERNAL_URL}/movie/nested-film-1999")

    def test_missing_nested_record_falls_back_to_source_title(self):
        record = {
            "id": 7,
            "eventType": "grabbed",
            "date": "2026-07-30T00:01:00Z",
            "sourceTitle": "Some.Release.1080p",
        }
        mapped = arr_client._map_activity_record("sonarr", record)
        self.assertEqual(mapped["title"], "Some.Release.1080p")
        self.assertEqual(mapped["subtitle"], "")
        self.assertIsNone(mapped["href"])

    def test_missing_date_is_skipped(self):
        record = _radarr_record(1, "grabbed", "")
        self.assertIsNone(arr_client._map_activity_record("radarr", record))


class ActivityFeedBuildTests(unittest.TestCase):
    def setUp(self):
        config._arr_cache.clear()

    def _patch_history(self, sonarr_records=None, radarr_records=None, sonarr_error=False, radarr_error=False):
        def fake_get(base, api_key, path):
            self.assertIn("sortKey=date", path)
            if "sonarr" in base:
                self.assertIn("includeSeries=true", path)
                self.assertIn("includeEpisode=true", path)
                if sonarr_error:
                    raise RuntimeError("sonarr down")
                return {"records": sonarr_records or []}
            self.assertIn("includeMovie=true", path)
            if radarr_error:
                raise RuntimeError("radarr down")
            return {"records": radarr_records or []}

        return mock.patch.multiple("clients.arr", _arr_get=mock.Mock(side_effect=fake_get))

    def test_merges_sources_sorted_by_timestamp_desc(self):
        sonarr = [
            _sonarr_record(1, "grabbed", "2026-07-30T00:10:00Z"),
            _sonarr_record(2, "downloadFolderImported", "2026-07-30T00:20:00Z"),
        ]
        radarr = [_radarr_record(3, "grabbed", "2026-07-30T00:15:00Z")]
        with (
            mock.patch.object(config, "SONARR_API_KEY", "sk"),
            mock.patch.object(config, "RADARR_API_KEY", "rk"),
            self._patch_history(sonarr_records=sonarr, radarr_records=radarr),
        ):
            feed = arr_client._build_activity_feed()
        self.assertTrue(feed["ok"])
        self.assertEqual(feed["sources"], {"sonarr": "ok", "radarr": "ok"})
        self.assertEqual([i["id"] for i in feed["items"]], ["sonarr:2", "radarr:3", "sonarr:1"])
        self.assertTrue(feed["generatedAt"].endswith("Z"))

    def test_unconfigured_source_is_reported(self):
        with (
            mock.patch.object(config, "SONARR_API_KEY", ""),
            mock.patch.object(config, "RADARR_API_KEY", "rk"),
            self._patch_history(radarr_records=[_radarr_record(1, "grabbed", "2026-07-30T00:15:00Z")]),
        ):
            feed = arr_client._build_activity_feed()
        self.assertTrue(feed["ok"])
        self.assertEqual(feed["sources"], {"sonarr": "unconfigured", "radarr": "ok"})
        self.assertEqual(len(feed["items"]), 1)

    def test_failing_source_degrades_but_feed_stays_ok(self):
        with (
            mock.patch.object(config, "SONARR_API_KEY", "sk"),
            mock.patch.object(config, "RADARR_API_KEY", "rk"),
            self._patch_history(sonarr_error=True, radarr_records=[_radarr_record(1, "grabbed", "2026-07-30T00:15:00Z")]),
        ):
            feed = arr_client._build_activity_feed()
        self.assertTrue(feed["ok"])
        self.assertEqual(feed["sources"], {"sonarr": "error", "radarr": "ok"})
        self.assertEqual(len(feed["items"]), 1)

    def test_both_failing_sources_yield_not_ok_feed(self):
        with (
            mock.patch.object(config, "SONARR_API_KEY", "sk"),
            mock.patch.object(config, "RADARR_API_KEY", "rk"),
            self._patch_history(sonarr_error=True, radarr_error=True),
        ):
            feed = arr_client._build_activity_feed()
        self.assertFalse(feed["ok"])
        self.assertEqual(feed["sources"], {"sonarr": "error", "radarr": "error"})
        self.assertEqual(feed["items"], [])


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

    def body(self):
        self.wfile.seek(0)
        return json.loads(self.wfile.read().decode("utf-8"))


class ActivityHandlerTests(unittest.TestCase):
    def setUp(self):
        config._arr_cache.clear()

    def _feed(self, count, sources=None):
        return {
            "ok": True,
            "generatedAt": "2026-07-30T00:20:00Z",
            "sources": sources or {"sonarr": "ok", "radarr": "ok"},
            "items": [
                {
                    "id": f"sonarr:{index}",
                    "source": "sonarr",
                    "kind": "grabbed",
                    "title": "Show",
                    "subtitle": "",
                    "timestamp": f"2026-07-30T00:{index:02d}:00Z",
                    "href": None,
                }
                for index in range(count)
            ],
        }

    def test_returns_200_and_truncates_to_limit(self):
        with mock.patch.object(activity_routes, "_build_activity_feed", return_value=self._feed(25)):
            handler = _CaptureHandler()
            activity_routes.handle_activity_feed(handler, {"limit": ["3"]})
        self.assertEqual(handler.status, 200)
        body = handler.body()
        self.assertTrue(body["ok"])
        self.assertEqual(len(body["items"]), 3)

    def test_default_limit_is_20(self):
        with mock.patch.object(activity_routes, "_build_activity_feed", return_value=self._feed(25)):
            handler = _CaptureHandler()
            activity_routes.handle_activity_feed(handler, {})
        self.assertEqual(handler.status, 200)
        self.assertEqual(len(handler.body()["items"]), 20)

    def test_invalid_limit_falls_back_to_default(self):
        with mock.patch.object(activity_routes, "_build_activity_feed", return_value=self._feed(25)):
            handler = _CaptureHandler()
            activity_routes.handle_activity_feed(handler, {"limit": ["nope"]})
        self.assertEqual(handler.status, 200)
        self.assertEqual(len(handler.body()["items"]), 20)

    def test_502_when_both_sources_error(self):
        feed = self._feed(0, sources={"sonarr": "error", "radarr": "error"})
        feed["ok"] = False
        with mock.patch.object(activity_routes, "_build_activity_feed", return_value=feed):
            handler = _CaptureHandler()
            activity_routes.handle_activity_feed(handler, {})
        self.assertEqual(handler.status, 502)
        self.assertFalse(handler.body()["ok"])

    def test_200_with_partial_error_source(self):
        feed = self._feed(1, sources={"sonarr": "error", "radarr": "ok"})
        with mock.patch.object(activity_routes, "_build_activity_feed", return_value=feed):
            handler = _CaptureHandler()
            activity_routes.handle_activity_feed(handler, {})
        self.assertEqual(handler.status, 200)
        body = handler.body()
        self.assertEqual(body["sources"]["sonarr"], "error")
        self.assertEqual(len(body["items"]), 1)

    def test_feed_is_cached(self):
        with mock.patch.object(activity_routes, "_build_activity_feed", return_value=self._feed(1)) as build:
            activity_routes.handle_activity_feed(_CaptureHandler(), {})
            activity_routes.handle_activity_feed(_CaptureHandler(), {})
        build.assert_called_once()

    def test_unexpected_exception_logs_server_side_and_returns_static_error(self):
        with (
            mock.patch.object(activity_routes, "_get_activity_cached", side_effect=RuntimeError("secret-token")),
            mock.patch("builtins.print") as log,
        ):
            handler = _CaptureHandler()
            activity_routes.handle_activity_feed(handler, {})
        self.assertEqual(handler.status, 502)
        self.assertEqual(handler.body(), {"ok": False, "error": "Activity feed is temporarily unavailable"})
        self.assertNotIn("secret-token", json.dumps(handler.body()))
        log.assert_called_once_with("[activity] feed failed: secret-token", flush=True)


if __name__ == "__main__":
    unittest.main()
