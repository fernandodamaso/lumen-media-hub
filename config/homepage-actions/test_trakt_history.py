import json
import os
import tempfile
import unittest
from unittest import mock

from trakt_history import (
    TraktWatchedService,
    WatchedSnapshotStore,
    parse_watched_identities,
)


class WatchedParserTests(unittest.TestCase):
    def test_parses_watched_movies_and_shows_as_typed_deduplicated_identities(self):
        movies = [
            {"movie": {"title": "Movie", "ids": {"tmdb": 42}}},
            {"movie": {"title": "Duplicate", "ids": {"tmdb": "42"}}},
            {"movie": {"title": "Missing", "ids": {"imdb": "tt1"}}},
        ]
        shows = [
            {"show": {"title": "Show", "ids": {"tmdb": 42}}, "episodes": [{"number": 1}]},
            {"show": {"title": "No id", "ids": {"tvdb": 9}}, "episodes": [{"number": 1}]},
        ]

        self.assertEqual(parse_watched_identities(movies, "movies"), {"movie:42"})
        self.assertEqual(parse_watched_identities(shows, "shows"), {"tv:42"})

    def test_does_not_match_movie_and_tv_numeric_id_collisions(self):
        movies = [{"movie": {"title": "Movie", "ids": {"tmdb": 7}}}]
        shows = [{"show": {"title": "Show", "ids": {"tmdb": 7}}, "episodes": [{"number": 1}]}]

        self.assertEqual(parse_watched_identities(movies, "movies") | parse_watched_identities(shows, "shows"), {"movie:7", "tv:7"})

    def test_marks_current_watched_show_shape_without_season_progress(self):
        shows = [{"show": {"title": "Watched show", "ids": {"tmdb": 8}}}]

        self.assertEqual(parse_watched_identities(shows, "shows"), {"tv:8"})

    def test_rejects_present_malformed_tmdb_identity_but_skips_missing_identity(self):
        self.assertEqual(
            parse_watched_identities([{"movie": {"ids": {"imdb": "tt1"}}}], "movies"),
            set(),
        )
        for value in (42.9, True, "", "bad", 0, -1):
            with self.assertRaises(ValueError):
                parse_watched_identities([{"movie": {"ids": {"tmdb": value}}}], "movies")


class WatchedPaginationTests(unittest.TestCase):
    def test_consumes_all_pages_from_authoritative_headers(self):
        calls = []
        pages = {
            "/sync/watched/movies?page=1&limit=100": ([{"movie": {"ids": {"tmdb": 1}}}], {"X-Pagination-Page-Count": "2"}),
            "/sync/watched/movies?page=2&limit=100": (
                [{"movie": {"ids": {"tmdb": 2}}}],
                {"X-Pagination-Page": "2", "X-Pagination-Page-Count": "2"},
            ),
            "/sync/watched/shows?page=1&limit=100": ([], {"X-Pagination-Page-Count": "1"}),
        }

        def get_page(path):
            calls.append(path)
            return pages[path]

        service = TraktWatchedService(get_page=get_page)
        self.assertEqual(service.fetch_identities(), {"movie:1", "movie:2"})
        self.assertEqual(calls, list(pages))

    def test_headerless_first_response_is_treated_as_complete(self):
        calls = []

        def get_page(path):
            calls.append(path)
            if "shows" in path:
                return ([], {})
            return ([{"movie": {"ids": {"tmdb": 9}}}], {})

        service = TraktWatchedService(get_page=get_page)
        self.assertEqual(service.fetch_identities(), {"movie:9"})
        self.assertEqual(calls, ["/sync/watched/movies?page=1&limit=100", "/sync/watched/shows?page=1&limit=100"])

    def test_missing_continuation_header_fails_after_page_one_declares_more(self):
        def get_page(path):
            if "movies?page=1" in path:
                return ([{"movie": {"ids": {"tmdb": 1}}}], {"X-Pagination-Page-Count": "3"})
            return ([{"movie": {"ids": {"tmdb": 2}}}], {"X-Pagination-Page-Count": "3"})

        with self.assertRaises(ValueError):
            TraktWatchedService(get_page=get_page).fetch_identities()

    def test_inconsistent_continuation_header_fails(self):
        def get_page(path):
            if "movies?page=1" in path:
                return ([{"movie": {"ids": {"tmdb": 1}}}], {"X-Pagination-Page-Count": "3"})
            return (
                [{"movie": {"ids": {"tmdb": 2}}}],
                {"X-Pagination-Page": "2", "X-Pagination-Page-Count": "2"},
            )

        with self.assertRaises(ValueError):
            TraktWatchedService(get_page=get_page).fetch_identities()


