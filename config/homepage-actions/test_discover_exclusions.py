import time
import unittest
from types import SimpleNamespace
from unittest import mock

from routes import discover as routes
from clients.trakt import TraktAuthError
from trakt_history import WatchedSnapshot


class TrackedArrCacheTests(unittest.TestCase):
    def setUp(self):
        self.original_cache = dict(routes._tracked_media_cache)
        routes._tracked_media_cache.update(
            {"expires": 0.0, "ids": [], "errors": [], "has_success": False}
        )
        self.addCleanup(routes._tracked_media_cache.clear)
        self.addCleanup(routes._tracked_media_cache.update, self.original_cache)

    def test_success_then_total_failure_preserves_last_good_combined_set(self):
        with mock.patch.object(
            routes, "TRACKED_MEDIA_CACHE_TTL", 60.0
        ), mock.patch.object(
            routes.time, "monotonic", return_value=100.0
        ), mock.patch.object(
            routes,
            "_build_tracked_media_ids",
            side_effect=[
                (["movie:101", "tv:202"], []),
                ([], ["radarr: unavailable", "sonarr: unavailable"]),
            ],
        ) as build_tracked:
            self.assertEqual(
                routes._get_tracked_media_ids(), (["movie:101", "tv:202"], [])
            )
            routes._tracked_media_cache["expires"] = 0.0
            ids, errors = routes._get_tracked_media_ids()
            cached_ids, cached_errors = routes._get_tracked_media_ids()

        self.assertEqual(ids, ["movie:101", "tv:202"])
        self.assertEqual(errors, ["radarr: unavailable", "sonarr: unavailable"])
        self.assertEqual(cached_ids, ids)
        self.assertEqual(cached_errors, errors)
        self.assertEqual(routes._tracked_media_cache["expires"], 115.0)
        self.assertEqual(build_tracked.call_count, 2)

    def test_success_then_one_provider_failure_preserves_complete_last_good_set(self):
        with mock.patch.object(
            routes,
            "_build_tracked_media_ids",
            side_effect=[
                (["movie:101", "tv:202"], []),
                (["movie:101"], ["sonarr: unavailable"]),
            ],
        ):
            routes._get_tracked_media_ids()
            routes._tracked_media_cache["expires"] = 0.0
            ids, errors = routes._get_tracked_media_ids()

        self.assertEqual(ids, ["movie:101", "tv:202"])
        self.assertEqual(errors, ["sonarr: unavailable"])

    def test_forced_refresh_bypasses_a_live_tracked_cache(self):
        routes._tracked_media_cache.update(
            {"expires": 9999.0, "ids": ["movie:101"], "errors": [], "has_success": True}
        )
        with mock.patch.object(routes.time, "monotonic", return_value=100.0), \
             mock.patch.object(routes, "_build_tracked_media_ids", return_value=(["movie:202"], [])):
            ids, errors = routes._get_tracked_media_ids(force=True)

        self.assertEqual(ids, ["movie:202"])
        self.assertEqual(errors, [])


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
        self.assertEqual(
            responses,
            [(502, {"ok": False, "error": "Jellyseerr is temporarily unavailable"})],
        )
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
            "media_status": "unknown",
            "service": None,
            "service_href": None,
            "request_id": None,
            "monitored": None,
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
                mock.patch.object(routes, "_trakt_get", return_value=raw), \
                mock.patch.object(routes, "_library_exclusion_snapshot", return_value=self.snapshot), \
                mock.patch.object(routes, "send_json", side_effect=lambda _h, _s, payload: captured.update(payload)):
            routes.handle_discover_trakt(handler, {"type": ["movies"]})
        self.assertEqual([item["tmdb_id"] for item in captured["items"]], [7])
        self.assertEqual(captured["items"][0]["type"], "movie")

    def test_ai_picks_library_match_is_projected_to_history_without_store_mutation(self):
        item = {
            "id": "ai-movie-42", "source": "ai", "type": "movie", "title": "The Bear",
            "tmdb_id": 42, "active": True, "feedback": None,
        }
        projected = routes._ai_picks_item_for_client(item, self.snapshot)
        self.assertFalse(projected["active"])
        self.assertEqual(projected["excluded_reason"], "in_library")
        self.assertTrue(projected["in_library"])
        self.assertTrue(item["active"])

    def _ai_picks_get(self, items, *, watched, library=None):
        captured = {}
        library = library or routes.LibraryExclusionSnapshot.from_maps(
            {}, {}, status="fresh", last_successful_refresh_at=None
        )
        store_data = {"version": 4, "revision": 4, "items": items}
        with mock.patch.object(routes.settings.RECOMMENDATIONS_STORE, "load", return_value=store_data), \
                mock.patch.object(routes, "_library_exclusion_snapshot", return_value=library), \
                mock.patch.object(routes, "_trakt_watched_snapshot", return_value=watched) as watched_snapshot, \
                mock.patch.object(routes, "_enrich_ai_picks_posters", side_effect=lambda values: values), \
                mock.patch.object(routes, "_ai_picks_generation_context", return_value={}), \
                mock.patch.object(routes, "send_json", side_effect=lambda _h, _s, payload: captured.update(payload)):
            routes.handle_discover_ai_picks_get(SimpleNamespace())
        watched_snapshot.assert_called_once_with()
        return captured, store_data

    def test_ai_picks_get_projects_active_watched_match_without_feedback(self):
        item = {
            "id": "ai-movie-7", "source": "ai", "type": "movie", "title": "Watched",
            "tmdb_id": 7, "active": True, "feedback": None,
        }
        watched = WatchedSnapshot(frozenset({"movie:7"}), "2026-08-11T12:00:00+00:00", "fresh")
        captured, store_data = self._ai_picks_get([item], watched=watched)
        projected = captured["items"][0]
        self.assertFalse(projected["active"])
        self.assertEqual(projected["excluded_reason"], "watched_on_trakt")
        self.assertTrue(projected["watched_on_trakt"])
        self.assertIsNone(projected["feedback"])
        self.assertTrue(store_data["items"][0]["active"])

    def test_ai_picks_get_projects_inactive_watched_match_without_reactivating_it(self):
        item = {
            "id": "ai-movie-8", "source": "ai", "type": "movie", "title": "Archived",
            "tmdb_id": 8, "active": False, "feedback": None,
        }
        watched = WatchedSnapshot(frozenset({"movie:8"}), "2026-08-11T12:00:00+00:00", "stale")
        captured, _ = self._ai_picks_get([item], watched=watched)
        projected = captured["items"][0]
        self.assertFalse(projected["active"])
        self.assertEqual(projected["excluded_reason"], "watched_on_trakt")
        self.assertTrue(projected["watched_on_trakt"])

    def test_ai_picks_get_preserves_feedback_and_request_fields_for_watched_match(self):
        item = {
            "id": "ai-movie-9", "source": "ai", "type": "movie", "title": "Liked watched",
            "tmdb_id": 9, "active": True, "feedback": "liked", "feedback_at": "2026-01-01T00:00:00Z",
            "request_state": "requested", "request_provider": "jellyseerr",
            "requested_at": "2026-01-02T00:00:00Z",
            "jellyseerr_request_id": 55,
        }
        watched = WatchedSnapshot(frozenset({"movie:9"}), "2026-08-11T12:00:00+00:00", "fresh")
        captured, store_data = self._ai_picks_get([item], watched=watched)
        projected = captured["items"][0]
        self.assertFalse(projected["active"])
        self.assertEqual(projected["excluded_reason"], "watched_on_trakt")
        self.assertTrue(projected["watched_on_trakt"])
        self.assertEqual(projected["feedback"], "liked")
        self.assertEqual(projected["feedback_at"], item["feedback_at"])
        self.assertEqual(projected["request_state"], item["request_state"])
        self.assertEqual(projected["request_provider"], item["request_provider"])
        self.assertEqual(projected["requested_at"], item["requested_at"])
        self.assertEqual(projected["jellyseerr_request_id"], item["jellyseerr_request_id"])
        self.assertEqual(store_data["items"], [item])

    def test_ai_picks_get_library_takes_precedence_while_retaining_watched_flag(self):
        item = {
            "id": "ai-movie-42", "source": "ai", "type": "movie", "title": "Both",
            "tmdb_id": 42, "active": True, "feedback": None,
        }
        watched = WatchedSnapshot(frozenset({"movie:42"}), "2026-08-11T12:00:00+00:00", "fresh")
        captured, _ = self._ai_picks_get([item], watched=watched, library=self.snapshot)
        projected = captured["items"][0]
        self.assertFalse(projected["active"])
        self.assertEqual(projected["excluded_reason"], "in_library")
        self.assertTrue(projected["in_library"])
        self.assertTrue(projected["watched_on_trakt"])

    def test_ai_picks_get_public_response_drops_private_item_fields_and_context(self):
        item = {
            "id": "ai-movie-42", "identity": "movie:42", "source": "ai",
            "type": "movie", "title": "Public title", "year": 2026, "tmdb_id": 42,
            "reason": "fixture", "active": True, "feedback": None,
            "feedback_at": None, "request_state": None, "request_provider": None,
            "requested_at": None,
            "jellyseerr_request_id": None, "added_at": "2026-01-01T00:00:00Z",
            "watched_identities": ["movie:42"], "watched_at": "private-history",
            "token": "private-token", "provider_metadata": {"secret": "value"},
        }
        captured = {}
        store_data = {"version": 4, "revision": 4, "items": [item]}
        with mock.patch.object(routes.settings.RECOMMENDATIONS_STORE, "load", return_value=store_data), \
                mock.patch.object(routes, "_library_exclusion_snapshot", return_value=self.snapshot), \
                mock.patch.object(routes, "_trakt_watched_snapshot", return_value=WatchedSnapshot(frozenset(), None, "fresh")), \
                mock.patch.object(routes, "_enrich_ai_picks_posters", side_effect=lambda values: values), \
                mock.patch.object(routes, "_ai_picks_generation_context", return_value={"watched_media_ids": ["movie:42"], "secret": "value"}), \
                mock.patch.object(routes, "send_json", side_effect=lambda _h, _s, payload: captured.update(payload)):
            routes.handle_discover_ai_picks_get(SimpleNamespace())

        self.assertNotIn("context", captured)
        public_item = captured["items"][0]
        self.assertEqual(public_item["title"], "Public title")
        self.assertIsNone(public_item["request_provider"])
        self.assertNotIn("identity", public_item)
        self.assertNotIn("watched_identities", public_item)
        self.assertNotIn("watched_at", public_item)
        self.assertNotIn("token", public_item)
        self.assertNotIn("provider_metadata", public_item)

    def test_ai_picks_get_public_response_keeps_exclusion_badges(self):
        item = {
            "id": "ai-movie-42", "source": "ai", "type": "movie", "title": "Watched",
            "tmdb_id": 42, "active": True, "feedback": None,
        }
        captured, _ = self._ai_picks_get(
            [item],
            watched=WatchedSnapshot(frozenset({"movie:42"}), "2026-08-11T12:00:00+00:00", "fresh"),
        )
        self.assertEqual(captured["items"][0]["excluded_reason"], "watched_on_trakt")
        self.assertTrue(captured["items"][0]["watched_on_trakt"])
        self.assertEqual(captured["watched_exclusion"]["status"], "fresh")

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

    def test_forced_library_refresh_bypasses_a_live_cache(self):
        old_cache = dict(routes._TMDB_LIBRARY_CACHE)
        try:
            routes._TMDB_LIBRARY_CACHE.update(
                expires=time.time() + 3600,
                movie={42: "old-movie-jf"},
                tv={},
                status="fresh",
                last_successful_refresh_at="2026-08-11T12:00:00+00:00",
            )

            def fetch(item_type):
                return {99: "new-movie-jf"} if item_type == "Movie" else {}

            with mock.patch.object(routes.settings, "JELLYFIN_API_KEY", "key"), \
                 mock.patch.object(routes, "_fetch_tmdb_map_for_type", side_effect=fetch):
                snapshot = routes._library_exclusion_snapshot(force=True)

            self.assertEqual(snapshot.movie, {99: "new-movie-jf"})
            self.assertFalse(snapshot.contains("movie", 42))
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

    def test_ai_picks_get_projects_library_match_without_mutating_store(self):
        item = {
            "id": "ai-movie-42", "source": "ai", "type": "movie", "title": "The Bear",
            "tmdb_id": 42, "active": True, "feedback": None,
        }
        captured = {}
        store_data = {"version": 4, "revision": 4, "items": [item]}
        with mock.patch.object(routes.settings.RECOMMENDATIONS_STORE, "load", return_value=store_data), \
                mock.patch.object(routes, "_library_exclusion_snapshot", return_value=self.snapshot), \
                mock.patch.object(routes, "_enrich_ai_picks_posters", side_effect=lambda values: values), \
                mock.patch.object(routes, "_ai_picks_generation_context", return_value={}), \
                mock.patch.object(routes, "send_json", side_effect=lambda _h, _s, payload: captured.update(payload)):
            routes.handle_discover_ai_picks_get(SimpleNamespace())
        self.assertFalse(captured["items"][0]["active"])
        self.assertEqual(captured["items"][0]["excluded_reason"], "in_library")
        self.assertTrue(store_data["items"][0]["active"])


