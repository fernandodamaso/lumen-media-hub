#!/usr/bin/env python3
"""Focused tests for the staged, opt-in verified original cleanup seam."""

import hashlib
import json
import os
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

import clients.arr as arr_client
import config
import verified_cleanup
from verified_cleanup import (
    ArrVerificationClient,
    apply_verified_cleanup,
    mapping_for_torrent,
    run_verified_cleanup_cycle,
    start_verified_cleanup_scheduler,
    stop_verified_cleanup_scheduler,
    verify_torrent,
    _verified_cleanup_scheduler_loop,
)


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

    def configured_services(self):
        return ("sonarr", "radarr")

    def history(self, service, arr_id):
        self.calls.append(("history", service, arr_id))
        return {"records": list(self.records), "complete": True, "totalRecords": len(self.records)}

    def library(self, service, arr_id):
        self.calls.append(("library", service, arr_id))
        if self.after_delete_entity is not None and len(self.calls) > 1:
            return self.after_delete_entity
        return self.entity_value


def _history(records):
    """Complete single-page history payload for fake Arr clients."""
    records = [dict(record) for record in records]
    return {"records": records, "complete": True, "totalRecords": len(records)}


class FakeHistoryArr:
    """Arr fake with declared services and complete per-case download history.

    ``payloads`` maps ``(service, download_id)`` to either a list of records
    (wrapped in complete metadata), a raw payload dict (used to exercise
    invalid metadata), or an exception instance to raise. Missing entries
    return an empty complete snapshot.
    """

    def __init__(self, payloads=None, *, services=("sonarr", "radarr"), outages=()):
        self.payloads = dict(payloads or {})
        self.services = tuple(services)
        self.outages = frozenset(outages)
        self.calls = []

    def configured_services(self):
        return self.services

    def history_for_download(self, service, download_id):
        self.calls.append((service, download_id))
        if service in self.outages:
            raise RuntimeError("Arr connection failed")
        value = self.payloads.get((service, download_id))
        if value is None:
            return _history([])
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, dict):
            return value
        return _history(value)


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

    def test_hardlinked_source_and_library_copy_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            downloads, library, source, destination, torrent, files, history = _fixture(Path(temporary))
            destination.unlink()
            os.link(source, destination)
            result = apply_verified_cleanup(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
                enabled=True,
                state_path=Path(temporary) / "state.json",
            )
            self.assertEqual(result["reason"], "source_destination_alias")
            self.assertTrue(source.exists())
            self.assertTrue(destination.exists())

    def test_deleted_record_does_not_block_a_readded_torrent(self):
        with tempfile.TemporaryDirectory() as temporary:
            downloads, library, source, destination, torrent, files, history = _fixture(Path(temporary))
            state_path = Path(temporary) / "state.json"
            first = apply_verified_cleanup(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
                enabled=True,
                state_path=state_path,
            )
            self.assertEqual(first["status"], "deleted")
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b"episode data")
            retry = apply_verified_cleanup(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
                enabled=True,
                state_path=state_path,
            )
            self.assertEqual(retry["status"], "deleted")
            self.assertFalse(source.exists())
            self.assertTrue(destination.exists())

    def test_qbit_folder_prefixed_names_map_onto_content_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            downloads, library, source, destination, torrent, files, history = _fixture(Path(temporary))
            pack = Path(torrent["content_path"]).name
            files = [{**files[0], "name": f"{pack}/{source.name}"}]
            result = apply_verified_cleanup(
                HASH,
                {"service": "sonarr", "id": 42},
                qbit=FakeQbit(torrent, files),
                arr=FakeArr(history),
                downloads_root=downloads,
                library_root=library,
                enabled=True,
                state_path=Path(temporary) / "state.json",
            )
            self.assertEqual(result["status"], "deleted")
            self.assertFalse(source.exists())
            self.assertTrue(destination.exists())

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


