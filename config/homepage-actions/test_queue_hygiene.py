import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import config
import queue_hygiene
from queue_hygiene import (
    classify_queue,
    flatten_status_messages,
    group_queue_by_download_id,
    run_queue_hygiene_cycle,
)


REASON = "Not an upgrade for existing episode file(s). Existing file is equal or better."
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
HASH = "AbCdEf1234567890" + "0" * 24


def row(queue_id=11, download_id=HASH, **overrides):
    value = {
        "id": queue_id,
        "title": f"Show S01E{queue_id:02d}",
        "downloadId": download_id,
        "status": "warning",
        "trackedDownloadStatus": "warning",
        "trackedDownloadState": "importPending",
        "episodeHasFile": True,
        "statusMessages": [{"messages": [REASON]}],
    }
    value.update(overrides)
    return value


def torrent(download_hash=HASH, completed_at=NOW - timedelta(hours=8), **overrides):
    value = {
        "hash": download_hash,
        "progress": 1,
        "amount_left": 0,
        "completion_on": completed_at.timestamp(),
        "state": "stalledUP",
    }
    value.update(overrides)
    return value


class QueueHygieneTests(unittest.TestCase):
    def test_flatten_status_messages_handles_nested_shapes(self):
        values = flatten_status_messages(
            {"statusMessages": [{"messages": [" one ", {"message": "two"}]}, {"message": "three"}]}
        )
        self.assertEqual(values, ["one", "two", "three"])

    def test_group_queue_by_download_id_is_case_insensitive_and_sorted(self):
        grouped = group_queue_by_download_id(
            [row(2, "ZZ"), row(1, "ab"), row(3, "AB"), {"id": 4}]
        )
        self.assertEqual(list(grouped), ["ab", "zz"])
        self.assertEqual([item["id"] for item in grouped["ab"]], [1, 3])

    def test_import_pending_complete_download_is_eligible(self):
        result = classify_queue([row()], [torrent()], NOW, 6 * 3600)
        self.assertEqual(result["totalQueued"], 1)
        self.assertEqual(result["eligibleGroups"][0]["queueIds"], [11])
        self.assertEqual(result["eligibleGroups"][0]["ageHours"], 8.0)
        self.assertEqual(result["blockedItems"], [])
        self.assertNotIn("safeToDeleteData", result)

    def test_import_blocked_complete_download_is_eligible(self):
        result = classify_queue(
            [row(trackedDownloadState="importBlocked")], [torrent()], NOW, 6 * 3600
        )
        self.assertEqual(len(result["eligibleGroups"]), 1)

    def test_active_download_is_report_only(self):
        result = classify_queue([row()], [torrent(progress=0.5, amount_left=10)], NOW, 0)
        self.assertEqual(result["eligibleGroups"], [])
        self.assertEqual(result["blockedItems"][0]["blocker"], "active_download")

    def test_missing_qbt_match_is_report_only(self):
        result = classify_queue([row()], [], NOW, 0)
        self.assertEqual(result["eligibleGroups"], [])
        self.assertEqual(result["blockedItems"][0]["blocker"], "missing_qbt")

    def test_episode_without_file_is_report_only(self):
        result = classify_queue([row(episodeHasFile=False)], [torrent()], NOW, 0)
        self.assertEqual(result["eligibleGroups"], [])
        self.assertEqual(result["blockedItems"][0]["blocker"], "no_episode_file")

    def test_mixed_messages_block_entire_group(self):
        result = classify_queue(
            [row(), row(12, statusMessages=[{"messages": ["Other warning"]}])],
            [torrent()],
            NOW,
            0,
        )
        self.assertEqual(result["eligibleGroups"], [])
        self.assertEqual(len(result["blockedItems"]), 2)
        self.assertEqual({item["blocker"] for item in result["blockedItems"]}, {"mixed_group", "unknown_reason"})

    def test_unknown_reason_is_report_only(self):
        result = classify_queue([row(statusMessages=[{"messages": ["Unknown reason"]}])], [torrent()], NOW, 0)
        self.assertEqual(result["eligibleGroups"], [])
        self.assertEqual(result["blockedItems"][0]["blocker"], "unknown_reason")

    def test_grace_period_blocks_young_completion(self):
        result = classify_queue(
            [row()], [torrent(completed_at=NOW - timedelta(hours=2))], NOW, 6 * 3600
        )
        self.assertEqual(result["eligibleGroups"], [])
        self.assertEqual(result["blockedItems"][0]["blocker"], "grace_period")

    def test_malformed_ids_timestamps_and_hashes_never_become_eligible(self):
        result = classify_queue(
            [row(queue_id=True), row(12, download_id="")],
            [{"hash": None, "progress": 1, "amount_left": 0, "completion_on": "bad"}],
            NOW,
            0,
        )
        self.assertEqual(result["eligibleGroups"], [])
        self.assertEqual(len(result["blockedItems"]), 2)

    def test_shared_download_id_is_atomic(self):
        result = classify_queue(
            [row(), row(12, episodeHasFile=False)], [torrent()], NOW, 0
        )
        self.assertEqual(result["eligibleGroups"], [])
        self.assertEqual(len(result["blockedItems"]), 2)

    def test_hash_matching_is_case_insensitive(self):
        result = classify_queue(
            [row(download_id=HASH.upper())], [torrent(download_hash=HASH.lower())], NOW, 0
        )
        self.assertEqual(len(result["eligibleGroups"]), 1)
        self.assertEqual(result["eligibleGroups"][0]["downloadId"], HASH.upper())

    def test_invalid_clock_and_grace_inputs_never_allow_cleanup(self):
        for now, grace in ((None, 0), (NOW, False), (NOW, "bad")):
            result = classify_queue([row()], [torrent()], now, grace)
            self.assertEqual(result["eligibleGroups"], [])
            self.assertEqual(result["blockedItems"][0]["blocker"], "grace_period")

    def test_duplicate_qbt_hashes_are_ambiguous_and_report_only(self):
        result = classify_queue([row()], [torrent(), torrent(progress=0.5)], NOW, 0)
        self.assertEqual(result["eligibleGroups"], [])
        self.assertEqual(result["blockedItems"][0]["blocker"], "ambiguous_qbt")

    def test_result_order_is_deterministic(self):
        hash_a = "a" * 40
        hash_z = "f" * 40
        result = classify_queue(
            [row(12, hash_z), row(11, hash_a)],
            [torrent(hash_z), torrent(hash_a)],
            NOW,
            0,
        )
        self.assertEqual(
            [group["downloadId"] for group in result["eligibleGroups"]], [hash_a, hash_z]
        )
        self.assertEqual(result["eligibleGroups"][0]["titles"], ["Show S01E11"])


class QueueHygieneCycleTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = os.path.join(self.tmpdir.name, "queue-hygiene-state.json")
        self._old = {
            "QUEUE_HYGIENE_MODE": config.QUEUE_HYGIENE_MODE,
            "QUEUE_HYGIENE_GRACE_SECONDS": config.QUEUE_HYGIENE_GRACE_SECONDS,
            "QUEUE_HYGIENE_STATE_PATH": config.QUEUE_HYGIENE_STATE_PATH,
        }
        config.QUEUE_HYGIENE_MODE = "observe"
        config.QUEUE_HYGIENE_GRACE_SECONDS = 6 * 3600
        config.QUEUE_HYGIENE_STATE_PATH = self.state_path
        config._arr_cache.clear()
        self.addCleanup(self._restore_config)
        self.addCleanup(self.tmpdir.cleanup)

    def _restore_config(self):
        for name, value in self._old.items():
            setattr(config, name, value)
        config._arr_cache.clear()

    def _run(self, mode, queue_snapshots, qbt_snapshots, now=NOW):
        with patch.object(
            queue_hygiene, "_fetch_sonarr_queue_snapshot", side_effect=queue_snapshots
        ) as sonarr_fetch, patch.object(
            queue_hygiene, "_fetch_qbt_torrents", side_effect=qbt_snapshots
        ) as qbt_fetch, patch.object(
            queue_hygiene, "_ignore_sonarr_queue_items"
        ) as ignore:
            result = run_queue_hygiene_cycle(mode=mode, now=now)
        return result, sonarr_fetch, qbt_fetch, ignore

    @staticmethod
    def _snapshot(records):
        return {"totalRecords": len(records), "records": records}

    def test_qbt_fetch_builds_cookie_processor_for_real_client(self):
        with patch("urllib.request.build_opener", return_value="opener") as build_opener, patch(
            "clients.qbittorrent.qbt_login"
        ) as login, patch("clients.qbittorrent.qbt_get_json", return_value=[]):
            result = queue_hygiene._fetch_qbt_torrents()
        self.assertEqual(result, [])
        login.assert_called_once_with("opener")
        self.assertEqual(len(build_opener.call_args.args), 1)
        self.assertEqual(type(build_opener.call_args.args[0]).__name__, "HTTPCookieProcessor")

    def test_off_does_not_make_upstream_requests(self):
        with patch.object(queue_hygiene, "_fetch_sonarr_queue_snapshot") as sonarr_fetch, patch.object(
            queue_hygiene, "_fetch_qbt_torrents"
        ) as qbt_fetch:
            result = run_queue_hygiene_cycle(mode="off", now=NOW)
        self.assertEqual(result["status"], "off")
        sonarr_fetch.assert_not_called()
        qbt_fetch.assert_not_called()

    def test_observe_classifies_without_delete(self):
        result, sonarr_fetch, qbt_fetch, ignore = self._run(
            "observe", [self._snapshot([row()])], [[torrent()]]
        )
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["counts"]["eligible"], 1)
        self.assertEqual(result["queueIds"], [11])
        sonarr_fetch.assert_called_once()
        qbt_fetch.assert_called_once()
        ignore.assert_not_called()

    def test_auto_deletes_all_eligible_ids_once(self):
        result, _sonarr_fetch, _qbt_fetch, ignore = self._run(
            "auto",
            [self._snapshot([row(), row(12)]) , self._snapshot([])],
            [[torrent()], [torrent()]],
        )
        self.assertEqual(result["status"], "cleaned")
        ignore.assert_called_once_with([11, 12])
        self.assertEqual(result["verification"]["queueIdsGone"], True)

    def test_shared_download_id_is_atomic_for_cycle_mutation(self):
        result, _sonarr_fetch, _qbt_fetch, ignore = self._run(
            "auto",
            [self._snapshot([row(), row(12, episodeHasFile=False)])],
            [[torrent()]],
        )
        self.assertEqual(result["counts"]["eligible"], 0)
        ignore.assert_not_called()

    def test_post_mutation_sonarr_ids_are_gone_and_qbt_hashes_preserved(self):
        result, _sonarr_fetch, qbt_fetch, ignore = self._run(
            "auto",
            [self._snapshot([row()]), self._snapshot([])],
            [[torrent()], [torrent()]],
        )
        self.assertEqual(result["verification"]["queueIdsGone"], True)
        self.assertEqual(result["verification"]["hashesPreserved"], True)
        self.assertEqual(result["verification"]["missingHashes"], [])
        self.assertEqual(qbt_fetch.call_count, 2)
        ignore.assert_called_once_with([11])

    def test_hash_disappearance_opens_persisted_circuit_and_blocks_later_auto(self):
        result, _sonarr_fetch, _qbt_fetch, ignore = self._run(
            "auto",
            [self._snapshot([row()]), self._snapshot([])],
            [[torrent()], []],
        )
        self.assertEqual(result["status"], "circuit_open")
        self.assertTrue(result["circuitOpen"])
        ignore.assert_called_once_with([11])
        with open(self.state_path, encoding="utf-8") as handle:
            state = json.load(handle)
        self.assertTrue(state["circuitOpen"])

        result, _sonarr_fetch, _qbt_fetch, ignore = self._run(
            "auto", [self._snapshot([row()])], [[torrent()]]
        )
        self.assertEqual(result["status"], "circuit_open")
        ignore.assert_not_called()

    def test_network_failure_is_report_only_and_does_not_open_circuit(self):
        with patch.object(
            queue_hygiene,
            "_fetch_sonarr_queue_snapshot",
            side_effect=ConnectionError("sonarr unavailable"),
        ), patch.object(queue_hygiene, "_fetch_qbt_torrents") as qbt_fetch, patch.object(
            queue_hygiene, "_ignore_sonarr_queue_items"
        ) as ignore:
            result = run_queue_hygiene_cycle(mode="auto", now=NOW)
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["circuitOpen"])
        self.assertIn("sonarr unavailable", result["error"])
        qbt_fetch.assert_not_called()
        ignore.assert_not_called()

    def test_success_invalidates_automation_cache(self):
        config._arr_cache.update({"automation": {"stale": True}, "automation_ts": 1})
        result, _sonarr_fetch, _qbt_fetch, _ignore = self._run(
            "auto", [self._snapshot([row()]), self._snapshot([])], [[torrent()], [torrent()]]
        )
        self.assertEqual(result["status"], "cleaned")
        self.assertNotIn("automation", config._arr_cache)
        self.assertNotIn("automation_ts", config._arr_cache)

    def test_successful_observe_clears_stale_error_state(self):
        queue_hygiene._write_state({"error": "previous upstream failure", "circuitOpen": False})
        self._run("observe", [self._snapshot([])], [[]])
        with open(self.state_path, encoding="utf-8") as handle:
            state = json.load(handle)
        self.assertNotIn("error", state)

    def test_state_write_is_atomic_bounded_and_public(self):
        with patch.object(queue_hygiene.os, "replace", wraps=os.replace) as replace:
            self._run("observe", [self._snapshot([row()])], [[torrent()]])
        replace.assert_called_once()
        self.assertTrue(os.path.exists(self.state_path))
        with open(self.state_path, encoding="utf-8") as handle:
            raw = handle.read()
            state = json.loads(raw)
        self.assertLessEqual(len(state["queueIds"]), queue_hygiene.MAX_STATE_ITEMS)
        self.assertLessEqual(len(state["hashes"]), queue_hygiene.MAX_STATE_ITEMS)
        self.assertNotIn("super-secret", raw)
        self.assertNotIn("magnet:", raw.lower())
        self.assertNotIn("api_key", raw.lower())
        self.assertNotIn("password", raw.lower())
        self.assertNotIn(".tmp-", " ".join(os.listdir(self.tmpdir.name)))

    def test_overlap_returns_skipped_without_upstream_work(self):
        self.assertTrue(queue_hygiene._cycle_lock.acquire(blocking=False))
        try:
            with patch.object(queue_hygiene, "_fetch_sonarr_queue_snapshot") as sonarr_fetch, patch.object(
                queue_hygiene, "_fetch_qbt_torrents"
            ) as qbt_fetch:
                result = run_queue_hygiene_cycle(mode="auto", now=NOW)
        finally:
            queue_hygiene._cycle_lock.release()
        self.assertEqual(result["status"], "skipped")
        self.assertTrue(result["skipped"])
        sonarr_fetch.assert_not_called()
        qbt_fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
