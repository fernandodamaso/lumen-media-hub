import unittest
from datetime import datetime, timedelta, timezone

from queue_hygiene import classify_queue, flatten_status_messages, group_queue_by_download_id


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


if __name__ == "__main__":
    unittest.main()
