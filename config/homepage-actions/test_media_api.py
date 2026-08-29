import io
import json
import unittest
from unittest import mock

import config
import media_state
from server import ActionsHandler
from routes import media


class _HandlerHarness:
    def __init__(self, path):
        self.handler = ActionsHandler.__new__(ActionsHandler)
        self.handler.path = path
        self.handler.headers = {}
        self.handler.wfile = io.BytesIO()
        self.handler.send_response = self._send_response
        self.handler.send_header = lambda _name, _value: None
        self.handler.end_headers = lambda: None
        self.status = None

    def _send_response(self, status):
        self.status = status

    def get(self):
        self.handler.do_GET()
        return self.status, json.loads(self.handler.wfile.getvalue())


class MediaApiDisabledTests(unittest.TestCase):
    def test_media_route_exposes_search_and_season_handlers(self):
        self.assertTrue(hasattr(media, "handle_media_search"))
        self.assertTrue(hasattr(media, "handle_media_tv_seasons"))

    def test_search_reports_disabled_without_calling_an_upstream(self):
        harness = _HandlerHarness("/media/search?q=alien")

        with mock.patch.object(config, "JELLYSEERR_ENABLED", False), mock.patch.object(
            config, "JELLYSEERR_API_KEY", ""
        ):
            status, payload = harness.get()

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["availability"], "disabled")
        self.assertEqual(payload["sources"], {"jellyseerr": "disabled"})
        self.assertEqual(payload["items"], [])


