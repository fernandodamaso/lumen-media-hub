"""Focused fake-only tests for the staged Trakt 48-hour retention rule."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from clients.trakt import TraktAuthError
from trakt_retention import (
    RetentionStateStore,
    SonarrRetentionClient,
    TraktRetentionRunner,
    _retention_scheduler_loop,
    build_retention_preview,
    fetch_complete_trakt_history,
    latest_watches,
)


NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
TVDB_ID = 100


def watch(season, number, watched_at, *, tvdb=TVDB_ID):
    return {
        "watched_at": watched_at,
        "show": {"ids": {"tvdb": tvdb}},
        "episode": {"season": season, "number": number, "ids": {"trakt": season * 100 + number}},
    }


def episode(number, *, episode_id=None, file_id=7, monitored=True, path="/data/media/tv/Show/S01E01.mkv"):
    return {
        "id": episode_id or number,
        "seriesId": 1,
        "seasonNumber": 1,
        "episodeNumber": number,
        "monitored": monitored,
        "hasFile": True,
        "episodeFileId": file_id,
        "path": path,
        "title": f"Episode {number}",
    }


class FakeTrakt:
    def __init__(self, entries, *, pages=None, error=None):
        self.entries = list(entries)
        self.pages = pages
        self.error = error
        self.calls = []

    def get_page(self, path):
        self.calls.append(path)
        if self.error:
            raise self.error
        page = int(path.split("page=")[1].split("&", 1)[0])
        if self.pages is None:
            payload = self.entries if page == 1 else []
            count = 1
        else:
            payload = self.pages.get(page, [])
            count = max(self.pages) if self.pages else 1
        return payload, {
            "X-Pagination-Page": str(page),
            "X-Pagination-Page-Count": str(count),
        }


class RewatchAfterSnapshot(FakeTrakt):
    """A rewatch appears after the first complete history snapshot."""

    def __init__(self, initial, newer):
        super().__init__(initial)
        self.newer = list(newer)

    def get_page(self, path):
        response = super().get_page(path)
        if len(self.calls) > 2:
            response = (self.newer, response[1])
        return response


class FakeSonarr:
    def __init__(self, episodes, *, series=None):
        self._episodes = [dict(row) for row in episodes]
        self._series = series or [{"id": 1, "tvdbId": TVDB_ID, "tmdbId": 200, "monitored": True}]
        self.set_calls = []
        self.delete_calls = []
        self.fail_unmonitor = False
        self.fail_delete = False
        self.file_details = {}

    def series(self):
        return [dict(row) for row in self._series]

    def episodes(self, series_id):
        return [dict(row) for row in self._episodes]

    def episode_file(self, file_id):
        return dict(self.file_details.get(file_id) or {})

    def set_episode(self, row):
        self.set_calls.append(dict(row))
        if self.fail_unmonitor:
            raise RuntimeError("unmonitor failed")
        for current in self._episodes:
            if current["id"] == row["id"]:
                current.update(row)

    def delete_episode_file(self, file_id):
        self.delete_calls.append(file_id)
        if self.fail_delete:
            raise RuntimeError("delete failed")
        self._episodes = [row for row in self._episodes if row.get("episodeFileId") != file_id]


class FakeJellyfin:
    def __init__(self, *, active=False, error=None):
        self.active = active
        self.error = error
        self.playback_calls = []
        self.refresh_calls = 0

    def playback_for_file(self, path):
        self.playback_calls.append(path)
        if self.error:
            raise self.error
        return self.active

    def refresh(self):
        self.refresh_calls += 1


def old_watch(season=1, number=1):
    return watch(season, number, (NOW - timedelta(hours=48)).isoformat())


class TraktRetentionTests(unittest.TestCase):
    def _preview(self, entries, episodes=None, *, trakt=None, jellyfin=None):
        return build_retention_preview(
            trakt=trakt or FakeTrakt(entries),
            sonarr=FakeSonarr(episodes or [episode(1)]),
            jellyfin=jellyfin or FakeJellyfin(),
            now=NOW,
        )

    def test_exact_48_hour_boundary_is_eligible(self):
        result = self._preview([old_watch()])
        self.assertEqual(len(result["eligible"]), 1)

    def test_episode_file_lookup_supplies_real_sonarr_path(self):
        row = episode(1)
        row.pop("path")
        sonarr = FakeSonarr([row])
        sonarr.file_details[7] = {"path": "/data/media/tv/Show/S01E01.mkv", "size": 123}
        result = build_retention_preview(
            trakt=FakeTrakt([old_watch()]), sonarr=sonarr, jellyfin=FakeJellyfin(), now=NOW
        )
        self.assertEqual(result["eligible"][0]["file"]["path"], "/data/media/tv/Show/S01E01.mkv")

    def test_sonarr_unmonitor_client_preserves_full_episode_payload(self):
        row = episode(1)
        client = SonarrRetentionClient(base="http://sonarr", api_key="key")
        with mock.patch("trakt_retention._arr_json", return_value=row) as request:
            client.set_episode(row)
        request.assert_called_once_with(
            "http://sonarr", "key", "/api/v3/episode/1", method="PUT", payload=row
        )

    def test_rewatch_resets_deadline(self):
        recent = (NOW - timedelta(hours=2)).isoformat()
        result = self._preview([old_watch(), watch(1, 1, recent)])
        self.assertEqual(result["eligible"], [])
        self.assertEqual(result["preserved"][0]["reason"], "watch_within_48h")

    def test_historical_pagination_is_consumed_completely(self):
        trakt = FakeTrakt([], pages={1: [old_watch()], 2: [watch(1, 2, (NOW - timedelta(hours=49)).isoformat())]})
        result = self._preview([], episodes=[episode(1), episode(2)], trakt=trakt)
        self.assertEqual(len(trakt.calls), 2)
        self.assertEqual(len(result["eligible"]), 1)
        self.assertEqual([row["number"] for row in result["eligible"][0]["episodes"]], [1, 2])

    def test_incomplete_pagination_blocks_preview(self):
        class Headerless:
            def get_page(self, _path):
                return [old_watch()], {}

        runner = TraktRetentionRunner(
            enabled=True,
            trakt=Headerless(),
            sonarr=FakeSonarr([episode(1)]),
            jellyfin=FakeJellyfin(),
        )
        result = runner.preview(now=NOW)
        self.assertEqual(result["reason"], "incomplete_history_pagination")

    def test_missing_watch_timestamp_blocks_preview(self):
        malformed = old_watch()
        malformed.pop("watched_at")
        runner = TraktRetentionRunner(
            enabled=True,
            trakt=FakeTrakt([malformed]),
            sonarr=FakeSonarr([episode(1)]),
            jellyfin=FakeJellyfin(),
        )
        result = runner.preview(now=NOW)
        self.assertEqual(result["reason"], "missing_timestamp")

    def test_missing_auth_blocks_without_sonarr_queries(self):
        sonarr = mock.Mock()
        runner = TraktRetentionRunner(
            enabled=True,
            trakt=FakeTrakt([], error=TraktAuthError()),
            sonarr=sonarr,
            jellyfin=FakeJellyfin(),
        )
        result = runner.preview(now=NOW)
        self.assertEqual(result["reason"], "auth_required")
        sonarr.series.assert_not_called()

    def test_default_off_runner_makes_no_upstream_calls(self):
        trakt = FakeTrakt([old_watch()])
        sonarr = mock.Mock()
        runner = TraktRetentionRunner(
            enabled=False, trakt=trakt, sonarr=sonarr, jellyfin=FakeJellyfin()
        )
        result = runner.run(now=NOW)
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(trakt.calls, [])
        sonarr.series.assert_not_called()

    def test_default_client_missing_oauth_configuration_blocks_safely(self):
        with mock.patch.object(__import__("config"), "TRAKT_CLIENT_ID", ""), mock.patch.object(
            __import__("config"), "TRAKT_CLIENT_SECRET", ""
        ):
            result = TraktRetentionRunner(enabled=True).preview(now=NOW)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "auth_required")

    def test_playback_failure_preserves(self):
        # The pure builder raises; the runner turns it into a safe blocked result.
        runner = TraktRetentionRunner(
            enabled=True,
            trakt=FakeTrakt([old_watch()]),
            sonarr=FakeSonarr([episode(1)]),
            jellyfin=FakeJellyfin(error=RuntimeError("sessions down")),
        )
        result = runner.preview(now=NOW)
        self.assertEqual(result["reason"], "playback_query_failed")

    def test_ambiguous_series_mapping_is_preserved(self):
        sonarr = FakeSonarr(
            [episode(1)],
            series=[{"id": 1, "tvdbId": TVDB_ID}, {"id": 2, "tvdbId": TVDB_ID}],
        )
        result = build_retention_preview(
            trakt=FakeTrakt([old_watch()]), sonarr=sonarr, jellyfin=FakeJellyfin(), now=NOW
        )
        self.assertEqual(result["eligible"], [])
        self.assertEqual(result["preserved"][0]["reason"], "ambiguous_series_mapping")

    def test_multi_episode_file_requires_every_episode(self):
        result = self._preview([old_watch(1, 1)], episodes=[episode(1), episode(2)])
        self.assertEqual(result["eligible"], [])
        self.assertEqual(result["preserved"][0]["reason"], "unwatched_episode")

    def test_newer_watch_and_unwatched_are_preserved(self):
        episodes = [
            episode(1),
            episode(2, file_id=8, path="/data/media/tv/Show/S01E02.mkv"),
            episode(3, file_id=9, path="/data/media/tv/Show/S01E03.mkv"),
        ]
        result = self._preview(
            [old_watch(1, 1), watch(1, 3, (NOW - timedelta(hours=1)).isoformat())], episodes=episodes
        )
        self.assertEqual(len(result["eligible"]), 1)
        self.assertEqual({row["reason"] for row in result["preserved"]}, {"watch_within_48h", "unwatched_episode"})

    def test_restart_between_unmonitor_and_delete_resumes_intent(self):
        with tempfile.TemporaryDirectory() as temporary:
            trakt = FakeTrakt([old_watch()])
            sonarr = FakeSonarr([episode(1)])
            jellyfin = FakeJellyfin()
            state = RetentionStateStore(Path(temporary) / "state.json")
            first = TraktRetentionRunner(
                enabled=True, trakt=trakt, sonarr=sonarr, jellyfin=jellyfin, state=state
            )
            original_delete = sonarr.delete_episode_file
            sonarr.delete_episode_file = mock.Mock(side_effect=RuntimeError("interrupted"))
            outcome = first.run(now=NOW)
            self.assertEqual(outcome["outcomes"][0]["status"], "unmonitored")
            self.assertEqual(sonarr.set_calls[0]["monitored"], False)
            self.assertEqual(sonarr.set_calls[0]["seriesId"], 1)
            self.assertEqual(sonarr.set_calls[0]["title"], "Episode 1")
            sonarr.delete_episode_file = original_delete
            second = TraktRetentionRunner(
                enabled=True, trakt=trakt, sonarr=sonarr, jellyfin=jellyfin, state=state
            )
            outcome = second.run(now=NOW)
            self.assertEqual(outcome["outcomes"][0]["status"], "deleted")
            self.assertEqual(sonarr.set_calls.__len__(), 1)

    def test_rewatch_is_revalidated_before_unmonitor_and_delete(self):
        with tempfile.TemporaryDirectory() as temporary:
            recent = watch(1, 1, (NOW - timedelta(hours=1)).isoformat())
            sonarr = FakeSonarr([episode(1)])
            runner = TraktRetentionRunner(
                enabled=True,
                trakt=RewatchAfterSnapshot([old_watch()], [recent]),
                sonarr=sonarr,
                jellyfin=FakeJellyfin(),
                state=RetentionStateStore(Path(temporary) / "state.json"),
            )
            result = runner.run(now=NOW)
            self.assertEqual(result["outcomes"][0]["reason"], "watch_within_48h")
            self.assertEqual(sonarr.set_calls, [])
            self.assertEqual(sonarr.delete_calls, [])

    def test_restart_with_new_rewatch_preserves_unmonitored_intent(self):
        with tempfile.TemporaryDirectory() as temporary:
            trakt = FakeTrakt([old_watch()])
            sonarr = FakeSonarr([episode(1)])
            jellyfin = FakeJellyfin()
            state = RetentionStateStore(Path(temporary) / "state.json")
            first = TraktRetentionRunner(
                enabled=True, trakt=trakt, sonarr=sonarr, jellyfin=jellyfin, state=state
            )
            sonarr.fail_delete = True
            result = first.run(now=NOW)
            self.assertEqual(result["outcomes"][0]["status"], "unmonitored")
            delete_attempts = len(sonarr.delete_calls)
            trakt.entries = [watch(1, 1, (NOW - timedelta(hours=1)).isoformat())]
            sonarr.fail_delete = False
            second = TraktRetentionRunner(
                enabled=True, trakt=trakt, sonarr=sonarr, jellyfin=jellyfin, state=state
            )
            result = second.run(now=NOW)
            self.assertEqual(result["outcomes"][0]["reason"], "watch_within_48h")
            self.assertEqual(len(sonarr.delete_calls), delete_attempts)

    def test_no_whole_series_deletion_helper_is_used(self):
        with tempfile.TemporaryDirectory() as temporary:
            sonarr = FakeSonarr([episode(1)])
            runner = TraktRetentionRunner(
                enabled=True,
                trakt=FakeTrakt([old_watch()]),
                sonarr=sonarr,
                jellyfin=FakeJellyfin(),
                state=RetentionStateStore(Path(temporary) / "state.json"),
            )
            result = runner.run(now=NOW)
            self.assertEqual(result["outcomes"][0]["status"], "deleted")
            self.assertEqual(sonarr.delete_calls, [7])

    def test_scheduler_seam_is_hourly_and_injectable(self):
        calls = []

        class Stop:
            def __init__(self):
                self.count = 0

        stop = Stop()

        def wait(_event, timeout):
            self.assertEqual(timeout, 3600)
            stop.count += 1
            return stop.count >= 1

        _retention_scheduler_loop(3600, stop, lambda: calls.append("cycle"), wait)
        self.assertEqual(calls, ["cycle"])

    def test_scheduler_cycle_exception_is_fail_closed_and_retries(self):
        calls = []
        waits = []

        def run_cycle():
            calls.append(len(calls))
            if len(calls) == 1:
                raise RuntimeError("controller unavailable")

        def wait(_event, timeout):
            waits.append(timeout)
            return len(waits) >= 2

        _retention_scheduler_loop(3600, object(), run_cycle, wait)
        self.assertEqual(calls, [0, 1])
        self.assertEqual(waits, [3600, 3600])


if __name__ == "__main__":
    unittest.main()
