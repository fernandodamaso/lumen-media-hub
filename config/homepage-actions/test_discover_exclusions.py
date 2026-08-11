import unittest
from types import SimpleNamespace
from unittest import mock

from routes import discover as routes
from trakt_history import WatchedSnapshot


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

    def _jellyseerr_discover(self, raw, *, kind="trending", watched=None, library=None):
        captured = {}
        library = library or routes.LibraryExclusionSnapshot.from_maps(
            {}, {}, status="fresh", last_successful_refresh_at=None
        )
        with mock.patch.object(routes.settings, "JELLYSEERR_ENABLED", True), \
                mock.patch.object(routes.settings, "JELLYSEERR_API_KEY", "key"), \
                mock.patch.object(routes, "_jellyseerr_get", return_value={"results": raw}), \
                mock.patch.object(routes, "_library_exclusion_snapshot", return_value=library), \
                mock.patch.object(routes, "_trakt_watched_snapshot", return_value=watched) as watched_snapshot, \
                mock.patch.object(routes, "send_json", side_effect=lambda _h, _s, payload: captured.update(payload)):
            routes.handle_discover_jellyseerr(SimpleNamespace(), {"kind": [kind]})
        return captured, watched_snapshot

    def test_jellyseerr_trending_filters_watched_movie_and_keeps_unwatched_item(self):
        watched = WatchedSnapshot(frozenset({"movie:42"}), "2026-08-11T12:00:00+00:00", "fresh")
        captured, watched_snapshot = self._jellyseerr_discover(
            [
                {"mediaType": "movie", "id": 42, "title": "Watched"},
                {"mediaType": "movie", "id": 7, "title": "Unwatched"},
            ],
            watched=watched,
        )
        self.assertEqual([item["tmdb_id"] for item in captured["items"]], [7])
        self.assertEqual(captured["watched_exclusion"], watched.public())
        watched_snapshot.assert_called_once_with()

    def test_jellyseerr_movie_feed_filters_watched_movie(self):
        watched = WatchedSnapshot(frozenset({"movie:42"}), "2026-08-11T12:00:00+00:00", "fresh")
        captured, _ = self._jellyseerr_discover(
            [{"mediaType": "movie", "id": 42, "title": "Watched"}],
            kind="movies",
            watched=watched,
        )
        self.assertEqual(captured["items"], [])

    def test_jellyseerr_tv_feed_filters_watched_show(self):
        watched = WatchedSnapshot(frozenset({"tv:42"}), "2026-08-11T12:00:00+00:00", "fresh")
        captured, _ = self._jellyseerr_discover(
            [{"mediaType": "tv", "id": 42, "name": "Watched show"}],
            kind="tv",
            watched=watched,
        )
        self.assertEqual(captured["items"], [])

    def test_jellyseerr_watched_movie_does_not_filter_tv_with_same_numeric_id(self):
        watched = WatchedSnapshot(frozenset({"movie:123"}), "2026-08-11T12:00:00+00:00", "fresh")
        captured, _ = self._jellyseerr_discover(
            [{"mediaType": "tv", "id": 123, "name": "Unwatched show"}],
            kind="tv",
            watched=watched,
        )
        self.assertEqual([item["tmdb_id"] for item in captured["items"]], [123])

    def test_jellyseerr_stale_snapshot_filters_and_reports_stale(self):
        watched = WatchedSnapshot(frozenset({"movie:42"}), "2026-08-11T11:00:00+00:00", "stale")
        captured, _ = self._jellyseerr_discover(
            [{"mediaType": "movie", "id": 42, "title": "Watched"}], watched=watched
        )
        self.assertEqual(captured["items"], [])
        self.assertEqual(captured["watched_exclusion"], watched.public())

    def test_jellyseerr_unavailable_snapshot_keeps_cards_and_reports_unavailable(self):
        watched = WatchedSnapshot(frozenset(), None, "unavailable")
        captured, _ = self._jellyseerr_discover(
            [{"mediaType": "movie", "id": 42, "title": "Keep"}], watched=watched
        )
        self.assertEqual([item["tmdb_id"] for item in captured["items"]], [42])
        self.assertEqual(captured["watched_exclusion"], watched.public())

    def test_jellyseerr_failure_preserves_error_and_does_not_fetch_watched(self):
        responses = []
        with mock.patch.object(routes.settings, "JELLYSEERR_ENABLED", True), \
                mock.patch.object(routes.settings, "JELLYSEERR_API_KEY", "key"), \
                mock.patch.object(routes, "_jellyseerr_get", side_effect=RuntimeError("upstream down")), \
                mock.patch.object(routes, "_trakt_watched_snapshot") as watched_snapshot, \
                mock.patch.object(routes, "send_json", side_effect=lambda _h, status, payload: responses.append((status, payload))):
            routes.handle_discover_jellyseerr(SimpleNamespace(), {"kind": ["movies"]})
        self.assertEqual(responses, [(502, {"ok": False, "error": "upstream down"})])
        watched_snapshot.assert_not_called()

    def test_jellyseerr_library_and_watched_exclusions_preserve_card_metadata(self):
        watched = WatchedSnapshot(frozenset({"movie:7"}), "2026-08-11T12:00:00+00:00", "fresh")
        library = routes.LibraryExclusionSnapshot.from_maps(
            {42: "jellyfin-movie"}, {}, status="fresh", last_successful_refresh_at="2026-08-11T12:00:00+00:00"
        )
        captured, _ = self._jellyseerr_discover(
            [
                {"mediaType": "movie", "id": 42, "title": "Library", "posterPath": "/library.jpg"},
                {"mediaType": "movie", "id": 7, "title": "Watched", "posterPath": "/watched.jpg"},
                {"mediaType": "movie", "id": 9, "title": "Keep", "posterPath": "/keep.jpg", "voteAverage": 8.2},
            ],
            watched=watched,
            library=library,
        )
        self.assertEqual(captured["items"], [{
            "id": "seerr-movie-9",
            "source": "jellyseerr",
            "type": "movie",
            "title": "Keep",
            "year": None,
            "tmdb_id": 9,
            "overview": "",
            "poster_path": "/keep.jpg",
            "poster_url": "https://image.tmdb.org/t/p/w342/keep.jpg",
            "rating": 8.2,
        }])
        self.assertEqual(captured["library_exclusion"], library.public())
        self.assertEqual(captured["watched_exclusion"], watched.public())

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
