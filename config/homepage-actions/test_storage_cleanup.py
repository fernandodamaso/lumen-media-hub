import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

import storage_cleanup as subject


NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
GB = 1024 ** 3


def policy(**overrides):
    raw = {
        "schemaVersion": 1,
        "targetFreeBytes": 200 * GB,
        "rules": {
            "watchedMovies": {"enabled": True, "retentionDays": 30},
            "watchedEpisodes": {"enabled": True, "retentionDays": 14, "keepLatestPerSeries": 3},
            "largeWatchedFiles": {"enabled": True, "minimumBytes": 20 * GB, "idleDays": 90},
        },
        "protections": {"recentAdditionGraceDays": 7, "pinnedCandidateIds": []},
    }
    raw.update(overrides)
    return subject.validate_cleanup_request(raw)


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def movie(item_id, path, *, size=10*GB, played=True, favorite=False, last=40, added=100, position=0, sources=None):
    return {
        "Id": item_id,
        "Type": "Movie",
        "Name": f"Movie {item_id}",
        "ProductionYear": 2024,
        "DateCreated": iso(added),
        "Path": path,
        "LocationType": "FileSystem",
        "IsPlaceHolder": False,
        "MediaSources": sources if sources is not None else [{
            "Id": f"src-{item_id}",
            "Path": path,
            "Protocol": "File",
            "Size": size,
            "Container": "mkv",
            "IsRemote": False,
        }],
        "UserData": {
            "Played": played,
            "IsFavorite": favorite,
            "PlaybackPositionTicks": position,
            "LastPlayedDate": iso(last) if played else None,
        },
    }


def episode(item_id, path, *, series="s1", season=1, number=1, end=None, size=3*GB, played=True,
            favorite=False, last=30, added=100, position=0):
    return {
        "Id": item_id,
        "Type": "Episode",
        "Name": f"Episode {number}",
        "SeriesId": series,
        "SeriesName": "Series One",
        "ParentIndexNumber": season,
        "IndexNumber": number,
        "EndIndexNumber": end,
        "DateCreated": iso(added),
        "Path": path,
        "LocationType": "FileSystem",
        "IsPlaceHolder": False,
        "MediaSources": [{
            "Id": f"src-{item_id}",
            "Path": path,
            "Protocol": "File",
            "Size": size,
            "Container": "mkv",
            "IsRemote": False,
        }],
        "UserData": {
            "Played": played,
            "IsFavorite": favorite,
            "PlaybackPositionTicks": position,
            "LastPlayedDate": iso(last) if played else None,
        },
    }


class ValidationTests(unittest.TestCase):
    def test_defaults_are_accepted(self):
        p = policy()
        self.assertEqual(p["rules"]["watchedMovies"]["retentionDays"], 30)
        self.assertEqual(p["protections"]["recentAdditionGraceDays"], 7)

    def test_rejects_unknown_fields_and_malformed_numbers(self):
        raw = {
            "schemaVersion": 1,
            "targetFreeBytes": 1,
            "rules": {
                "watchedMovies": {"enabled": True, "retentionDays": 30},
                "watchedEpisodes": {"enabled": True, "retentionDays": 14, "keepLatestPerSeries": 3},
                "largeWatchedFiles": {"enabled": True, "minimumBytes": 1, "idleDays": 90},
            },
            "protections": {"recentAdditionGraceDays": 7, "pinnedCandidateIds": []},
            "extra": True,
        }
        with self.assertRaises(subject.CleanupValidationError):
            subject.validate_cleanup_request(raw)
        raw.pop("extra")
        raw["rules"]["watchedMovies"]["retentionDays"] = float("nan")
        with self.assertRaises(subject.CleanupValidationError):
            subject.validate_cleanup_request(raw)

    def test_pins_are_deduped_and_invalid_ids_fail_closed(self):
        p = policy()
        raw = {**p, "protections": {**p["protections"], "pinnedCandidateIds": ["sg_" + "a" * 24] * 2}}
        self.assertEqual(len(subject.validate_cleanup_request(raw)["protections"]["pinnedCandidateIds"]), 1)
        raw["protections"]["pinnedCandidateIds"] = ["../../private"]
        with self.assertRaises(subject.CleanupValidationError):
            subject.validate_cleanup_request(raw)