class MappingAndCycleTests(unittest.TestCase):
    def test_mapping_uses_unique_sonarr_import_history(self):
        class Arr:
            def configured_services(self):
                return ("sonarr", "radarr")

            def history_for_download(self, service, torrent_hash):
                if service == "sonarr":
                    return {
                        "records": [
                            {
                                "downloadId": HASH,
                                "eventType": "downloadFolderImported",
                                "seriesId": 42,
                            }
                        ],
                        "complete": True,
                        "totalRecords": 1,
                    }
                return {"records": [], "complete": True, "totalRecords": 0}

        self.assertEqual(mapping_for_torrent(Arr(), HASH), {"service": "sonarr", "id": 42})

    def test_mapping_matches_uppercase_sonarr_download_id(self):
        class Arr:
            def configured_services(self):
                return ("sonarr", "radarr")

            def history_for_download(self, service, download_id):
                if service == "sonarr" and download_id == HASH.upper():
                    return {
                        "records": [
                            {
                                "downloadId": HASH.upper(),
                                "eventType": "downloadFolderImported",
                                "seriesId": 42,
                            }
                        ],
                        "complete": True,
                        "totalRecords": 1,
                    }
                return {"records": [], "complete": True, "totalRecords": 0}

        self.assertEqual(mapping_for_torrent(Arr(), HASH), {"service": "sonarr", "id": 42})

    def test_mapping_skips_when_sonarr_and_radarr_both_match(self):
        class Arr:
            def configured_services(self):
                return ("sonarr", "radarr")

            def history_for_download(self, service, torrent_hash):
                if service == "sonarr":
                    return {
                        "records": [
                            {
                                "downloadId": HASH,
                                "eventType": "downloadFolderImported",
                                "seriesId": 42,
                            }
                        ],
                        "complete": True,
                        "totalRecords": 1,
                    }
                return {
                    "records": [
                        {
                            "downloadId": HASH,
                            "eventType": "movieFileImported",
                            "movieId": 7,
                        }
                    ],
                    "complete": True,
                    "totalRecords": 1,
                }

        self.assertIsNone(mapping_for_torrent(Arr(), HASH))

    def test_disabled_cycle_makes_no_calls(self):
        applied = []
        qbit = FakeQbit(
            {"hash": HASH, "progress": 1.0, "amount_left": 0, "content_path": "/downloads/x"},
            [],
        )
        result = run_verified_cleanup_cycle(
            qbit=qbit,
            enabled=False,
            apply=lambda *args, **kwargs: applied.append(args) or {"status": "deleted"},
            mapping_lookup=lambda torrent_hash: {"service": "sonarr", "id": 42},
        )
        self.assertEqual(result, {"status": "disabled", "results": []})
        self.assertEqual(applied, [])
        self.assertEqual(qbit.calls, [])

    def test_complete_imported_torrent_is_applied(self):
        applied = []
        torrent = {"hash": HASH, "progress": 1.0, "amount_left": 0, "content_path": "/downloads/x"}
        qbit = FakeQbit(torrent, [])
        mapping = {"service": "sonarr", "id": 42}

        def apply(torrent_hash, received, **kwargs):
            applied.append((torrent_hash, received, kwargs["enabled"]))
            return {"status": "deleted", "torrent_hash": torrent_hash}

        result = run_verified_cleanup_cycle(
            qbit=qbit,
            enabled=True,
            apply=apply,
            mapping_lookup=lambda torrent_hash: mapping,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["results"][0]["status"], "deleted")
        self.assertEqual(applied, [(HASH, mapping, True)])

    def test_incomplete_torrent_is_not_applied(self):
        applied = []
        torrent = {"hash": HASH, "progress": 0.0, "amount_left": 12, "content_path": "/downloads/x"}
        result = run_verified_cleanup_cycle(
            qbit=FakeQbit(torrent, []),
            enabled=True,
            apply=lambda *args, **kwargs: applied.append(args) or {"status": "deleted"},
            mapping_lookup=lambda torrent_hash: {"service": "sonarr", "id": 42},
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["results"][0]["reason"], "torrent_incomplete")
        self.assertEqual(applied, [])

    def test_unmapped_complete_torrent_is_skipped(self):
        applied = []
        torrent = {"hash": HASH, "progress": 1.0, "amount_left": 0, "content_path": "/downloads/x"}
        result = run_verified_cleanup_cycle(
            qbit=FakeQbit(torrent, []),
            enabled=True,
            apply=lambda *args, **kwargs: applied.append(args) or {"status": "deleted"},
            mapping_lookup=lambda torrent_hash: None,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["results"][0]["reason"], "no_import_mapping")
        self.assertEqual(applied, [])

    def test_scheduler_does_not_start_when_disabled(self):
        previous = config.VERIFIED_CLEANUP_ENABLED
        config.VERIFIED_CLEANUP_ENABLED = False
        try:
            self.assertFalse(start_verified_cleanup_scheduler(0.01))
        finally:
            stop_verified_cleanup_scheduler()
            config.VERIFIED_CLEANUP_ENABLED = previous

    def test_scheduler_loop_retries_after_cycle_exception(self):
        calls = []
        waits = []

        def run_cycle():
            calls.append(len(calls))
            if len(calls) == 1:
                raise RuntimeError("qbit unavailable")

        def wait(_event, timeout):
            waits.append(timeout)
            return len(waits) >= 2

        _verified_cleanup_scheduler_loop(300, object(), run_cycle, wait)
        self.assertEqual(calls, [0, 1])
        self.assertEqual(waits, [300, 300])


