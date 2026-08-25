import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import config
import library_delete
import queue_hygiene
import routes.arr as arr_routes
import routes.automation as automation_routes
import routes.library as library_routes

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
HASH = "a" * 40
REASON = "Not an upgrade for existing episode file(s). Existing file is equal or better."


def queue_row(**overrides):
    value = {
        "id": 11,
        "title": "Example S01E01",
        "downloadId": HASH,
        "status": "warning",
        "trackedDownloadStatus": "warning",
        "trackedDownloadState": "importPending",
        "episodeHasFile": True,
        "statusMessages": [{"messages": [REASON]}],
    }
    value.update(overrides)
    return value


def torrent(**overrides):
    value = {
        "hash": HASH,
        "progress": 1,
        "amount_left": 0,
        "completion_on": (NOW - timedelta(hours=8)).timestamp(),
        "state": "stalledUP",
    }
    value.update(overrides)
    return value


def snapshot(records):
    return {"totalRecords": len(records), "records": records}


class LibraryDeletionSafetyRegressions(unittest.TestCase):
    def test_history_overflow_is_a_safety_conflict_not_an_unmanaged_match(self):
        with self.assertRaises(library_delete.ConflictError):
            library_delete._history_download_ids(
                {"totalRecords": library_delete.HISTORY_PAGE_SIZE + 1, "records": []}
            )

    def test_preview_safety_conflict_does_not_offer_unmanaged_direct_delete(self):
        handler = object()
        with mock.patch.object(config, "JELLYFIN_API_KEY", "test-key"), mock.patch.object(
            library_routes,
            "resolve_library_target",
            side_effect=library_delete.ConflictError(),
        ), mock.patch.object(library_routes, "send_json") as send_json:
            library_routes.handle_library_delete_preview(handler, "jf-item")

        status = send_json.call_args.args[1]
        payload = send_json.call_args.args[2]
        self.assertEqual(status, 409)
        self.assertNotEqual(payload.get("code"), "unmanaged_title")

    def test_direct_delete_revalidates_that_movie_is_unmanaged(self):
        jellyfin_item = {
            "Type": "Movie",
            "Name": "Dune",
            "ProviderIds": {"Tmdb": "123"},
        }
        with mock.patch.object(
            library_delete, "_jellyfin_user_id_for_queries", return_value="user-1"
        ), mock.patch.object(
            library_delete, "jellyfin_get", return_value=jellyfin_item
        ), mock.patch.object(
            library_delete,
            "find_radarr_movies_by_tmdb",
            return_value=[{"id": 7, "tmdbId": 123}],
        ), mock.patch.object(
            library_delete, "delete_jellyfin_item"
        ) as delete_item, mock.patch.object(
            library_delete, "tombstone_jellyfin_item"
        ), mock.patch.object(
            library_delete, "invalidate_jellyfin_caches"
        ), mock.patch.object(
            library_delete, "jellyfin_post"
        ), mock.patch(
            "routes.discover.invalidate_discover_library_caches"
        ):
            with self.assertRaises(library_delete.ConflictError):
                library_delete.delete_jellyfin_item_directly("jf-item")

        delete_item.assert_not_called()


class ManagerLinkRegressions(unittest.TestCase):
    def test_duplicate_titles_use_year_keys_without_ambiguous_title_fallback(self):
        links = arr_routes._arr_slug_map(
            [
                {"title": "Dune", "titleSlug": "dune-1984", "year": 1984},
                {"title": "Dune", "titleSlug": "dune-2021", "year": 2021},
            ]
        )
        self.assertNotIn("dune", links)
        self.assertEqual(links["dune::1984"], "dune-1984")
        self.assertEqual(links["dune::2021"], "dune-2021")