class DiscoverLibraryCacheInvalidationTests(unittest.TestCase):
    def setUp(self):
        self.original = {
            "expires": routes._TMDB_LIBRARY_CACHE["expires"],
            "movie": dict(routes._TMDB_LIBRARY_CACHE["movie"]),
            "tv": dict(routes._TMDB_LIBRARY_CACHE["tv"]),
            "status": routes._TMDB_LIBRARY_CACHE["status"],
            "last_successful_refresh_at": routes._TMDB_LIBRARY_CACHE[
                "last_successful_refresh_at"
            ],
        }
        self.original_tracked = dict(routes._tracked_media_cache)
        routes._TMDB_LIBRARY_CACHE.update(
            {
                "expires": 9999.0,
                "movie": {1: "jf-1"},
                "tv": {2: "jf-2"},
                "status": "fresh",
                "last_successful_refresh_at": "2026-08-13T12:00:00+00:00",
            }
        )
        routes._tracked_media_cache.update({"expires": 9999.0})

        def restore():
            routes._TMDB_LIBRARY_CACHE.update(self.original)
            routes._tracked_media_cache.clear()
            routes._tracked_media_cache.update(self.original_tracked)

        self.addCleanup(restore)

    def test_invalidate_preserves_last_good_maps(self):
        routes.invalidate_discover_library_caches()
        self.assertEqual(routes._TMDB_LIBRARY_CACHE["expires"], 0.0)
        self.assertEqual(routes._TMDB_LIBRARY_CACHE["status"], "stale")
        self.assertEqual(routes._TMDB_LIBRARY_CACHE["movie"], {1: "jf-1"})
        self.assertEqual(routes._TMDB_LIBRARY_CACHE["tv"], {2: "jf-2"})
        self.assertEqual(
            routes._TMDB_LIBRARY_CACHE["last_successful_refresh_at"],
            "2026-08-13T12:00:00+00:00",
        )
        self.assertEqual(routes._tracked_media_cache["expires"], 0.0)

    def test_invalidate_without_last_good_stays_unavailable(self):
        routes._TMDB_LIBRARY_CACHE["last_successful_refresh_at"] = None
        routes._TMDB_LIBRARY_CACHE["status"] = "unavailable"
        routes._TMDB_LIBRARY_CACHE["movie"] = {}
        routes._TMDB_LIBRARY_CACHE["tv"] = {}
        routes.invalidate_discover_library_caches()
        self.assertEqual(routes._TMDB_LIBRARY_CACHE["status"], "unavailable")
        self.assertIsNone(routes._TMDB_LIBRARY_CACHE["last_successful_refresh_at"])


if __name__ == "__main__":
    unittest.main()