class MappingEvidenceTests(unittest.TestCase):
    def test_mapping_rejects_two_series_for_one_hash(self):
        arr_with_series_42_and_43 = FakeHistoryArr(
            {
                ("sonarr", HASH.upper()): [
                    {"downloadId": HASH, "eventType": "downloadFolderImported", "seriesId": 42},
                    {"downloadId": HASH, "eventType": "episodeFileImported", "seriesId": 43},
                ]
            }
        )
        self.assertIsNone(mapping_for_torrent(arr_with_series_42_and_43, HASH))

    def test_mapping_deduplicates_multiple_episodes_from_one_series(self):
        arr_with_repeated_series_42 = FakeHistoryArr(
            {
                ("sonarr", HASH.upper()): [
                    {"downloadId": HASH, "eventType": "downloadFolderImported", "seriesId": 42},
                    {"downloadId": HASH, "eventType": "episodeFileImported", "seriesId": 42},
                    {"downloadId": HASH.upper(), "eventType": "seriesFolderImported", "seriesId": 42},
                ]
            }
        )
        self.assertEqual(
            mapping_for_torrent(arr_with_repeated_series_42, HASH),
            {"service": "sonarr", "id": 42},
        )

    def test_mapping_rejects_sonarr_and_radarr_matches(self):
        arr_with_both_services = FakeHistoryArr(
            {
                ("sonarr", HASH.upper()): [
                    {"downloadId": HASH, "eventType": "downloadFolderImported", "seriesId": 42}
                ],
                ("radarr", HASH.upper()): [
                    {"downloadId": HASH, "eventType": "movieFileImported", "movieId": 7}
                ],
            }
        )
        self.assertIsNone(mapping_for_torrent(arr_with_both_services, HASH))

    def test_mapping_preserves_on_configured_arr_outage(self):
        arr_with_radarr_outage = FakeHistoryArr(
            {
                ("sonarr", HASH.upper()): [
                    {"downloadId": HASH, "eventType": "downloadFolderImported", "seriesId": 42}
                ]
            },
            outages=("radarr",),
        )
        with self.assertRaisesRegex(RuntimeError, "import_history_unavailable"):
            mapping_for_torrent(arr_with_radarr_outage, HASH)

    def test_mapping_ignores_unconfigured_service(self):
        arr_with_only_sonarr_configured = FakeHistoryArr(
            {
                ("sonarr", HASH.upper()): [
                    {"downloadId": HASH, "eventType": "downloadFolderImported", "seriesId": 42}
                ],
                ("radarr", HASH.upper()): [
                    {"downloadId": HASH, "eventType": "movieFileImported", "movieId": 7}
                ],
            },
            services=("sonarr",),
        )
        self.assertEqual(
            mapping_for_torrent(arr_with_only_sonarr_configured, HASH),
            {"service": "sonarr", "id": 42},
        )
        self.assertTrue(
            all(service == "sonarr" for service, _ in arr_with_only_sonarr_configured.calls)
        )

    def test_conflict_on_second_history_page_is_rejected(self):
        pages = {
            1: {
                "records": [
                    {"id": 1, "downloadId": HASH, "eventType": "downloadFolderImported", "seriesId": 42}
                ],
                "totalRecords": 2,
            },
            2: {
                "records": [
                    {"id": 2, "downloadId": HASH, "eventType": "episodeFileImported", "seriesId": 43}
                ],
                "totalRecords": 2,
            },
        }

        def fake_arr_get(base, api_key, path):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
            return pages[int(query["page"][0])]

        class PagedArr:
            def configured_services(self):
                return ("sonarr", "radarr")

            def history_for_download(self, service, download_id):
                return arr_client.fetch_arr_history_for_download_all(
                    "http://sonarr", "key", download_id, page_size=1
                )

        with mock.patch.object(arr_client, "_arr_get", side_effect=fake_arr_get):
            snapshot = arr_client.fetch_arr_history_for_download_all(
                "http://sonarr", "key", HASH, page_size=1
            )
            self.assertEqual(snapshot["totalRecords"], 2)
            self.assertEqual(len(snapshot["records"]), 2)
            self.assertIsNone(mapping_for_torrent(PagedArr(), HASH))

    def test_mapping_rejects_conflicting_case_variant_evidence(self):
        conflicting_cases = FakeHistoryArr(
            {
                ("sonarr", HASH.upper()): [
                    {"downloadId": HASH, "eventType": "downloadFolderImported", "seriesId": 42}
                ],
                ("sonarr", HASH): [
                    {"downloadId": HASH, "eventType": "downloadFolderImported", "seriesId": 43}
                ],
            }
        )
        self.assertIsNone(mapping_for_torrent(conflicting_cases, HASH))

    def test_mapping_raises_when_configured_history_is_incomplete(self):
        incomplete_payloads = (
            {
                "records": [
                    {"downloadId": HASH, "eventType": "downloadFolderImported", "seriesId": 42}
                ],
                "complete": False,
                "totalRecords": 1,
            },
            {"records": [{"downloadId": HASH, "eventType": "downloadFolderImported", "seriesId": 42}]},
            {
                "records": [],
                "complete": True,
                "totalRecords": 2,
            },
        )
        for payload in incomplete_payloads:
            with self.subTest(payload=payload):
                arr = FakeHistoryArr({("sonarr", HASH.upper()): payload})
                with self.assertRaisesRegex(RuntimeError, "import_history_unavailable"):
                    mapping_for_torrent(arr, HASH)

    def test_mapping_returns_none_without_configured_services(self):
        no_services = FakeHistoryArr(
            {
                ("sonarr", HASH.upper()): [
                    {"downloadId": HASH, "eventType": "downloadFolderImported", "seriesId": 42}
                ]
            },
            services=(),
        )
        self.assertIsNone(mapping_for_torrent(no_services, HASH))
        self.assertEqual(no_services.calls, [])

    def test_configured_services_reports_url_and_key_presence_only(self):
        with mock.patch.object(config, "SONARR_URL", "http://sonarr:8989"), mock.patch.object(
            config, "SONARR_API_KEY", "sonarr-secret-key"
        ), mock.patch.object(config, "RADARR_URL", ""), mock.patch.object(
            config, "RADARR_API_KEY", "radarr-secret-key"
        ):
            services = ArrVerificationClient().configured_services()

        self.assertEqual(services, ("sonarr",))
        self.assertNotIn("sonarr-secret-key", " ".join(services))
        self.assertNotIn("radarr-secret-key", " ".join(services))

    def test_history_for_download_uses_complete_snapshot_helper(self):
        with mock.patch.object(
            arr_client,
            "fetch_arr_history_for_download_all",
            return_value={"records": [], "totalRecords": 0, "complete": True},
        ) as helper:
            payload = ArrVerificationClient().history_for_download("sonarr", HASH.upper())

        helper.assert_called_once_with(config.SONARR_URL, config.SONARR_API_KEY, HASH.upper())
        self.assertEqual(payload, {"records": [], "totalRecords": 0, "complete": True})