class MediaSearchApiTests(unittest.TestCase):
    def setUp(self):
        self.enabled = mock.patch.multiple(
            config, JELLYSEERR_ENABLED=True, JELLYSEERR_API_KEY="jellyseerr-key"
        )
        self.enabled.start()
        self.addCleanup(self.enabled.stop)

    def test_query_validation_is_strict_and_never_calls_jellyseerr(self):
        invalid_paths = (
            "/media/search",
            "/media/search?q=a",
            "/media/search?q=%20%20%20",
            f"/media/search?q={'x' * 101}",
            "/media/search?q=alien&q=arrival",
        )
        with mock.patch.object(media, "_jellyseerr_get") as upstream:
            responses = [_HandlerHarness(path).get() for path in invalid_paths]

        self.assertTrue(all(status == 400 for status, _payload in responses))
        self.assertTrue(all(payload == {
            "ok": False,
            "error": "Search query must contain 2 to 100 characters",
        } for _status, payload in responses))
        upstream.assert_not_called()

    def test_search_encodes_query_filters_people_and_resolves_typed_statuses(self):
        raw = [
            {
                "mediaType": "movie",
                "id": 42,
                "title": "Alien",
                "releaseDate": "1979-05-25",
                "overview": "A crew encounters something.",
                "posterPath": "/alien.jpg",
            },
            {
                "mediaType": "tv",
                "id": 42,
                "name": "Alien Worlds",
                "firstAirDate": "2020-12-02",
                "overview": "Documentary",
                "posterPath": "https://evil.example/poster.jpg?token=secret",
                "mediaInfo": {"requests": [{"id": 501, "status": 1}]},
            },
            {
                "mediaType": "movie",
                "id": 7,
                "title": "Tracked Movie",
                "releaseDate": "2024",
            },
            {"mediaType": "tv", "id": 8, "name": "Missing Show"},
            {"mediaType": "movie", "id": 9, "title": "Uncertain Movie"},
            {"mediaType": "person", "id": 99, "name": "Not media"},
        ]
        library = media_state.LibraryExclusionSnapshot.from_maps(
            {42: "jf-movie"},
            {},
            status="fresh",
            last_successful_refresh_at="2026-08-29T12:00:00+00:00",
        )
        arr = media_state.ArrTrackingSnapshot.from_maps(
            movie={
                7: {
                    "service": "radarr",
                    "monitored": True,
                    "titleSlug": "tracked-movie",
                    "serviceHref": "https://radarr.example/movie/tracked-movie",
                }
            },
            tv={},
            sources={"radarr": "stale", "sonarr": "fresh"},
        )

        with mock.patch.object(
            media, "_jellyseerr_get", return_value={"results": raw}
        ) as upstream, mock.patch.object(
            media, "get_library_exclusion_snapshot", return_value=library
        ), mock.patch.object(
            media, "get_arr_tracking_snapshot", return_value=arr
        ), mock.patch.object(
            config, "JELLYFIN_EXTERNAL_URL", "https://jellyfin.example"
        ):
            status, payload = _HandlerHarness(
                "/media/search?q=%20alien%20world%20"
            ).get()

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["availability"], "available")
        self.assertEqual(
            payload["sources"],
            {
                "jellyseerr": "fresh",
                "jellyfin": "fresh",
                "radarr": "stale",
                "sonarr": "fresh",
            },
        )
        upstream.assert_called_once_with("/api/v1/search?query=alien+world&page=1")
        self.assertEqual(
            [(item["identity"], item["status"]) for item in payload["items"]],
            [
                ("movie:42", "available"),
                ("tv:42", "requested"),
                ("movie:7", "tracked"),
                ("tv:8", "missing"),
                ("movie:9", "unknown"),
            ],
        )
        available, requested, tracked = payload["items"][:3]
        self.assertEqual(available["jellyfinId"], "jf-movie")
        self.assertEqual(
            available["serviceHref"],
            "https://jellyfin.example/web/index.html#!/details?id=jf-movie",
        )
        self.assertEqual(available["posterUrl"], "https://image.tmdb.org/t/p/w342/alien.jpg")
        self.assertEqual(requested["requestId"], 501)
        self.assertIsNone(requested["posterUrl"])
        self.assertNotIn("evil.example", json.dumps(payload))
        self.assertNotIn("secret", json.dumps(payload))
        self.assertEqual(tracked["service"], "radarr")
        self.assertTrue(tracked["monitored"])

    def test_configured_upstream_failure_is_sanitized_unavailable(self):
        with mock.patch.object(
            media,
            "_jellyseerr_get",
            side_effect=RuntimeError(
                "GET http://jellyseerr:5055/api/v1/search failed: key=jellyseerr-key body=/data/private"
            ),
        ):
            status, payload = _HandlerHarness("/media/search?q=alien").get()

        self.assertEqual(status, 502)
        self.assertEqual(
            payload,
            {
                "ok": False,
                "availability": "unavailable",
                "sources": {"jellyseerr": "unavailable"},
                "items": [],
                "error": "Media search is temporarily unavailable",
            },
        )
        serialized = json.dumps(payload)
        self.assertNotIn("jellyseerr-key", serialized)
        self.assertNotIn("/data/private", serialized)

    def test_partial_state_failure_keeps_catalog_item_but_marks_it_unknown(self):
        library = media_state.LibraryExclusionSnapshot.from_maps(
            {}, {}, status="unavailable", last_successful_refresh_at=None
        )
        arr = media_state.ArrTrackingSnapshot.from_maps(
            movie={},
            tv={},
            sources={"radarr": "fresh", "sonarr": "fresh"},
        )
        with mock.patch.object(
            media,
            "_jellyseerr_get",
            return_value={"results": [{"mediaType": "movie", "id": 20, "title": "Result"}]},
        ), mock.patch.object(
            media, "get_library_exclusion_snapshot", return_value=library
        ), mock.patch.object(media, "get_arr_tracking_snapshot", return_value=arr):
            status, payload = _HandlerHarness("/media/search?q=result").get()

        self.assertEqual(status, 200)
        self.assertEqual(payload["items"][0]["status"], "unknown")
        self.assertEqual(payload["sources"]["jellyfin"], "unavailable")

    def test_search_discards_non_integral_tmdb_identities(self):
        library = media_state.LibraryExclusionSnapshot.from_maps(
            {}, {}, status="fresh", last_successful_refresh_at=None
        )
        arr = media_state.ArrTrackingSnapshot.from_maps(
            movie={}, tv={}, sources={"radarr": "fresh", "sonarr": "fresh"}
        )
        with mock.patch.object(
            media,
            "_jellyseerr_get",
            return_value={
                "results": [
                    {"mediaType": "movie", "id": 1.5, "title": "Wrong identity"}
                ]
            },
        ), mock.patch.object(
            media, "get_library_exclusion_snapshot", return_value=library
        ), mock.patch.object(media, "get_arr_tracking_snapshot", return_value=arr):
            status, payload = _HandlerHarness("/media/search?q=wrong").get()

        self.assertEqual(status, 200)
        self.assertEqual(payload["items"], [])