class WatchedCacheTests(unittest.TestCase):
    def test_refreshes_after_fifteen_minute_in_memory_window(self):
        now = [1000]
        calls = []

        def get_page(path):
            calls.append(path)
            return ([], {})

        service = TraktWatchedService(get_page=get_page, clock=lambda: now[0])
        service.snapshot()
        self.assertEqual(len(calls), 2)
        now[0] = 1899
        service.snapshot()
        self.assertEqual(len(calls), 2)
        now[0] = 1900
        service.snapshot()
        self.assertEqual(len(calls), 4)

    def test_repeated_failure_after_unavailable_stays_unavailable(self):
        now = [1000]
        service = TraktWatchedService(
            get_page=mock.Mock(side_effect=RuntimeError("down")),
            clock=lambda: now[0],
        )
        self.assertEqual(service.snapshot().status, "unavailable")
        now[0] = 1900
        self.assertEqual(service.snapshot().status, "unavailable")

    def test_unexpected_snapshot_store_read_error_is_unavailable(self):
        store = mock.Mock()
        store.load.side_effect = PermissionError(r"C:\private\trakt-watched.json: access denied")
        service = TraktWatchedService(
            get_page=mock.Mock(side_effect=RuntimeError("network down")),
            store=store,
        )
        snapshot = service.snapshot()
        self.assertEqual(snapshot.status, "unavailable")
        self.assertEqual(snapshot.identities, set())

    def test_fresh_empty_snapshot_remains_last_good_after_failure(self):
        now = [1000]
        get_page = mock.Mock(return_value=([], {}))
        service = TraktWatchedService(get_page=get_page, clock=lambda: now[0])
        self.assertEqual(service.snapshot().status, "fresh")
        get_page.side_effect = RuntimeError("down")
        now[0] = 1900
        self.assertEqual(service.snapshot().status, "stale")

    def test_persists_only_schema_timestamp_and_identities(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trakt-watched.json")
            store = WatchedSnapshotStore(path)
            store.replace({"movie:1", "tv:2"}, refreshed_at="2026-08-11T12:00:00+00:00")
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertEqual(set(data), {"schema_version", "refreshed_at", "identities"})
            self.assertEqual(data["identities"], ["movie:1", "tv:2"])

    def test_uses_stale_snapshot_after_refresh_failure_and_unavailable_without_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trakt-watched.json")
            store = WatchedSnapshotStore(path)
            store.replace({"movie:1"}, refreshed_at="2026-08-11T12:00:00+00:00")
            service = TraktWatchedService(
                get_page=mock.Mock(side_effect=RuntimeError("down")),
                store=store,
                clock=lambda: 1_000,
            )
            stale = service.snapshot()
            self.assertEqual(stale.status, "stale")
            self.assertEqual(stale.identities, {"movie:1"})

            empty = TraktWatchedService(get_page=mock.Mock(side_effect=RuntimeError("down"))).snapshot()
            self.assertEqual(empty.status, "unavailable")
            self.assertEqual(empty.identities, set())

    def test_rejects_malformed_page_without_persisting_fresh_empty_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trakt-watched.json")
            store = WatchedSnapshotStore(path)
            store.replace({"movie:1"}, refreshed_at="2026-08-11T12:00:00+00:00")
            stale = TraktWatchedService(
                get_page=mock.Mock(return_value=({"unexpected": "object"}, {})),
                store=store,
            ).snapshot()
            self.assertEqual(stale.status, "stale")
            self.assertEqual(stale.identities, {"movie:1"})
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["identities"], ["movie:1"])

            empty = TraktWatchedService(
                get_page=mock.Mock(return_value=({"unexpected": "object"}, {})),
            ).snapshot()
            self.assertEqual(empty.status, "unavailable")
            self.assertEqual(empty.identities, set())

    def test_rejects_malformed_list_member_with_last_good_and_without_cache(self):
        malformed = [{"unexpected": "object"}]
        with tempfile.TemporaryDirectory() as tmp:
            store = WatchedSnapshotStore(os.path.join(tmp, "trakt-watched.json"))
            store.replace({"movie:1"}, refreshed_at="2026-08-11T12:00:00+00:00")
            stale = TraktWatchedService(
                get_page=mock.Mock(return_value=(malformed, {})),
                store=store,
            ).snapshot()
            self.assertEqual(stale.status, "stale")
            self.assertEqual(stale.identities, {"movie:1"})

            unavailable = TraktWatchedService(
                get_page=mock.Mock(return_value=(malformed, {})),
            ).snapshot()
            self.assertEqual(unavailable.status, "unavailable")

    def test_rejects_malformed_persisted_identity_set_as_unusable(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = WatchedSnapshotStore(os.path.join(tmp, "trakt-watched.json"))
            store.replace({"movie:1"}, refreshed_at="2026-08-11T12:00:00+00:00")
            with open(store.path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "schema_version": 1,
                        "refreshed_at": "2026-08-11T12:00:00+00:00",
                        "identities": ["movie:1", "tv:not-an-id"],
                    },
                    handle,
                )
            self.assertIsNone(store.load())

    def test_rejects_malformed_persisted_timestamp_as_unusable(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = WatchedSnapshotStore(os.path.join(tmp, "trakt-watched.json"))
            with open(store.path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "schema_version": 1,
                        "refreshed_at": "not-a-timestamp",
                        "identities": ["movie:1"],
                    },
                    handle,
                )
            self.assertIsNone(store.load())

    def test_malformed_timestamp_cache_falls_back_to_unavailable_without_usable_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = WatchedSnapshotStore(os.path.join(tmp, "trakt-watched.json"))
            with open(store.path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "schema_version": 1,
                        "refreshed_at": "not-a-timestamp",
                        "identities": ["movie:1"],
                    },
                    handle,
                )
            service = TraktWatchedService(
                get_page=mock.Mock(side_effect=RuntimeError("down")),
                store=store,
            )
            snapshot = service.snapshot()
            self.assertEqual(snapshot.status, "unavailable")
            self.assertEqual(snapshot.identities, set())


if __name__ == "__main__":
    unittest.main()