class InventoryTests(unittest.TestCase):
    def test_dedupes_same_physical_file_and_never_exposes_path(self):
        raw = [movie("m1", "/data/movies/a.mkv"), movie("m1", "/data/movies/a.mkv")]
        inventory = subject.normalize_jellyfin_inventory(raw)
        self.assertEqual(len(inventory["files"]), 1)
        self.assertNotIn("/data/", repr(inventory["unresolved"]))
        self.assertTrue(inventory["files"][0]["id"].startswith("sg_"))

    def test_ambiguous_multiple_local_versions_are_unresolved(self):
        raw = [movie("m1", "/data/a.mkv", sources=[
            {"Path": "/data/a.mkv", "Protocol": "File", "Size": 10 * GB, "Container": "mkv", "IsRemote": False},
            {"Path": "/data/b.mkv", "Protocol": "File", "Size": 12 * GB, "Container": "mkv", "IsRemote": False},
        ])]
        inventory = subject.normalize_jellyfin_inventory(raw)
        self.assertEqual(inventory["files"], [])
        self.assertEqual(inventory["unresolved"][0]["reason"], "ambiguous_versions")
        self.assertNotIn("/data/", repr(inventory["unresolved"]))

    def test_mixed_valid_and_malformed_sources_are_unresolved(self):
        raw = [movie("m1", "/data/a.mkv", sources=[
            {"Path": "/data/a.mkv", "Protocol": "File", "Size": 10 * GB, "Container": "mkv", "IsRemote": False},
            {"Path": "/data/b.mkv", "Protocol": "File", "Size": None, "Container": "mkv", "IsRemote": False},
        ])]
        inventory = subject.normalize_jellyfin_inventory(raw)
        self.assertEqual(inventory["files"], [])
        self.assertEqual(inventory["unresolved"][0]["reason"], "malformed_media_sources")
        self.assertNotIn("/data/", repr(inventory["unresolved"]))

    def test_remote_placeholder_and_strm_are_excluded(self):
        remote = movie("remote", "https://example.test/video", sources=[
            {"Path": "https://example.test/video", "Protocol": "Http", "Size": 10 * GB, "IsRemote": True}
        ])
        placeholder = movie("placeholder", "/data/p.mkv")
        placeholder["IsPlaceHolder"] = True
        strm = movie("strm", "/data/r.strm")
        inventory = subject.normalize_jellyfin_inventory([remote, placeholder, strm])
        self.assertEqual(inventory["files"], [])
        self.assertEqual(inventory["unresolved"], [])

    def test_malformed_watched_metadata_is_unresolved(self):
        raw = movie("m1", "/data/a.mkv")
        del raw["UserData"]["IsFavorite"]
        inventory = subject.normalize_jellyfin_inventory([raw])
        self.assertEqual(inventory["files"], [])
        self.assertEqual(inventory["unresolved"][0]["reason"], "malformed_watch_metadata")

    def test_paginated_movies_and_episodes_are_fetched(self):
        calls = []
        pages = {
            ("Movie", "0"): {"Items": [movie("m1", "/data/m1.mkv")], "TotalRecordCount": 2},
            ("Movie", "1"): {"Items": [movie("m2", "/data/m2.mkv")], "TotalRecordCount": 2},
            ("Episode", "0"): {"Items": [episode("e1", "/data/e1.mkv")], "TotalRecordCount": 1},
        }
        def fake_get(_path, query):
            calls.append((query["IncludeItemTypes"], query["StartIndex"]))
            return pages[(query["IncludeItemTypes"], query["StartIndex"])]
        with patch.object(subject, "_jellyfin_items_path", return_value="/Users/u1/Items"):
            inventory = subject.fetch_jellyfin_cleanup_inventory(fake_get)
        self.assertEqual(len(inventory["files"]), 3)
        self.assertEqual(calls, [("Movie", "0"), ("Movie", "1"), ("Episode", "0")])