class MediaSeasonsApiTests(unittest.TestCase):
    def setUp(self):
        self.enabled = mock.patch.multiple(
            config, JELLYSEERR_ENABLED=True, JELLYSEERR_API_KEY="jellyseerr-key"
        )
        self.enabled.start()
        self.addCleanup(self.enabled.stop)

    def test_seasons_are_sorted_and_include_specials(self):
        raw = {
            "name": "The Show",
            "seasons": [
                {"seasonNumber": 2, "name": "Season 2", "episodeCount": 8, "airDate": "2025-01-01"},
                {"seasonNumber": 0, "name": "Specials", "episodeCount": 3, "airDate": None},
                {"seasonNumber": 1, "name": "Season 1", "episodeCount": 10, "airDate": "2024-01-01"},
            ],
        }
        with mock.patch.object(media, "_jellyseerr_get", return_value=raw) as upstream:
            status, payload = _HandlerHarness("/media/tv/42/seasons").get()

        self.assertEqual(status, 200)
        upstream.assert_called_once_with("/api/v1/tv/42")
        self.assertEqual(payload["tmdbId"], 42)
        self.assertEqual(payload["title"], "The Show")
        self.assertEqual(
            [season["seasonNumber"] for season in payload["seasons"]], [0, 1, 2]
        )
        self.assertEqual(payload["seasons"][0]["name"], "Specials")

    def test_seasons_drop_non_date_upstream_urls(self):
        raw = {
            "name": "The Show",
            "seasons": [
                {
                    "seasonNumber": 1,
                    "name": "Season 1",
                    "episodeCount": 8,
                    "airDate": "http://internal/state?token=secret",
                }
            ],
        }
        with mock.patch.object(media, "_jellyseerr_get", return_value=raw):
            status, payload = _HandlerHarness("/media/tv/42/seasons").get()

        self.assertEqual(status, 200)
        self.assertIsNone(payload["seasons"][0]["airDate"])
        self.assertNotIn("internal", json.dumps(payload))
        self.assertNotIn("secret", json.dumps(payload))

    def test_season_id_validation_is_strict_and_sanitized(self):
        invalid_paths = (
            "/media/tv/0/seasons",
            "/media/tv/-1/seasons",
            "/media/tv/not-a-number/seasons",
            "/media/tv/1.5/seasons",
        )
        with mock.patch.object(media, "_jellyseerr_get") as upstream:
            responses = [_HandlerHarness(path).get() for path in invalid_paths]

        self.assertTrue(all(status == 400 for status, _payload in responses))
        self.assertTrue(all(payload == {
            "ok": False,
            "error": "TMDB id must be a positive integer",
        } for _status, payload in responses))
        upstream.assert_not_called()

    def test_oversized_numeric_season_id_is_rejected_without_an_exception(self):
        with mock.patch.object(media, "_jellyseerr_get") as upstream:
            try:
                status, payload = _HandlerHarness(
                    f"/media/tv/{'9' * 5000}/seasons"
                ).get()
            except ValueError as error:
                self.fail(f"numeric validation raised {type(error).__name__}")

        self.assertEqual(status, 400)
        self.assertEqual(
            payload,
            {"ok": False, "error": "TMDB id must be a positive integer"},
        )
        upstream.assert_not_called()

    def test_seasons_upstream_failure_never_exposes_the_raw_error(self):
        with mock.patch.object(
            media,
            "_jellyseerr_get",
            side_effect=RuntimeError("http://jellyseerr:5055 key=jellyseerr-key /state/private"),
        ):
            status, payload = _HandlerHarness("/media/tv/42/seasons").get()

        self.assertEqual(status, 502)
        self.assertEqual(
            payload,
            {"ok": False, "error": "TV seasons are temporarily unavailable"},
        )
        self.assertNotIn("jellyseerr-key", json.dumps(payload))
        self.assertNotIn("/state/private", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
