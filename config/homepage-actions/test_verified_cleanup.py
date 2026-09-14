#!/usr/bin/env python3
"""Focused tests for the staged, opt-in verified original cleanup seam."""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

import config
from verified_cleanup import apply_verified_cleanup, verify_torrent


HASH = "a" * 40
OTHER_HASH = "b" * 40


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


class FakeQbit:
    def __init__(self, torrent, files, all_torrents=None, delete_mode="ok", stopped_state="pausedUP"):
        self.torrent_value = dict(torrent)
        self.files_value = [dict(row) for row in files]
        self.all_torrents_value = [dict(row) for row in (all_torrents or [torrent])]
        self.delete_mode = delete_mode
        self.stopped_state = stopped_state
        self.calls = []
        self.stopped = False
        self.deleted = False

    def torrent(self, torrent_hash):
        self.calls.append(("torrent", torrent_hash))
        if self.deleted:
            return None
        value = dict(self.torrent_value)
        if self.stopped:
            value["state"] = self.stopped_state
        return value

    def files(self, torrent_hash):
        self.calls.append(("files", torrent_hash))
        return [dict(row) for row in self.files_value]

    def torrents(self):
        self.calls.append(("torrents",))
        return [dict(row) for row in self.all_torrents_value]

    def stop(self, torrent_hash):
        self.calls.append(("stop", torrent_hash))
        self.stopped = True
        return {"status": 200}

    def delete(self, torrent_hash):
        self.calls.append(("delete", torrent_hash, True))
        if self.delete_mode == "ambiguous":
            raise RuntimeError("connection lost after request")
        content_path = Path(self.torrent_value["content_path"])
        if content_path.is_dir():
            for item in sorted(content_path.rglob("*"), reverse=True):
                if item.is_file() or item.is_symlink():
                    item.unlink()
            for item in sorted(content_path.rglob("*"), reverse=True):
                if item.is_dir():
                    item.rmdir()
            content_path.rmdir()
        elif content_path.exists():
            content_path.unlink()
        self.deleted = True
        return {"status": 200}


class FakeArr:
    def __init__(self, records, entity=None, after_delete_entity=None):
        self.records = records
        self.entity_value = entity or {"id": 42, "path": "/data/media/tv/Show"}
        self.after_delete_entity = after_delete_entity
        self.calls = []

    def history(self, service, arr_id):
        self.calls.append(("history", service, arr_id))
        return {"records": list(self.records), "complete": True, "totalRecords": len(self.records)}

    def library(self, service, arr_id):
        self.calls.append(("library", service, arr_id))
        if self.after_delete_entity is not None and len(self.calls) > 1:
            return self.after_delete_entity
        return self.entity_value


def _fixture(base, *, content_name="Show.S01E01.mkv", body=b"episode data"):
    downloads = base / "downloads"
    library = base / "library"
    source_dir = downloads / "sonarr" / "Show"
    destination = library / "tv" / "Show" / "Season 01" / content_name
    source_dir.mkdir(parents=True)
    destination.parent.mkdir(parents=True)
    source = source_dir / content_name
    source.write_bytes(body)
    destination.write_bytes(body)
    torrent = {
        "hash": HASH,
        "state": "stalledUP",
        "progress": 1.0,
        "amount_left": 0,
        "content_path": str(source_dir),
    }
    files = [{"index": 0, "name": content_name, "size": len(body), "progress": 1.0, "is_seed": True, "priority": 1}]
    history = [{
        "id": 100,
        "downloadId": HASH,
        "eventType": "downloadFolderImported",
        "seriesId": 42,
        "episodeFileId": 9,
        "data": {"sourcePath": str(source), "importedPath": str(destination)},
    }]
    return downloads, library, source, destination, torrent, files, history