class PolicyTests(unittest.TestCase):
    def preview(self, raw, p=None, *, free=100*GB, total=1000*GB):
        inventory = subject.normalize_jellyfin_inventory(raw)
        return subject.evaluate_cleanup_preview(
            inventory,
            {"total": total, "used": total-free, "free": free},
            p or policy(),
            evaluated_at=NOW,
            jellyfin_external_url="http://127.0.0.1:8096",
        )

    def test_movie_boundary_is_inclusive_and_order_is_deterministic(self):
        raw = [
            movie("newer", "/data/newer.mkv", size=30*GB, last=30),
            movie("older-small", "/data/old-small.mkv", size=10*GB, last=50),
            movie("older-large", "/data/old-large.mkv", size=40*GB, last=50),
        ]
        first = self.preview(raw, free=120*GB)
        second = self.preview(list(reversed(raw)), free=120*GB)
        self.assertEqual([c["id"] for c in first["candidates"]], [c["id"] for c in second["candidates"]])
        self.assertEqual(first["storage"]["eligibleBytes"], 80*GB)
        self.assertEqual(first["storage"]["recommendedBytes"], 80*GB)
        self.assertEqual(first["storage"]["remainingShortfallBytes"], 0)
        self.assertTrue(all(c["recommended"] for c in first["candidates"]))

    def test_target_met_returns_no_recommended_plan_but_all_matches(self):
        result = self.preview([movie("m1", "/data/m1.mkv", last=60)], free=250*GB)
        self.assertEqual(result["storage"]["requiredReclaimBytes"], 0)
        self.assertEqual(result["storage"]["recommendedBytes"], 0)
        self.assertFalse(result["candidates"][0]["recommended"])

    def test_insufficient_capacity_returns_shortfall(self):
        result = self.preview([movie("m1", "/data/m1.mkv", size=10*GB, last=60)], free=100*GB)
        self.assertEqual(result["storage"]["recommendedBytes"], 10*GB)
        self.assertEqual(result["storage"]["projectedFreeBytes"], 110*GB)
        self.assertEqual(result["storage"]["remainingShortfallBytes"], 90*GB)

    def test_hard_protections_override_large_rule(self):
        raw = [
            movie("never", "/data/never.mkv", size=30*GB, played=False),
            movie("progress", "/data/progress.mkv", size=30*GB, played=False, position=100),
            movie("favorite", "/data/favorite.mkv", size=30*GB, favorite=True, last=120),
            movie("recent", "/data/recent.mkv", size=30*GB, added=2, last=120),
        ]
        result = self.preview(raw)
        self.assertEqual(result["candidates"], [])
        codes = {entry["code"] for entry in result["blocked"]}
        self.assertEqual(codes, {"never_watched", "in_progress", "favorite", "recent_addition"})

    def test_manual_pin_overrides_eligibility(self):
        inv = subject.normalize_jellyfin_inventory([movie("m1", "/data/m1.mkv", last=60)])
        pinned = inv["files"][0]["id"]
        p = policy()
        p["protections"]["pinnedCandidateIds"] = [pinned]
        result = subject.evaluate_cleanup_preview(
            inv, {"total": 1000*GB, "used": 900*GB, "free": 100*GB}, p,
            evaluated_at=NOW,
        )
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["blocked"][0]["code"], "manual_pin")

    def test_latest_standard_episodes_are_protected_from_rolling_rule(self):
        raw = [episode(f"e{number}", f"/data/e{number}.mkv", number=number, last=30) for number in range(1, 6)]
        result = self.preview(raw)
        eligible_subtitles = {c["subtitle"] for c in result["candidates"]}
        self.assertEqual(eligible_subtitles, {"Episode · S01E01", "Episode · S01E02"})

    def test_season_zero_is_not_eligible_through_episode_retention(self):
        p = policy()
        p["rules"]["largeWatchedFiles"]["enabled"] = False
        result = self.preview([episode("special", "/data/special.mkv", season=0, number=1, last=120)], p)
        self.assertEqual(result["candidates"], [])

    def test_multi_episode_file_is_atomic(self):
        raw = [
            episode("e1", "/data/multi.mkv", number=1, last=60),
            episode("e2", "/data/multi.mkv", number=2, last=5),
            episode("e3", "/data/e3.mkv", number=3, last=5),
            episode("e4", "/data/e4.mkv", number=4, last=5),
            episode("e5", "/data/e5.mkv", number=5, last=5),
        ]
        p = policy()
        p["rules"]["largeWatchedFiles"]["enabled"] = False
        result = self.preview(raw, p)
        self.assertFalse(any(c["subtitle"].startswith("Episode · S01E01") for c in result["candidates"]))

    def test_unresolved_items_degrade_without_private_paths(self):
        bad = movie("bad", "/secret/library/a.mkv")
        bad["MediaSources"][0]["Size"] = None
        result = self.preview([bad])
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["summary"]["unresolvedFiles"], 1)
        self.assertNotIn("/secret/", repr(result))
        self.assertEqual(result["candidates"], [])


if __name__ == "__main__":
    unittest.main()
