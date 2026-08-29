import unittest
from types import SimpleNamespace
from unittest import mock

import media_state
from routes import discover
from trakt_history import WatchedSnapshot


LIFECYCLE_KEYS = {
    "media_status",
    "service",
    "service_href",
    "request_id",
    "monitored",
}


class DiscoverLifecycleDecorationTests(unittest.TestCase):
    def test_shared_state_decorates_typed_items_with_all_wire_fields(self):
        library = media_state.LibraryExclusionSnapshot.from_maps(
            {1: "jf-movie-1"},
            {},
            status="fresh",
            last_successful_refresh_at="2026-08-29T12:00:00+00:00",
        )
        arr = media_state.ArrTrackingSnapshot.from_maps(
            movie={
                2: {
                    "service": "radarr",
                    "monitored": False,
                    "titleSlug": "movie-two",
                    "serviceHref": "https://radarr.example/movie/movie-two",
                }
            },
            tv={},
            sources={"radarr": "fresh", "sonarr": "fresh"},
        )
        jellyseerr = media_state.JellyseerrRequestSnapshot(
            states={"tv:1": {"status": "processing", "request_id": 88}},
            sources={
                "movie:1": "fresh",
                "tv:1": "fresh",
                "movie:2": "fresh",
                "movie:3": "fresh",
                "tv:4": "unavailable",
            },
        )
        items = [
            {"type": "movie", "tmdb_id": 1},
            {"type": "tv", "tmdb_id": 1},
            {"type": "movie", "tmdb_id": 2},
            {"type": "movie", "tmdb_id": 3},
            {"type": "tv", "tmdb_id": 4},
        ]
        with mock.patch.object(
            media_state, "get_library_exclusion_snapshot", return_value=library
        ), mock.patch.object(
            media_state, "get_arr_tracking_snapshot", return_value=arr
        ), mock.patch.object(
            media_state,
            "get_jellyseerr_request_snapshot",
            return_value=jellyseerr,
        ):
            decorated = discover._decorate_discover_lifecycle(items)

        for item in decorated:
            self.assertTrue(LIFECYCLE_KEYS.issubset(item))
        self.assertEqual(decorated[0]["media_status"], "available")
        self.assertEqual(decorated[0]["service"], "jellyfin")
        self.assertEqual(decorated[1]["media_status"], "processing")
        self.assertEqual(decorated[1]["request_id"], 88)
        self.assertEqual(decorated[2]["media_status"], "tracked")
        self.assertEqual(decorated[2]["service"], "radarr")
        self.assertFalse(decorated[2]["monitored"])
        self.assertEqual(decorated[3]["media_status"], "missing")
        self.assertEqual(decorated[4]["media_status"], "unknown")

    def _wire_decorator(self, items, **_kwargs):
        for item in items:
            item.update(
                media_status="requested",
                service=None,
                service_href=None,
                request_id=91,
                monitored=None,
            )
        return items

    def test_hermes_projection_keeps_compatibility_and_adds_lifecycle(self):
        item = {
            "id": "hermes-movie-42",
            "source": "hermes",
            "type": "movie",
            "title": "Title",
            "tmdb_id": 42,
            "active": False,
            "feedback": None,
            "request_state": "requested",
            "request_provider": "jellyseerr",
            "jellyseerr_request_id": 91,
        }
        captured = {}
        library = media_state.LibraryExclusionSnapshot.from_maps(
            {}, {}, status="fresh", last_successful_refresh_at=None
        )
        with mock.patch.object(
            discover.settings.RECOMMENDATIONS_STORE,
            "load",
            return_value={"version": 4, "items": [item]},
        ), mock.patch.object(
            discover, "_library_exclusion_snapshot", return_value=library
        ), mock.patch.object(
            discover,
            "_trakt_watched_snapshot",
            return_value=WatchedSnapshot(frozenset(), None, "fresh"),
        ), mock.patch.object(
            discover, "_enrich_hermes_posters", side_effect=lambda values: values
        ), mock.patch.object(
            discover,
            "_decorate_discover_lifecycle",
            side_effect=self._wire_decorator,
        ), mock.patch.object(
            discover,
            "send_json",
            side_effect=lambda _handler, _status, payload: captured.update(payload),
        ):
            discover.handle_discover_hermes_get(SimpleNamespace())

        public = captured["items"][0]
        self.assertTrue(LIFECYCLE_KEYS.issubset(public))
        self.assertEqual(public["request_state"], "requested")
        self.assertEqual(public["request_provider"], "jellyseerr")
        self.assertEqual(public["jellyseerr_request_id"], 91)

    def test_jellyseerr_and_trakt_handlers_apply_lifecycle_before_sending(self):
        library = media_state.LibraryExclusionSnapshot.from_maps(
            {}, {}, status="fresh", last_successful_refresh_at=None
        )
        watched = WatchedSnapshot(frozenset(), None, "fresh")
        for source in ("jellyseerr", "trakt"):
            captured = {}
            common = (
                mock.patch.object(discover, "_library_exclusion_snapshot", return_value=library),
                mock.patch.object(discover, "_trakt_watched_snapshot", return_value=watched),
                mock.patch.object(
                    discover,
                    "_decorate_discover_lifecycle",
                    side_effect=self._wire_decorator,
                ),
                mock.patch.object(
                    discover,
                    "send_json",
                    side_effect=lambda _handler, _status, payload: captured.update(payload),
                ),
            )
            if source == "jellyseerr":
                specific = (
                    mock.patch.object(discover.settings, "JELLYSEERR_ENABLED", True),
                    mock.patch.object(discover.settings, "JELLYSEERR_API_KEY", "key"),
                    mock.patch.object(
                        discover,
                        "_jellyseerr_get",
                        return_value={
                            "results": [
                                {"mediaType": "movie", "id": 42, "title": "Title"}
                            ]
                        },
                    ),
                )
                query = {"kind": ["movies"]}
                handler = discover.handle_discover_jellyseerr
            else:
                specific = (
                    mock.patch.object(discover.settings, "TRAKT_CLIENT_ID", "client"),
                    mock.patch.object(
                        discover,
                        "_trakt_get",
                        return_value=[
                            {"title": "Title", "ids": {"tmdb": 42, "slug": "title"}}
                        ],
                    ),
                    mock.patch.object(discover, "_jellyseerr_poster_path", return_value=None),
                )
                query = {"type": ["movies"]}
                handler = discover.handle_discover_trakt

            with common[0], common[1], common[2], common[3], specific[0], specific[1], specific[2]:
                handler(SimpleNamespace(), query)

            with self.subTest(source=source):
                self.assertTrue(LIFECYCLE_KEYS.issubset(captured["items"][0]))


if __name__ == "__main__":
    unittest.main()
