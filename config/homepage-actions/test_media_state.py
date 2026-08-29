import copy
import importlib.util
import unittest
from unittest import mock

import media_state


class MediaStateBoundaryTests(unittest.TestCase):
    def test_shared_media_state_boundary_exists(self):
        self.assertIsNotNone(importlib.util.find_spec("media_state"))

    def test_shared_media_state_boundary_exposes_cache_and_resolution_contracts(self):
        expected = {
            "ArrTrackingSnapshot",
            "LibraryExclusionSnapshot",
            "build_service_href",
            "get_arr_tracking_snapshot",
            "get_library_exclusion_snapshot",
            "jellyseerr_request_state",
            "resolve_media_state",
        }
        missing = sorted(name for name in expected if not hasattr(media_state, name))
        self.assertEqual(missing, [])


class ArrTrackingSnapshotTests(unittest.TestCase):
    def setUp(self):
        with media_state._ARR_TRACKING_CACHE_LOCK:
            self.original = copy.deepcopy(media_state._ARR_TRACKING_CACHE)
            media_state._ARR_TRACKING_CACHE.clear()

        def restore():
            with media_state._ARR_TRACKING_CACHE_LOCK:
                media_state._ARR_TRACKING_CACHE.clear()
                media_state._ARR_TRACKING_CACHE.update(self.original)

        self.addCleanup(restore)

    def test_arr_snapshot_keeps_typed_ids_and_builds_links_from_safe_slugs(self):
        responses = {
            "http://radarr:7878": [
                {"tmdbId": 42, "titleSlug": "same/movie", "monitored": True}
            ],
            "http://sonarr:8989": [
                {"tmdbId": 42, "titleSlug": "same-show", "monitored": False}
            ],
        }

        with mock.patch.object(media_state.settings, "RADARR_API_KEY", "radarr-key"), mock.patch.object(
            media_state.settings, "SONARR_API_KEY", "sonarr-key"
        ), mock.patch.object(
            media_state.settings, "RADARR_EXTERNAL_URL", "https://radarr.example"
        ), mock.patch.object(
            media_state.settings, "SONARR_EXTERNAL_URL", "https://sonarr.example/base"
        ), mock.patch.object(
            media_state, "_arr_get", side_effect=lambda base, _key, _path: responses[base]
        ):
            snapshot = media_state.get_arr_tracking_snapshot(force=True)

        movie = snapshot.get("movie", 42)
        show = snapshot.get("tv", 42)
        self.assertIsNotNone(movie)
        self.assertIsNotNone(show)
        self.assertEqual(movie.service, "radarr")
        self.assertTrue(movie.monitored)
        self.assertEqual(movie.title_slug, "same/movie")
        self.assertEqual(
            movie.service_href, "https://radarr.example/movie/same%2Fmovie"
        )
        self.assertEqual(show.service, "sonarr")
        self.assertFalse(show.monitored)
        self.assertEqual(
            show.service_href, "https://sonarr.example/base/series/same-show"
        )
        self.assertEqual(snapshot.sources, {"radarr": "fresh", "sonarr": "fresh"})

    def test_arr_refresh_failure_keeps_only_that_sources_last_good_state(self):
        rounds = {
            "http://radarr:7878": [
                [{"tmdbId": 7, "titleSlug": "old-movie", "monitored": True}],
                RuntimeError("http://radarr:7878/api/v3/movie?apikey=secret"),
            ],
            "http://sonarr:8989": [
                [{"tmdbId": 8, "titleSlug": "old-show", "monitored": True}],
                [{"tmdbId": 9, "titleSlug": "new-show", "monitored": False}],
            ],
        }

        def fetch(base, _key, _path):
            result = rounds[base].pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with mock.patch.object(media_state.settings, "RADARR_API_KEY", "radarr-key"), mock.patch.object(
            media_state.settings, "SONARR_API_KEY", "sonarr-key"
        ), mock.patch.object(media_state, "_arr_get", side_effect=fetch):
            media_state.get_arr_tracking_snapshot(force=True)
            snapshot = media_state.get_arr_tracking_snapshot(force=True)

        self.assertEqual(snapshot.sources, {"radarr": "stale", "sonarr": "fresh"})
        self.assertIsNotNone(snapshot.get("movie", 7))
        self.assertIsNone(snapshot.get("tv", 8))
        self.assertIsNotNone(snapshot.get("tv", 9))
        self.assertNotIn("secret", repr(snapshot))
        self.assertNotIn("http://radarr", repr(snapshot))

    def test_unsafe_external_base_never_reaches_a_service_link(self):
        self.assertIsNone(
            media_state.build_service_href(
                "radarr",
                "safe-slug",
                "https://user:secret@radarr.example/movie?apikey=secret",
            )
        )