class VerifiedCleanupTests(unittest.TestCase):
    def test_complete_import_is_hash_verified_then_qbit_owns_source_removal(self):
        with tempfile.TemporaryDirectory() as temporary:
            downloads, library, source, destination, torrent, files, history = _fixture(Path(temporary))
            qbit = FakeQbit(torrent, files)
            arr = FakeArr(history)
            result = apply_verified_cleanup(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=qbit,
                arr=arr,
                downloads_root=downloads,
                library_root=library,
                enabled=True,
                state_path=Path(temporary) / "state.json",
            )
            self.assertEqual(result["status"], "deleted")
            self.assertFalse(source.exists())
            self.assertTrue(destination.exists())
            self.assertEqual(_sha256(destination.read_bytes()), _sha256(b"episode data"))
            self.assertIn(("stop", HASH), qbit.calls)
            self.assertIn(("delete", HASH, True), qbit.calls)

    def test_single_file_torrent_uses_content_path_as_the_source_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            downloads = base / "downloads"
            library = base / "library"
            source = downloads / "Movie.mkv"
            destination = library / "movies" / "Movie.mkv"
            source.parent.mkdir(parents=True)
            destination.parent.mkdir(parents=True)
            source.write_bytes(b"movie data")
            destination.write_bytes(b"movie data")
            torrent = {
                "hash": HASH,
                "state": "stalledUP",
                "progress": 1.0,
                "amount_left": 0,
                "content_path": str(source),
            }
            files = [{
                "index": 0,
                "name": source.name,
                "size": source.stat().st_size,
                "progress": 1.0,
                "is_seed": True,
                "priority": 1,
            }]
            history = [{
                "id": 101,
                "downloadId": HASH,
                "eventType": "movieFileImported",
                "movieId": 42,
                "data": {"sourcePath": str(source), "importedPath": str(destination)},
            }]
            result = apply_verified_cleanup(
                HASH,
                {"service": "radarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr(history, entity={"id": 42, "path": "/data/media/movies/Movie"}),
                downloads_root=downloads,
                library_root=library,
                enabled=True,
                state_path=base / "state.json",
            )
            self.assertEqual(result["status"], "deleted")
            self.assertFalse(source.exists())
            self.assertTrue(destination.exists())

    def test_supported_stopped_up_state_is_accepted_after_stop(self):
        with tempfile.TemporaryDirectory() as temporary:
            downloads, library, source, destination, torrent, files, history = _fixture(Path(temporary))
            qbit = FakeQbit(torrent, files, stopped_state="stoppedUP")
            result = apply_verified_cleanup(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=qbit,
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
                enabled=True,
                state_path=Path(temporary) / "state.json",
            )
            self.assertEqual(result["status"], "deleted")
            self.assertFalse(source.exists())
            self.assertTrue(destination.exists())

    def test_stop_transition_is_allowed_to_propagate_before_revalidation(self):
        with tempfile.TemporaryDirectory() as temporary:
            downloads, library, source, destination, torrent, files, history = _fixture(Path(temporary))

            class DelayedStopQbit(FakeQbit):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.post_stop_reads = 0

                def torrent(self, torrent_hash):
                    value = super().torrent(torrent_hash)
                    if self.stopped:
                        self.post_stop_reads += 1
                        if self.post_stop_reads < 3:
                            value["state"] = "queuedUP"
                    return value

            qbit = DelayedStopQbit(torrent, files)
            result = apply_verified_cleanup(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=qbit,
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
                enabled=True,
                state_path=Path(temporary) / "state.json",
            )
            self.assertEqual(result["status"], "deleted")
            self.assertGreaterEqual(qbit.post_stop_reads, 3)
            self.assertFalse(source.exists())
            self.assertTrue(destination.exists())

    def test_default_off_does_not_call_stop_or_delete(self):
        with tempfile.TemporaryDirectory() as temporary:
            downloads, library, _source, _destination, torrent, files, history = _fixture(Path(temporary))
            qbit = FakeQbit(torrent, files)
            arr = FakeArr(history)
            result = apply_verified_cleanup(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=qbit,
                arr=arr,
                downloads_root=downloads,
                library_root=library,
                state_path=Path(temporary) / "state.json",
            )
            self.assertEqual(result["status"], "disabled")
            self.assertNotIn(("stop", HASH), qbit.calls)
            self.assertFalse(any(call[0] == "delete" for call in qbit.calls))

    def test_partial_pack_keeps_entire_torrent(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            downloads, library, source, destination, torrent, files, history = _fixture(base)
            second = source.parent / "Show.S01E02.mkv"
            second.write_bytes(b"second")
            files.append({"index": 1, "name": second.name, "size": 6, "progress": 1.0, "is_seed": True, "priority": 1})
            result = verify_torrent(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
            )
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["reason"], "missing_import_evidence")
            self.assertTrue(source.exists())
            self.assertTrue(destination.exists())

    def test_unselected_qbit_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            downloads, library, _source, _destination, torrent, files, history = _fixture(Path(temporary))
            files[0]["priority"] = 0
            result = verify_torrent(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
            )
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["reason"], "qbit_file_not_selected")

    def test_single_file_torrent_uses_current_content_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            downloads = base / "downloads"
            library = base / "library"
            source = downloads / "movie.mkv"
            destination = library / "movies" / "movie.mkv"
            downloads.mkdir()
            destination.parent.mkdir(parents=True)
            source.write_bytes(b"movie data")
            destination.write_bytes(b"movie data")
            torrent = {
                "hash": HASH,
                "state": "stalledUP",
                "progress": 1.0,
                "amount_left": 0,
                "content_path": str(source),
            }
            files = [{"index": 0, "name": "movie.mkv", "size": 10, "progress": 1.0, "is_seed": True, "priority": 1}]
            history = [{
                "id": 101,
                "downloadId": HASH,
                "eventType": "movieFileImported",
                "movieId": 42,
                "data": {"sourcePath": str(source), "importedPath": str(destination)},
            }]
            result = verify_torrent(
                HASH,
                {"service": "radarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr(history, entity={"id": 42}),
                downloads_root=downloads,
                library_root=library,
            )
            self.assertEqual(result["status"], "verified")

    def test_unknown_extra_sidecar_and_preexisting_file_skips(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            downloads, library, source, _destination, torrent, files, history = _fixture(base)
            (source.parent / "sample.srt").write_text("sidecar", encoding="utf-8")
            result = verify_torrent(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
            )
            self.assertEqual(result["reason"], "unknown_extra")
            self.assertTrue(source.exists())

    def test_shared_or_overlapping_torrent_path_skips(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            downloads, library, _source, _destination, torrent, files, history = _fixture(base)
            other = dict(torrent, hash=OTHER_HASH, content_path=str(Path(torrent["content_path"]).parent))
            result = verify_torrent(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files, all_torrents=[torrent, other]),
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
            )
            self.assertEqual(result["reason"], "shared_source_path")

    def test_source_mutation_or_destination_removal_after_snapshot_skips(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            downloads, library, source, destination, torrent, files, history = _fixture(base)
            original_hash = _sha256(source.read_bytes())
            source.write_bytes(b"changed")
            result = verify_torrent(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
            )
            self.assertEqual(result["reason"], "hash_mismatch")
            self.assertNotEqual(_sha256(source.read_bytes()), original_hash)
            source.write_bytes(b"episode data")
            destination.unlink()
            result = verify_torrent(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
            )
            self.assertEqual(result["reason"], "destination_missing")

    def test_symlink_and_traversal_are_never_cleanup_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            downloads, library, source, _destination, torrent, files, history = _fixture(base)
            outside = base / "outside.mkv"
            outside.write_bytes(b"outside")
            source.unlink()
            source.symlink_to(outside)
            result = verify_torrent(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
            )
            self.assertEqual(result["reason"], "symlink_source")
            files[0]["name"] = "../outside.mkv"
            result = verify_torrent(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
            )
            self.assertEqual(result["reason"], "unsafe_file_path")

    def test_failed_hash_and_stale_or_incomplete_history_skip(self):
        with tempfile.TemporaryDirectory() as temporary:
            downloads, library, _source, _destination, torrent, files, history = _fixture(Path(temporary))
            result = verify_torrent(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr([{**history[0], "data": {"sourcePath": history[0]["data"]["sourcePath"], "importedPath": history[0]["data"]["importedPath"]}}]),
                downloads_root=downloads,
                library_root=library,
            )
            self.assertEqual(result["status"], "verified")
            destination = library / "tv" / "Show" / "Season 01" / "Show.S01E01.mkv"
            destination.write_bytes(b"wrong")
            result = verify_torrent(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
            )
            self.assertEqual(result["reason"], "hash_mismatch")
            result = verify_torrent(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
            )
            self.assertEqual(result["reason"], "hash_mismatch")

    def test_absent_api_or_incomplete_history_is_preserve(self):
        with tempfile.TemporaryDirectory() as temporary:
            downloads, library, _source, _destination, torrent, files, _history = _fixture(Path(temporary))
            class IncompleteArr(FakeArr):
                def history(self, service, arr_id):
                    return {"records": [], "complete": False, "totalRecords": 2}

            result = verify_torrent(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=IncompleteArr([]),
                downloads_root=downloads,
                library_root=library,
            )
            self.assertEqual(result["reason"], "incomplete_import_history")

            class MissingArr(FakeArr):
                def history(self, service, arr_id):
                    raise RuntimeError("Arr unavailable")

            result = verify_torrent(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=MissingArr([]),
                downloads_root=downloads,
                library_root=library,
            )
            self.assertEqual(result["reason"], "arr_unavailable")

    def test_restart_record_is_atomic_and_ambiguous_delete_is_not_repeated(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            downloads, library, _source, _destination, torrent, files, history = _fixture(base)
            state_path = base / "state.json"
            qbit = FakeQbit(torrent, files, delete_mode="ambiguous")
            result = apply_verified_cleanup(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=qbit,
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
                enabled=True,
                state_path=state_path,
            )
            self.assertEqual(result["reason"], "ambiguous_delete")
            delete_count = sum(call[0] == "delete" for call in qbit.calls)
            result = apply_verified_cleanup(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=qbit,
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
                enabled=True,
                state_path=state_path,
            )
            self.assertEqual(result["reason"], "ambiguous_delete")
            self.assertEqual(sum(call[0] == "delete" for call in qbit.calls), delete_count)
            stored = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(stored[HASH]["status"], "ambiguous_delete")

    def test_library_destination_must_survive_native_delete(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            downloads, library, _source, destination, torrent, files, history = _fixture(base)

            class PostDeleteLibraryMutationQbit(FakeQbit):
                def delete(self, torrent_hash):
                    result = super().delete(torrent_hash)
                    destination.unlink()
                    return result

            result = apply_verified_cleanup(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=PostDeleteLibraryMutationQbit(torrent, files),
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
                enabled=True,
                state_path=base / "state.json",
            )
            self.assertEqual(result["reason"], "library_missing_after_delete")


if __name__ == "__main__":
    unittest.main()