class CycleResilienceTests(unittest.TestCase):
    """One failing item must never starve later independent items."""

    @staticmethod
    def _complete(hash_value):
        return {"hash": hash_value, "progress": 1.0, "amount_left": 0, "content_path": "/downloads/x"}

    @staticmethod
    def _inventory(*torrents):
        return FakeQbit(torrents[0], [], all_torrents=list(torrents))

    def test_cycle_continues_after_first_item_failure(self):
        visited = []

        def apply(torrent_hash, mapping, **kwargs):
            visited.append(torrent_hash)
            if torrent_hash == HASH:
                raise RuntimeError("apply exploded at /data/media/private")
            return {"status": "skipped", "reason": "stop_not_confirmed", "torrent_hash": torrent_hash}

        result = run_verified_cleanup_cycle(
            qbit=self._inventory(self._complete(HASH), self._complete(OTHER_HASH)),
            enabled=True,
            apply=apply,
            mapping_lookup=lambda torrent_hash: {"service": "sonarr", "id": 42},
        )

        self.assertEqual(visited, [HASH, OTHER_HASH])
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(
            result["results"][0],
            {"status": "error", "reason": "cleanup_item_failed", "torrent_hash": HASH},
        )
        self.assertEqual(
            result["results"][1],
            {"status": "skipped", "reason": "stop_not_confirmed", "torrent_hash": OTHER_HASH},
        )
        self.assertNotIn("/data/media/private", json.dumps(result))

    def test_cycle_continues_after_invalid_item_result(self):
        visited = []

        def apply(torrent_hash, mapping, **kwargs):
            visited.append(torrent_hash)
            if torrent_hash == HASH:
                return {"status": ["deleted"]}
            return {"status": "skipped", "torrent_hash": torrent_hash}

        result = run_verified_cleanup_cycle(
            qbit=self._inventory(self._complete(HASH), self._complete(OTHER_HASH)),
            enabled=True,
            apply=apply,
            mapping_lookup=lambda torrent_hash: {"service": "sonarr", "id": 42},
        )
        self.assertEqual(visited, [HASH, OTHER_HASH])
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(
            result["results"][0],
            {"status": "error", "reason": "cleanup_item_failed", "torrent_hash": HASH},
        )
        self.assertEqual(result["results"][1]["status"], "skipped")

    def test_cycle_degrades_on_returned_item_error_without_leaking_details(self):
        visited = []

        def apply(torrent_hash, mapping, **kwargs):
            visited.append(torrent_hash)
            if torrent_hash == HASH:
                return {"status": "error", "reason": "Connection refused /data/private"}
            return {"status": "skipped", "torrent_hash": torrent_hash}

        result = run_verified_cleanup_cycle(
            qbit=self._inventory(self._complete(HASH), self._complete(OTHER_HASH)),
            enabled=True,
            apply=apply,
            mapping_lookup=lambda torrent_hash: {"service": "sonarr", "id": 42},
        )
        self.assertEqual(visited, [HASH, OTHER_HASH])
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(
            result["results"][0],
            {"status": "error", "reason": "cleanup_item_failed", "torrent_hash": HASH},
        )
        self.assertEqual(result["results"][1]["status"], "skipped")
        self.assertNotIn("/data/private", json.dumps(result))

    def test_cycle_continues_after_first_item_mapping_failure(self):
        lookups, applied = [], []

        def lookup(torrent_hash):
            lookups.append(torrent_hash)
            if torrent_hash == HASH:
                raise RuntimeError("sonarr at http://192.168.1.5:8989 returned 500")
            return {"service": "sonarr", "id": 42}

        def apply(torrent_hash, mapping, **kwargs):
            applied.append(torrent_hash)
            return {"status": "skipped", "reason": "stop_not_confirmed", "torrent_hash": torrent_hash}

        result = run_verified_cleanup_cycle(
            qbit=self._inventory(self._complete(HASH), self._complete(OTHER_HASH)),
            enabled=True,
            apply=apply,
            mapping_lookup=lookup,
        )

        self.assertEqual(lookups, [HASH, OTHER_HASH])
        self.assertEqual(applied, [OTHER_HASH])
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(
            result["results"][0],
            {"status": "error", "reason": "import_history_unavailable", "torrent_hash": HASH},
        )
        self.assertEqual(result["results"][1]["status"], "skipped")
        self.assertNotIn("192.168.1.5", json.dumps(result))

    def test_cycle_preserves_torrent_on_configured_arr_outage(self):
        arr_with_radarr_outage = FakeHistoryArr({}, outages=("radarr",))
        applied = []

        result = run_verified_cleanup_cycle(
            qbit=self._inventory(self._complete(HASH)),
            arr=arr_with_radarr_outage,
            enabled=True,
            apply=lambda *args, **kwargs: applied.append(args[0]) or {"status": "deleted"},
        )

        self.assertEqual(applied, [])
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(
            result["results"][0],
            {"status": "error", "reason": "import_history_unavailable", "torrent_hash": HASH},
        )

    def test_cycle_degrades_when_apply_reports_provider_unavailable(self):
        result = run_verified_cleanup_cycle(
            qbit=self._inventory(self._complete(HASH)),
            enabled=True,
            apply=lambda *args, **kwargs: {
                "status": "skipped",
                "reason": "arr_unavailable",
                "torrent_hash": HASH,
            },
            mapping_lookup=lambda torrent_hash: {"service": "sonarr", "id": 42},
        )

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["results"][0]["reason"], "arr_unavailable")

    def test_malformed_state_blocks_cleanup_before_item_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"
            state_path.write_text("not-json", encoding="utf-8")
            qbit = self._inventory(self._complete(HASH))

            result = run_verified_cleanup_cycle(
                qbit=qbit,
                enabled=True,
                state_path=state_path,
                apply=apply_verified_cleanup,
                mapping_lookup=lambda torrent_hash: {"service": "sonarr", "id": 42},
            )

            self.assertEqual(result["status"], "degraded")
            self.assertEqual(result["results"][0]["status"], "error")
            self.assertEqual(result["results"][0]["reason"], "cleanup_item_failed")
            self.assertEqual(qbit.calls, [("torrents",)])
            self.assertEqual(state_path.read_text(encoding="utf-8"), "not-json")

    def test_cycle_reports_qbit_unavailable_when_constructor_fails(self):
        with mock.patch(
            "verified_cleanup.QbittorrentVerificationClient",
            side_effect=RuntimeError("qbit login rejected credential"),
        ):
            result = run_verified_cleanup_cycle(
                enabled=True,
                apply=lambda *args, **kwargs: {"status": "deleted"},
                mapping_lookup=lambda torrent_hash: {"service": "sonarr", "id": 42},
            )

        self.assertEqual(result, {"status": "qbit_unavailable", "results": []})
        self.assertNotIn("credential", json.dumps(result))

    def test_unknown_deletion_outcome_stays_terminal_and_degrades_cycle(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"
            state_path.write_text(
                json.dumps({HASH: {"status": "delete_outcome_unknown", "torrent_hash": HASH}}),
                encoding="utf-8",
            )
            qbit = FakeQbit(self._complete(HASH), [])

            for _ in range(2):
                result = run_verified_cleanup_cycle(
                    qbit=qbit,
                    enabled=True,
                    state_path=state_path,
                    apply=apply_verified_cleanup,
                    mapping_lookup=lambda torrent_hash: {"service": "sonarr", "id": 42},
                )
                self.assertEqual(result["status"], "degraded")
                self.assertEqual(result["results"][0]["status"], "delete_outcome_unknown")

            self.assertNotIn("delete", [call[0] for call in qbit.calls])
            self.assertNotIn("stop", [call[0] for call in qbit.calls])


class SchedulerTelemetryAndLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.previous_enabled = config.VERIFIED_CLEANUP_ENABLED
        # Register restoration before mutating shared config so a failing setUp
        # cannot leak ENABLED=True into later tests.
        self.addCleanup(self._restore)
        config.VERIFIED_CLEANUP_ENABLED = True
        self._reset_status()
        self.addCleanup(stop_verified_cleanup_scheduler, 2.0)

    def _restore(self):
        config.VERIFIED_CLEANUP_ENABLED = self.previous_enabled
        self._reset_status()

    @staticmethod
    def _reset_status():
        with verified_cleanup._scheduler_status_lock:
            verified_cleanup._scheduler_status.update(
                lastCycleAt=None, lastStatus=None, lastError=None
            )

    def test_scheduler_loop_retries_with_safe_telemetry_and_never_logs_the_exception(self):
        sentinel = "SENTINEL-PRIVATE-9f3c"
        calls, waits, observed = [], [], []

        def run_cycle():
            calls.append(len(calls))
            if len(calls) == 1:
                raise RuntimeError(sentinel)
            return {"status": "ok", "results": []}

        def wait(_event, timeout):
            waits.append(timeout)
            if len(waits) == 1:
                observed.append(verified_cleanup.get_verified_cleanup_scheduler_status())
            return len(waits) >= 2

        with self.assertLogs("verified_cleanup", level="WARNING") as captured:
            _verified_cleanup_scheduler_loop(300, object(), run_cycle, wait)

        final = verified_cleanup.get_verified_cleanup_scheduler_status()
        self.assertEqual(calls, [0, 1])
        self.assertEqual(waits, [300, 300])
        self.assertEqual(observed[0]["lastStatus"], "cleanup_cycle_failed")
        self.assertEqual(observed[0]["lastError"], "cleanup_cycle_failed")
        self.assertIsNotNone(observed[0]["lastCycleAt"])
        self.assertEqual(final["lastStatus"], "ok")
        self.assertIsNone(final["lastError"])
        self.assertIsNotNone(final["lastCycleAt"])
        transcript = json.dumps([observed[0], final]) + "\n" + "\n".join(captured.output)
        self.assertNotIn(sentinel, transcript)
        self.assertIn("cleanup_cycle_failed", "\n".join(captured.output))

    def test_scheduler_status_snapshot_is_locked_and_read_only(self):
        snapshot = verified_cleanup.get_verified_cleanup_scheduler_status()
        self.assertEqual(
            set(snapshot), {"running", "lastCycleAt", "lastStatus", "lastError"}
        )
        self.assertIsInstance(snapshot["running"], bool)
        snapshot["lastError"] = "mutated"
        self.assertIsNone(verified_cleanup.get_verified_cleanup_scheduler_status()["lastError"])

    def test_scheduler_loop_retries_after_invalid_result_status(self):
        calls = []
        seen = []

        def cycle():
            calls.append(len(calls))
            return {"status": ["ok"]} if len(calls) == 1 else {"status": "ok"}

        def wait(_event, _interval):
            seen.append(verified_cleanup.get_verified_cleanup_scheduler_status())
            return len(seen) == 2

        _verified_cleanup_scheduler_loop(300, object(), cycle, wait)
        self.assertEqual(calls, [0, 1])
        self.assertEqual(seen[0]["lastStatus"], "cleanup_cycle_failed")
        self.assertEqual(seen[0]["lastError"], "cleanup_cycle_failed")
        self.assertEqual(seen[1]["lastStatus"], "ok")
        self.assertIsNone(seen[1]["lastError"])

    def test_invalid_intervals_are_rejected_before_thread_creation(self):
        for value in (True, False, 0, -1, float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                with mock.patch.object(threading, "Thread") as thread_factory:
                    with self.assertRaises(ValueError):
                        start_verified_cleanup_scheduler(value)
                    thread_factory.assert_not_called()

    def test_default_interval_is_three_hundred_seconds(self):
        seen = {}

        def record_loop(interval_seconds, stop_event, run_cycle, wait):
            seen["interval"] = interval_seconds

        with mock.patch.object(
            verified_cleanup, "_verified_cleanup_scheduler_loop", side_effect=record_loop
        ):
            self.assertTrue(
                start_verified_cleanup_scheduler(run_cycle=lambda: {"status": "ok", "results": []})
            )
            self.assertTrue(stop_verified_cleanup_scheduler(timeout=2.0))

        self.assertEqual(seen["interval"], 300.0)

    def test_timed_out_stop_blocks_a_second_start_until_the_worker_exits(self):
        release = threading.Event()
        self.addCleanup(release.set)
        entered = threading.Event()
        workers = []

        def blocking_cycle():
            workers.append(threading.current_thread())
            entered.set()
            release.wait(5.0)
            return {"status": "ok", "results": []}

        self.assertTrue(start_verified_cleanup_scheduler(300, run_cycle=blocking_cycle))
        self.assertTrue(entered.wait(5.0))

        self.assertFalse(stop_verified_cleanup_scheduler(timeout=0.05))
        self.assertTrue(verified_cleanup.get_verified_cleanup_scheduler_status()["running"])
        self.assertFalse(
            start_verified_cleanup_scheduler(
                300, run_cycle=lambda: {"status": "ok", "results": []}
            )
        )

        release.set()
        workers[0].join(timeout=5.0)
        self.assertFalse(workers[0].is_alive())

        second_run = threading.Event()
        self.assertTrue(
            start_verified_cleanup_scheduler(
                300, run_cycle=lambda: second_run.set() or {"status": "ok", "results": []}
            )
        )
        self.assertTrue(second_run.wait(5.0))
        live_workers = [
            thread for thread in threading.enumerate() if thread.name == "verified-cleanup"
        ]
        self.assertEqual(len(live_workers), 1)
        self.assertTrue(live_workers[0].is_alive())
        self.assertTrue(stop_verified_cleanup_scheduler(timeout=5.0))


if __name__ == "__main__":
    unittest.main()