class MediaStatusResolutionTests(unittest.TestCase):
    def setUp(self):
        self.library = media_state.LibraryExclusionSnapshot.from_maps(
            {1: "jf-1"},
            {},
            status="fresh",
            last_successful_refresh_at="2026-08-29T12:00:00+00:00",
        )
        self.arr = media_state.ArrTrackingSnapshot.from_maps(
            movie={
                1: {
                    "service": "radarr",
                    "monitored": True,
                    "titleSlug": "one",
                    "serviceHref": "https://radarr.example/movie/one",
                },
                4: {
                    "service": "radarr",
                    "monitored": False,
                    "titleSlug": "four",
                    "serviceHref": "https://radarr.example/movie/four",
                },
            },
            tv={},
            sources={"radarr": "fresh", "sonarr": "fresh"},
        )

    def resolve(self, tmdb_id, *, request=None, library=None, arr=None):
        return media_state.resolve_media_state(
            "movie",
            tmdb_id,
            library=library or self.library,
            arr=arr or self.arr,
            jellyseerr=request,
            jellyseerr_status="fresh",
        )

    def test_positive_jellyfin_match_has_highest_precedence(self):
        stale_library = media_state.LibraryExclusionSnapshot.from_maps(
            {1: "jf-1"},
            {},
            status="stale",
            last_successful_refresh_at="2026-08-29T12:00:00+00:00",
        )
        state = self.resolve(
            1,
            request={"status": "requested", "request_id": 91},
            library=stale_library,
        )
        self.assertEqual(state["status"], "available")
        self.assertEqual(state["service"], "jellyfin")
        self.assertEqual(state["jellyfinId"], "jf-1")

    def test_active_jellyseerr_states_precede_arr_tracking(self):
        requested = self.resolve(4, request={"status": "requested", "request_id": 94})
        processing = self.resolve(4, request={"status": "processing", "request_id": 95})
        self.assertEqual((requested["status"], requested.get("requestId")), ("requested", 94))
        self.assertEqual((processing["status"], processing.get("requestId")), ("processing", 95))

    def test_positive_stale_arr_match_remains_tracked(self):
        stale_arr = media_state.ArrTrackingSnapshot.from_maps(
            movie={
                4: {
                    "service": "radarr",
                    "monitored": False,
                    "titleSlug": "four",
                    "serviceHref": "https://radarr.example/movie/four",
                }
            },
            tv={},
            sources={"radarr": "stale", "sonarr": "fresh"},
        )
        state = self.resolve(4, arr=stale_arr)
        self.assertEqual(state["status"], "tracked")
        self.assertEqual(state["service"], "radarr")
        self.assertFalse(state["monitored"])

    def test_negative_state_is_missing_only_when_every_required_source_is_fresh(self):
        missing = self.resolve(99)
        stale_library = media_state.LibraryExclusionSnapshot.from_maps(
            {}, {}, status="stale", last_successful_refresh_at="2026-08-29T12:00:00+00:00"
        )
        unknown = self.resolve(99, library=stale_library)
        self.assertEqual(missing["status"], "missing")
        self.assertEqual(unknown["status"], "unknown")


class JellyseerrRequestStateTests(unittest.TestCase):
    def test_pending_request_and_approved_or_partial_media_are_normalized(self):
        self.assertEqual(
            media_state.jellyseerr_request_state(
                {"mediaInfo": {"requests": [{"id": 12, "status": 1}]}}
            ),
            {"status": "requested", "request_id": 12},
        )
        self.assertEqual(
            media_state.jellyseerr_request_state(
                {"mediaInfo": {"requests": [{"id": 13, "status": 2}]}}
            ),
            {"status": "processing", "request_id": 13},
        )
        self.assertEqual(
            media_state.jellyseerr_request_state({"mediaInfo": {"status": 4}}),
            {"status": "processing", "request_id": None},
        )

    def test_declined_or_available_media_does_not_create_an_active_request(self):
        self.assertIsNone(
            media_state.jellyseerr_request_state(
                {"mediaInfo": {"status": 5, "requests": [{"id": 14, "status": 3}]}}
            )
        )


if __name__ == "__main__":
    unittest.main()
