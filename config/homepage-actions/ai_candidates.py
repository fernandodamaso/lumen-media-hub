#!/usr/bin/env python3
"""Build the private, verified candidate snapshot consumed by the AI worker."""

import copy


class CandidateUnavailable(Exception):
    """Authoritative exclusions or all candidate sources are unavailable."""

    def __init__(self, message, code="candidate_unavailable"):
        super().__init__(message)
        self.code = code


def _identity(item):
    item_type = item.get("type")
    tmdb_id = item.get("tmdb_id")
    if item_type not in ("movie", "tv"):
        return None
    if isinstance(tmdb_id, bool) or not isinstance(tmdb_id, int) or tmdb_id <= 0:
        return None
    if not isinstance(item.get("title"), str) or not item["title"].strip():
        return None
    return f"{item_type}:{tmdb_id}"


def build_candidate_snapshot(doc, *, sources, exclusions, cap=100):
    """Merge provider results after server-side never-twice/exclusion checks."""
    exclusion = exclusions(doc)
    if not isinstance(exclusion, dict) or exclusion.get("errors"):
        raise CandidateUnavailable("authoritative exclusion snapshot unavailable")

    denied = set(doc.get("presented_media_ids", ()))
    denied.update(exclusion.get("tracked", ()))
    denied.update(exclusion.get("in_library", ()))
    denied.update(exclusion.get("watched", ()))

    merged = []
    usable_source = False
    for source in sources:
        try:
            values = source()
        except Exception:
            continue
        if not isinstance(values, list):
            continue
        usable_source = True
        merged.extend(values)
    if not usable_source:
        raise CandidateUnavailable("candidate sources unavailable")

    candidates = []
    seen = set()
    for raw in merged:
        if not isinstance(raw, dict):
            continue
        identity = _identity(raw)
        legacy_identity = f"legacy:{raw.get('tmdb_id')}"
        if (
            identity is None
            or identity in seen
            or identity in denied
            or legacy_identity in denied
        ):
            continue
        candidate = {
            key: copy.deepcopy(raw.get(key))
            for key in (
                "type", "title", "year", "tmdb_id", "overview", "rating",
                "poster_path", "poster_url", "in_library", "jellyfin_id",
            )
            if key in raw
        }
        candidate["identity"] = identity
        signals = raw.get("signals")
        candidate["signals"] = list(signals) if isinstance(signals, list) else []
        candidates.append(candidate)
        seen.add(identity)
        if len(candidates) >= cap:
            break

    if not candidates:
        raise CandidateUnavailable("eligible candidate pool is empty", "empty_pool")
    return {
        "candidates": candidates,
        "taste": copy.deepcopy(exclusion.get("taste", {})),
        "required_retain": copy.deepcopy(exclusion.get("required_retain", [])),
    }
