import unittest
from types import SimpleNamespace
from unittest import mock

from routes import discover as routes


class DiscoverExclusionTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = routes.LibraryExclusionSnapshot.from_maps(
            {42: "movie-jf"}, {7: "tv-jf"}, status="fresh", last_successful_refresh_at="2026-08-11T12:00:00+00:00"
        )

    def test_snapshot_uses_composite_movie_and_tv_identity(self):
        snapshot = routes.LibraryExclusionSnapshot.from_maps({42: "movie-jf"}, {42: "tv-jf"}, status="fresh", last_successful_refresh_at="2026-08-11T12:00:00+00:00")
        self.assertTrue(snapshot.contains("movie", 42))
        self.assertTrue(snapshot.contains("tv", 42))
        self.assertFalse(self.snapshot.contains("movie", 7))
        self.assertEqual(snapshot.public(), {
            "status": "fresh",
            "last_successful_refresh_at": "2026-08-11T12:00:00+00:00",
        })

    def test_jellyseerr_filters_library_movie_without_title_matching(self):
        handler = SimpleNamespace()
        raw = [
            {"mediaType": "movie", "id": 42, "title": "Different title", "releaseDate": "2024-01-01"},
            {"mediaType": "tv", "id": 42, "name": "Keep same numeric id"},
        ]
        captured = {}
        with mock.patch.object(routes.settings, "JELLYSEERR_ENABLED", True), \
                mock.patch.object(routes.settings, "JELLYSEERR_API_KEY", "key"), \
                mock.patch.object(routes, "_jellyseerr_get", return_value={"results": raw}), \
                mock.patch.object(routes, "_library_exclusion_snapshot", return_value=self.snapshot), \
                mock.patch.object(routes, "send_json", side_effect=lambda _h, _s, payload: captured.update(payload)):
            routes.handle_discover_jellyseerr(handler, {"kind": ["trending"]})
        self.assertEqual([item["tmdb_id"] for item in captured["items"]], [42])
        self.assertEqual(captured["items"][0]["type"], "tv")

    def test_trakt_filters_library_movie_without_title_matching(self):
        handler = SimpleNamespace()
        raw = [
            {"title": "Different title", "year": 2024, "ids": {"tmdb": 42}},
            {"title": "Keep another movie", "year": 2025, "ids": {"tmdb": 7}},
        ]
        captured = {}
        with mock.patch.object(routes.settings, "TRAKT_CLIENT_ID", "id"), \
                mock.patch.object(routes.settings, "TRAKT_ACCESS_TOKEN", "token"), \
                mock.patch.object(routes, "_trakt_get", return_value=raw), \
                mock.patch.object(routes, "_library_exclusion_snapshot", return_value=self.snapshot), \
                mock.patch.object(routes, "send_json", side_effect=lambda _h, _s, payload: captured.update(payload)):
            routes.handle_discover_trakt(handler, {"type": ["movies"]})
        self.assertEqual([item["tmdb_id"] for item in captured["items"]], [7])
        self.assertEqual(captured["items"][0]["type"], "movie")

    def test_hermes_library_match_is_projected_to_history_without_store_mutation(self):
        item = {
            "id": "hermes-movie-42", "source": "hermes", "type": "movie", "title": "The Bear",
            "tmdb_id": 42, "active": True, "feedback": None,
        }
        projected = routes._hermes_item_for_client(item, self.snapshot)
        self.assertFalse(projected["active"])
        self.assertEqual(projected["excluded_reason"], "in_library")
        self.assertTrue(projected["in_library"])
        self.assertTrue(item["active"])

    def test_jellyfin_failure_keeps_last_good_map_as_stale(self):
        old_cache = dict(routes._TMDB_LIBRARY_CACHE)
        try:
            routes._TMDB_LIBRARY_CACHE.update(
                expires=0,
                movie={42: "movie-jf"},
                tv={},
                status="fresh",
                last_successful_refresh_at="2026-08-11T12:00:00+00:00",
            )
            with mock.patch.object(routes.settings, "JELLYFIN_API_KEY", "key"), \
                    mock.patch.object(routes, "_fetch_tmdb_map_for_type", side_effect=RuntimeError("down")):
                snapshot = routes._library_exclusion_snapshot()
            self.assertEqual(snapshot.status, "stale")
            self.assertTrue(snapshot.contains("movie", 42))
            self.assertEqual(snapshot.last_successful_refresh_at, "2026-08-11T12:00:00+00:00")
        finally:
            routes._TMDB_LIBRARY_CACHE.clear()
            routes._TMDB_LIBRARY_CACHE.update(old_cache)

    def test_second_jellyfin_fetch_failure_keeps_entire_last_good_snapshot(self):
        old_cache = dict(routes._TMDB_LIBRARY_CACHE)
        try:
            routes._TMDB_LIBRARY_CACHE.update(
                expires=0,
                movie={42: "old-movie-jf"},
                tv={7: "old-tv-jf"},
                status="fresh",
                last_successful_refresh_at="2026-08-11T12:00:00+00:00",
            )

            def fetch(item_type):
                if item_type == "Movie":
                    return {99: "new-movie-jf"}
                raise RuntimeError("series unavailable")

            with mock.patch.object(routes.settings, "JELLYFIN_API_KEY", "key"), \
                    mock.patch.object(routes, "_fetch_tmdb_map_for_type", side_effect=fetch):
                snapshot = routes._library_exclusion_snapshot()
            self.assertEqual(snapshot.movie, {42: "old-movie-jf"})
            self.assertEqual(snapshot.tv, {7: "old-tv-jf"})
            self.assertEqual(snapshot.status, "stale")
            self.assertEqual(snapshot.last_successful_refresh_at, "2026-08-11T12:00:00+00:00")
        finally:
            routes._TMDB_LIBRARY_CACHE.clear()
            routes._TMDB_LIBRARY_CACHE.update(old_cache)

    def test_successful_refresh_returns_new_maps_to_current_request(self):
        old_cache = dict(routes._TMDB_LIBRARY_CACHE)
        try:
            routes._TMDB_LIBRARY_CACHE.update(
                expires=0,
                movie={},
                tv={},
                status="unavailable",
                last_successful_refresh_at=None,
            )

            def fetch(item_type):
                return {42: "new-movie-jf"} if item_type == "Movie" else {7: "new-tv-jf"}

            with mock.patch.object(routes.settings, "JELLYFIN_API_KEY", "key"), \
                    mock.patch.object(routes, "_fetch_tmdb_map_for_type", side_effect=fetch):
                snapshot = routes._library_exclusion_snapshot()
            self.assertEqual(snapshot.movie, {42: "new-movie-jf"})
            self.assertEqual(snapshot.tv, {7: "new-tv-jf"})
            self.assertEqual(snapshot.status, "fresh")
        finally:
            routes._TMDB_LIBRARY_CACHE.clear()
            routes._TMDB_LIBRARY_CACHE.update(old_cache)

    def test_missing_jellyfin_key_keeps_cached_last_good_snapshot(self):
        old_cache = dict(routes._TMDB_LIBRARY_CACHE)
        try:
            routes._TMDB_LIBRARY_CACHE.update(
                expires=0,
                movie={42: "movie-jf"},
                tv={7: "tv-jf"},
                status="fresh",
                last_successful_refresh_at="2026-08-11T12:00:00+00:00",
            )
            with mock.patch.object(routes.settings, "JELLYFIN_API_KEY", ""):
                snapshot = routes._library_exclusion_snapshot()
            self.assertEqual(snapshot.movie, {42: "movie-jf"})
            self.assertEqual(snapshot.tv, {7: "tv-jf"})
            self.assertEqual(snapshot.status, "stale")
            self.assertEqual(snapshot.last_successful_refresh_at, "2026-08-11T12:00:00+00:00")
        finally:
            routes._TMDB_LIBRARY_CACHE.clear()
            routes._TMDB_LIBRARY_CACHE.update(old_cache)

    def test_hermes_get_projects_library_match_without_mutating_store(self):
        item = {
            "id": "hermes-movie-42", "source": "hermes", "type": "movie", "title": "The Bear",
            "tmdb_id": 42, "active": True, "feedback": None,
        }
        captured = {}
        store_data = {"version": 3, "revision": 4, "items": [item]}
        with mock.patch.object(routes.settings.RECOMMENDATIONS_STORE, "load", return_value=store_data), \
                mock.patch.object(routes, "_library_exclusion_snapshot", return_value=self.snapshot), \
                mock.patch.object(routes, "_enrich_hermes_posters", side_effect=lambda values: values), \
                mock.patch.object(routes, "_hermes_generation_context", return_value={}), \
                mock.patch.object(routes, "send_json", side_effect=lambda _h, _s, payload: captured.update(payload)):
            routes.handle_discover_hermes_get(SimpleNamespace())
        self.assertFalse(captured["items"][0]["active"])
        self.assertEqual(captured["items"][0]["excluded_reason"], "in_library")
        self.assertTrue(store_data["items"][0]["active"])


if __name__ == "__main__":
    unittest.main()
