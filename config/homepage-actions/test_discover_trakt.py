import unittest
from types import SimpleNamespace
from unittest import mock

from routes import discover as routes
from routes.discover import _map_trakt_result
from clients.trakt import TraktAuthError
from trakt_history import WatchedSnapshot


class TraktDiscoverMappingTests(unittest.TestCase):
    def test_movie_includes_slug(self):
        raw = {
            "title": "Dune: Part Two",
            "year": 2024,
            "ids": {"tmdb": 693134, "slug": "dune-part-two-2024"},
            "overview": "Epic continuation.",
            "rating": 8.3,
        }
        result = _map_trakt_result(raw, "movies")
        self.assertEqual(result["type"], "movie")
        self.assertEqual(result["title"], "Dune: Part Two")
        self.assertEqual(result["trakt_slug"], "dune-part-two-2024")
        self.assertEqual(result["tmdb_id"], 693134)

    def test_show_includes_slug(self):
        raw = {
            "show": {
                "title": "Severance",
                "year": 2022,
                "ids": {"tmdb": 95396, "slug": "severance"},
                "overview": "Work-life balance taken literally.",
            },
            "rating": 8.7,
        }
        result = _map_trakt_result(raw, "shows")
        self.assertEqual(result["type"], "tv")
        self.assertEqual(result["title"], "Severance")
        self.assertEqual(result["trakt_slug"], "severance")
        self.assertEqual(result["tmdb_id"], 95396)

    def test_missing_slug_is_none(self):
        raw = {
            "title": "Untitled",
            "year": 2026,
            "ids": {"tmdb": 1},
            "overview": "",
        }
        result = _map_trakt_result(raw, "movies")
        self.assertIsNone(result["trakt_slug"])


class TraktWatchedExclusionRouteTests(unittest.TestCase):
    def test_filters_typed_watched_identities_and_reports_freshness(self):
        captured = {}
        raw = [
            {"title": "Watched movie", "ids": {"tmdb": 42}},
            {"title": "Keep movie", "ids": {"tmdb": 7}},
        ]
        watched = WatchedSnapshot(frozenset({"movie:42", "tv:42"}), "2026-08-11T12:00:00+00:00", "fresh")
        with mock.patch.object(routes.settings, "TRAKT_CLIENT_ID", "id"), \
                mock.patch.object(routes, "_trakt_get", return_value=raw) as trakt_get, \
                mock.patch.object(routes, "_trakt_watched_snapshot", return_value=watched), \
                mock.patch.object(routes, "_library_exclusion_snapshot", return_value=routes.LibraryExclusionSnapshot.from_maps({}, {}, status="fresh", last_successful_refresh_at=None)), \
                mock.patch.object(routes, "send_json", side_effect=lambda _h, _s, payload: captured.update(payload)):
            routes.handle_discover_trakt(SimpleNamespace(), {"type": ["movies"]})
        self.assertEqual([item["tmdb_id"] for item in captured["items"]], [7])
        self.assertEqual(captured["watched_exclusion"], watched.public())
        self.assertIn("ignore_watched=true", trakt_get.call_args.args[0])

    def test_keeps_cards_and_warns_when_watched_snapshot_is_unavailable(self):
        captured = {}
        watched = WatchedSnapshot(frozenset(), None, "unavailable")
        raw = [{"title": "Keep movie", "ids": {"tmdb": 7}}]
        with mock.patch.object(routes.settings, "TRAKT_CLIENT_ID", "id"), \
                mock.patch.object(routes, "_trakt_get", return_value=raw), \
                mock.patch.object(routes, "_trakt_watched_snapshot", return_value=watched), \
                mock.patch.object(routes, "_library_exclusion_snapshot", return_value=routes.LibraryExclusionSnapshot.from_maps({}, {}, status="fresh", last_successful_refresh_at=None)), \
                mock.patch.object(routes, "send_json", side_effect=lambda _h, _s, payload: captured.update(payload)):
            routes.handle_discover_trakt(SimpleNamespace(), {"type": ["movies"]})
        self.assertEqual([item["tmdb_id"] for item in captured["items"]], [7])
        self.assertEqual(captured["watched_exclusion"]["status"], "unavailable")

    def test_route_sanitizes_unexpected_trakt_errors(self):
        responses = []
        leaked = r"C:\private\trakt-token.json: permission denied"
        with mock.patch.object(routes.settings, "TRAKT_CLIENT_ID", "id"), \
                mock.patch.object(routes, "_trakt_get", side_effect=PermissionError(leaked)), \
                mock.patch.object(routes, "send_json", side_effect=lambda _h, status, payload: responses.append((status, payload))):
            routes.handle_discover_trakt(SimpleNamespace(), {"type": ["movies"]})
        self.assertEqual(responses, [(502, {"ok": False, "error": "Trakt temporarily unavailable"})])

    def test_route_maps_persistent_trakt_auth_rejection_to_reconnect(self):
        responses = []
        leaked = "refresh-token-secret"
        with mock.patch.object(routes.settings, "TRAKT_CLIENT_ID", "id"), \
                mock.patch.object(
                    routes,
                    "_trakt_get",
                    side_effect=TraktAuthError("reconnect_required", leaked),
                ), \
                mock.patch.object(
                    routes,
                    "send_json",
                    side_effect=lambda _handler, status, payload: responses.append(
                        (status, payload)
                    ),
                ):
            routes.handle_discover_trakt(SimpleNamespace(), {"type": ["movies"]})

        self.assertEqual(
            responses,
            [
                (
                    503,
                    {
                        "ok": False,
                        "error": "Trakt reconnect required",
                        "code": "reconnect_required",
                    },
                )
            ],
        )
        self.assertNotIn(leaked, str(responses))

    def test_route_forces_watched_refresh_when_requested(self):
        with mock.patch.object(routes.settings, "TRAKT_CLIENT_ID", "id"), \
                mock.patch.object(routes, "_trakt_get", return_value=[]), \
                mock.patch.object(
                    routes,
                    "_trakt_watched_snapshot",
                ) as watched_snapshot, \
                mock.patch.object(
                    routes,
                    "_library_exclusion_snapshot",
                    return_value=routes.LibraryExclusionSnapshot.from_maps({}, {}, status="fresh", last_successful_refresh_at=None),
                ), \
                mock.patch.object(routes, "send_json"):
            routes.handle_discover_trakt(
                SimpleNamespace(),
                {"type": ["movies"], "refresh_watched": ["true"]},
            )
        watched_snapshot.assert_called_once_with(force=True)


if __name__ == "__main__":
    unittest.main()