class QueueHygieneSafetyRegressions(unittest.TestCase):
    def test_ordinary_active_download_is_outside_hygiene_scope(self):
        result = queue_hygiene.classify_queue(
            [
                queue_row(
                    status="downloading",
                    trackedDownloadStatus="ok",
                    trackedDownloadState="downloading",
                    episodeHasFile=False,
                    statusMessages=[],
                )
            ],
            [torrent(progress=0.5, amount_left=100)],
            NOW,
            6 * 3600,
        )
        self.assertEqual(result["eligibleGroups"], [])
        self.assertEqual(result["blockedItems"], [])

    def test_grace_period_candidate_does_not_raise_a_review_alarm(self):
        result = queue_hygiene.classify_queue(
            [queue_row()],
            [torrent(completion_on=(NOW - timedelta(hours=1)).timestamp())],
            NOW,
            6 * 3600,
        )
        self.assertEqual(result["eligibleGroups"], [])
        self.assertEqual(result["blockedItems"], [])

    def test_malformed_public_queue_id_is_normalized_to_null(self):
        result = queue_hygiene.classify_queue(
            [queue_row(id=True)],
            [torrent()],
            NOW,
            0,
        )
        self.assertEqual(result["blockedItems"][0]["queueId"], None)

    def test_normalized_state_reports_configured_mode_not_last_manual_mode(self):
        with mock.patch.object(config, "QUEUE_HYGIENE_MODE", "off"):
            state = queue_hygiene.normalized_state({"mode": "auto"})
        self.assertEqual(state["mode"], "off")

    def test_nonpositive_scheduler_interval_is_rejected_before_thread_start(self):
        with mock.patch.object(queue_hygiene, "_scheduler_thread", None), mock.patch.object(
            queue_hygiene.threading, "Thread"
        ) as thread:
            with self.assertRaises(ValueError):
                queue_hygiene.start_queue_hygiene_scheduler(0)
        thread.assert_not_called()

    def test_scheduler_continues_after_one_cycle_raises(self):
        calls = []
        waits = iter([False, True])

        def run_cycle():
            calls.append("run")
            if len(calls) == 1:
                raise RuntimeError("transient")

        def wait(_event, _timeout):
            return next(waits)

        with mock.patch.object(queue_hygiene, "_read_state", return_value={}), mock.patch.object(
            queue_hygiene, "_write_state"
        ) as write_state:
            queue_hygiene._queue_hygiene_scheduler_loop(1, object(), run_cycle, wait)

        self.assertEqual(len(calls), 2)
        write_state.assert_called()

    def test_remaining_queue_ids_open_the_circuit(self):
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.object(
            config, "QUEUE_HYGIENE_STATE_PATH", os.path.join(tmpdir, "state.json")
        ), mock.patch.object(config, "QUEUE_HYGIENE_GRACE_SECONDS", 0), mock.patch.object(
            queue_hygiene,
            "_fetch_sonarr_queue_snapshot",
            side_effect=[snapshot([queue_row()]), snapshot([queue_row()])],
        ), mock.patch.object(
            queue_hygiene,
            "_fetch_qbt_torrents",
            side_effect=[[torrent()], [torrent()]],
        ), mock.patch.object(queue_hygiene, "_ignore_sonarr_queue_items"):
            result = queue_hygiene.run_queue_hygiene_cycle(mode="auto", now=NOW)

            with open(config.QUEUE_HYGIENE_STATE_PATH, encoding="utf-8") as handle:
                state = json.load(handle)

        self.assertEqual(result["status"], "circuit_open")
        self.assertTrue(result["circuitOpen"])
        self.assertTrue(state["circuitOpen"])

    def test_post_mutation_verification_failure_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.object(
            config, "QUEUE_HYGIENE_STATE_PATH", os.path.join(tmpdir, "state.json")
        ), mock.patch.object(config, "QUEUE_HYGIENE_GRACE_SECONDS", 0), mock.patch.object(
            queue_hygiene,
            "_fetch_sonarr_queue_snapshot",
            side_effect=[snapshot([queue_row()]), ConnectionError("sonarr unavailable")],
        ), mock.patch.object(
            queue_hygiene, "_fetch_qbt_torrents", return_value=[torrent()]
        ), mock.patch.object(queue_hygiene, "_ignore_sonarr_queue_items"):
            result = queue_hygiene.run_queue_hygiene_cycle(mode="auto", now=NOW)

        self.assertEqual(result["status"], "circuit_open")
        self.assertTrue(result["circuitOpen"])

    def test_persisted_scheduler_error_marks_sonarr_degraded(self):
        hygiene = {
            "mode": "observe",
            "circuitOpen": False,
            "eligibleCount": 0,
            "blockedCount": 0,
            "eligibleItems": [],
            "blockedItems": [],
            "lastCycleAt": "2026-08-24T12:00:00Z",
            "lastCleanup": None,
            "verification": None,
            "error": "sonarr unavailable",
        }
        with mock.patch.multiple(
            config,
            SONARR_API_KEY="sonarr-key",
            RADARR_API_KEY="",
            PROWLARR_API_KEY="",
            BAZARR_ENABLED=False,
        ), mock.patch.object(automation_routes, "_arr_get", return_value=[]), mock.patch.object(
            automation_routes, "_sonarr_missing_preview", return_value=(0, [])
        ), mock.patch.object(
            automation_routes,
            "_fetch_queue_snapshot",
            return_value={"totalRecords": 0, "records": []},
        ), mock.patch.object(automation_routes, "_queue_hygiene_summary", return_value=hygiene):
            summary = automation_routes._build_automation_summary()

        self.assertTrue(summary["sonarr"]["degraded"])


if __name__ == "__main__":
    unittest.main()
