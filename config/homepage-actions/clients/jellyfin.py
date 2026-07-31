"""Jellyfin API client and library/watch-next data access."""
import json
import threading
import time
import urllib.parse
import urllib.request

import config as settings


def jellyfin_get(path, query=None):
    url = f"{settings.JELLYFIN_URL}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url)
    req.add_header("X-Emby-Token", settings.JELLYFIN_API_KEY)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=settings.TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _jellyfin_lock_for(item_type):
    with settings._jellyfin_cache_lock:
        lock = settings._jellyfin_locks.get(item_type)
        if lock is None:
            lock = threading.Lock()
            settings._jellyfin_locks[item_type] = lock
        return lock


def _jellyfin_image_url(item_id, image_tag=None):
    """Build a browser-facing Primary image URL.

    Do not append api_key: authenticated image requests fail when Jellyfin's
    auth/DB path is unhealthy, while anonymous Primary GETs still succeed.
    Optional tag= is only a cache-buster when ImageTags.Primary is known.
    """
    if not item_id:
        return None
    url = f"{settings.JELLYFIN_EXTERNAL_URL}/Items/{item_id}/Images/Primary"
    if image_tag:
        url += "?" + urllib.parse.urlencode({"tag": image_tag})
    return url


def _jellyfin_typed_image_url(item_id, image_type):
    """Browser-facing URL for non-Primary art (Backdrop/Thumb), same anonymous pattern."""
    if not item_id:
        return None
    return f"{settings.JELLYFIN_EXTERNAL_URL}/Items/{item_id}/Images/{image_type}"


def _jellyfin_user_id_for_queries():
    if settings.JELLYFIN_USER_ID:
        return settings.JELLYFIN_USER_ID
    with settings._jellyfin_user_id_lock:
        if settings._jellyfin_user_id:
            return settings._jellyfin_user_id
        users = jellyfin_get("/Users")
        for user in users:
            if user.get("Policy", {}).get("IsAdministrator"):
                settings._jellyfin_user_id = user["Id"]
                return settings._jellyfin_user_id
        if users:
            settings._jellyfin_user_id = users[0]["Id"]
        return settings._jellyfin_user_id


def _jellyfin_items_path():
    user_id = _jellyfin_user_id_for_queries()
    if user_id:
        return f"/Users/{user_id}/Items"
    return "/Items"


JELLYFIN_PAGE_SIZE = 100


def _jellyfin_item_is_playable(raw, item_type):
    if raw.get("IsPlaceHolder"):
        return False
    path = raw.get("Path")
    # Exclude JellyNext virtual-library stubs. Those are .strm recommendation /
    # "next season" entries that live under the plugin's jellynext-virtual tree
    # (Trakt recommendations), not media Fernando actually has. They carry a
    # real-looking Path and LocationType=FileSystem, so the only reliable signal
    # is the path itself. Keep genuine items whose Path is outside that tree.
    if path and "jellynext-virtual" in path:
        return False
    if item_type == "Movie":
        return bool(path)
    return True


def _fetch_all_jellyfin_raw(item_type):
    items = []
    start = 0
    while True:
        data = jellyfin_get(
            _jellyfin_items_path(),
            {
                "Recursive": "true",
                "IncludeItemTypes": item_type,
                "StartIndex": str(start),
                "Limit": str(JELLYFIN_PAGE_SIZE),
                "SortBy": "SortName",
                "SortOrder": "Ascending",
                "Fields": "ProductionYear,CommunityRating,PrimaryImageAspectRatio,Path,IsPlaceHolder,ImageTags",
            },
        )
        batch = [
            item for item in data.get("Items", [])
            if _jellyfin_item_is_playable(item, item_type)
        ]
        items.extend(batch)
        total = data.get("TotalRecordCount", len(items))
        start += len(data.get("Items", []))
        if not data.get("Items") or start >= total:
            break
    return items


def _series_episode_count(item_id):
    user_id = _jellyfin_user_id_for_queries()
    path = f"/Users/{user_id}/Items" if user_id else "/Items"
    try:
        episodes_data = jellyfin_get(
            path,
            {
                "ParentId": item_id,
                "Recursive": "true",
                "IncludeItemTypes": "Episode",
                "Limit": "0",
            },
        )
        return episodes_data.get("TotalRecordCount", 0)
    except Exception:
        return 0


def _map_jellyfin_item(raw, item_type):
    item_id = raw.get("Id")
    aspect = raw.get("PrimaryImageAspectRatio")
    rating = raw.get("CommunityRating")
    if isinstance(rating, bool) or not isinstance(rating, (int, float)) or not 0 <= rating <= 10:
        rating = None
    image_tags = raw.get("ImageTags") or {}
    primary_tag = image_tags.get("Primary")
    item_data = {
        "name": raw.get("Name", ""),
        "year": raw.get("ProductionYear"),
        "rating": rating,
        "id": item_id,
        "image": _jellyfin_image_url(item_id, primary_tag),
        "aspectRatio": aspect if aspect else (2 / 3),
    }
    if item_type == "Series":
        item_data["episodeCount"] = _series_episode_count(item_id)
    return item_data


def _dedupe_jellyfin_items(items, item_type):
    # Jellyfin can return the same title from multiple library paths (different IDs).
    seen = {}
    for item in items:
        key = (item["name"].strip().lower(), item.get("year"))
        existing = seen.get(key)
        if item_type == "Series":
            if existing is None or item.get("episodeCount", 0) > existing.get("episodeCount", 0):
                seen[key] = item
        elif existing is None:
            seen[key] = item
    return list(seen.values())


def _fetch_jellyfin_items(item_type):
    ret_items = [_map_jellyfin_item(raw, item_type) for raw in _fetch_all_jellyfin_raw(item_type)]
    ret_items = _dedupe_jellyfin_items(ret_items, item_type)

    if item_type == "Series":
        ret_items = [item for item in ret_items if item.get("episodeCount", 0) > 0]

    ret_items.sort(key=lambda item: item.get("name", "").lower())

    return {
        "ok": True,
        "total": len(ret_items),
        "items": ret_items,
    }


def _get_jellyfin_payload(item_type):
    now = time.monotonic()
    cached = settings._jellyfin_cache.get(item_type)
    if cached and now - cached["ts"] < settings.JELLYFIN_CACHE_TTL:
        return cached["payload"]

    lock = _jellyfin_lock_for(item_type)
    with lock:
        cached = settings._jellyfin_cache.get(item_type)
        if cached and now - cached["ts"] < settings.JELLYFIN_CACHE_TTL:
            return cached["payload"]

        payload = _fetch_jellyfin_items(item_type)
        settings._jellyfin_cache[item_type] = {"ts": time.monotonic(), "payload": payload}
        return payload


WATCH_NEXT_ITEM_LIMIT = 40
WATCH_NEXT_UNSTARTED_SERIES_LOOKUP_LIMIT = 60
WATCH_NEXT_FIELDS = (
    "UserData,RunTimeTicks,SeriesName,ParentId,SeasonId,IndexNumber,"
    "ParentIndexNumber,ImageTags,Path,SeriesId,MediaType,Type,Name,"
    "DateCreated,DateLastContentAdded,ProductionYear,CommunityRating,"
    "Genres,Overview,BackdropImageTags"
)


def _clamp_progress_percent(value):
    if not isinstance(value, (int, float)):
        return 0
    if value != value:
        return 0
    return max(0, min(100, int(round(value))))


def _progress_percent(user_data, runtime_ticks):
    user_data = user_data or {}
    if user_data.get("Played"):
        return None
    position = user_data.get("PlaybackPositionTicks") or 0
    if not isinstance(position, (int, float)):
        position = 0
    runtime = runtime_ticks or 0
    if not isinstance(runtime, (int, float)):
        runtime = 0
    if position <= 0:
        return 0
    if runtime <= 0:
        return 1
    return _clamp_progress_percent(position / runtime * 100)


def _watch_next_rating(raw):
    rating = raw.get("CommunityRating")
    if isinstance(rating, bool) or not isinstance(rating, (int, float)) or not 0 <= rating <= 10:
        return None
    return rating


def _watch_next_genres(raw):
    genres = raw.get("Genres")
    if not isinstance(genres, list):
        return []
    return [g.strip() for g in genres if isinstance(g, str) and g.strip()]


def _watch_next_ticks(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _watch_next_item_metadata(raw):
    """Hero/art metadata resolved from the item's own Jellyfin record."""
    item_id = raw.get("Id")
    image_tags = raw.get("ImageTags") or {}
    return {
        "year": raw.get("ProductionYear"),
        "rating": _watch_next_rating(raw),
        "genres": _watch_next_genres(raw),
        "overview": raw.get("Overview") or None,
        "runtimeTicks": _watch_next_ticks(raw.get("RunTimeTicks")),
        "positionTicks": _watch_next_ticks((raw.get("UserData") or {}).get("PlaybackPositionTicks")),
        "backdropUrl": (
            _jellyfin_typed_image_url(item_id, "Backdrop") if raw.get("BackdropImageTags") else None
        ),
        "thumbUrl": (
            _jellyfin_typed_image_url(item_id, "Thumb") if image_tags.get("Thumb") else None
        ),
    }


SERIES_METADATA_FIELDS = (
    "ProductionYear,CommunityRating,Genres,Overview,BackdropImageTags,ImageTags"
)


def _empty_series_metadata():
    return {
        "year": None,
        "rating": None,
        "genres": [],
        "overview": None,
        "backdropUrl": None,
        "thumbUrl": None,
    }


def _map_series_metadata(raw, series_id):
    image_tags = raw.get("ImageTags") or {}
    return {
        "year": raw.get("ProductionYear"),
        "rating": _watch_next_rating(raw),
        "genres": _watch_next_genres(raw),
        "overview": raw.get("Overview") or None,
        "backdropUrl": (
            _jellyfin_typed_image_url(series_id, "Backdrop")
            if raw.get("BackdropImageTags")
            else None
        ),
        "thumbUrl": (
            _jellyfin_typed_image_url(series_id, "Thumb") if image_tags.get("Thumb") else None
        ),
    }


def _get_series_metadata(series_id):
    """Cached /Items/{seriesId} metadata for episode hero art; never raises."""
    if not series_id:
        return _empty_series_metadata()
    cache_key = f"series-meta:{series_id}"
    now = time.monotonic()
    cached = settings._jellyfin_cache.get(cache_key)
    if cached and now - cached["ts"] < settings.JELLYFIN_CACHE_TTL:
        return cached["payload"]

    lock = _jellyfin_lock_for(cache_key)
    with lock:
        cached = settings._jellyfin_cache.get(cache_key)
        if cached and now - cached["ts"] < settings.JELLYFIN_CACHE_TTL:
            return cached["payload"]
        try:
            user_id = _jellyfin_user_id_for_queries()
            path = (
                f"/Users/{user_id}/Items/{series_id}"
                if user_id
                else f"/Items/{series_id}"
            )
            raw = jellyfin_get(path, {"Fields": SERIES_METADATA_FIELDS})
            payload = _map_series_metadata(raw, series_id)
        except Exception:
            payload = _empty_series_metadata()
        settings._jellyfin_cache[cache_key] = {"ts": time.monotonic(), "payload": payload}
        return payload


def _apply_series_metadata(item, meta):
    """Overlay series-level presentation fields onto an episode watch-next item."""
    if meta["year"] is not None:
        item["year"] = meta["year"]
    if meta["rating"] is not None:
        item["rating"] = meta["rating"]
    if meta["genres"]:
        item["genres"] = meta["genres"]
    if meta["overview"]:
        item["overview"] = meta["overview"]
    if meta["backdropUrl"]:
        item["backdropUrl"] = meta["backdropUrl"]
    if meta["thumbUrl"]:
        item["thumbUrl"] = meta["thumbUrl"]


def _format_episode_subtitle(raw):
    season = raw.get("ParentIndexNumber")
    episode = raw.get("IndexNumber")
    name = (raw.get("Name") or "").strip()
    if isinstance(season, int) and isinstance(episode, int):
        prefix = f"S{season:02d}E{episode:02d}"
        return f"{prefix} · {name}" if name else prefix
    return name


def _watch_next_image(raw):
    item_type = raw.get("Type") or ""
    series_id = raw.get("SeriesId")
    if item_type == "Episode" and series_id:
        return _jellyfin_image_url(series_id)
    item_id = raw.get("Id")
    image_tags = raw.get("ImageTags") or {}
    primary_tag = image_tags.get("Primary")
    if primary_tag and item_id:
        return _jellyfin_image_url(item_id, primary_tag)
    if series_id:
        return _jellyfin_image_url(series_id)
    return None


def _jellyfin_media_kind(raw):
    item_type = raw.get("Type") or ""
    if item_type == "Movie":
        return "movie"
    if item_type == "Episode":
        return "episode"
    return None


def _map_watch_next_item(raw, force_progress=None):
    kind = _jellyfin_media_kind(raw)
    if kind == "movie":
        if not _jellyfin_item_is_playable(raw, "Movie"):
            return None
    elif kind == "episode":
        if not _jellyfin_item_is_playable(raw, "Episode"):
            return None
    else:
        return None

    if force_progress is not None:
        progress = _clamp_progress_percent(force_progress)
    else:
        progress = _progress_percent(raw.get("UserData"), raw.get("RunTimeTicks"))
    if progress is None:
        return None

    item_id = raw.get("Id")
    if not item_id:
        return None

    last_played = (raw.get("UserData") or {}).get("LastPlayedDate") or ""
    sort_date = raw.get("DateLastContentAdded") or raw.get("DateCreated") or ""

    if kind == "movie":
        title = (raw.get("Name") or "").strip()
        if not title:
            return None
        return {
            "id": item_id,
            "parentId": None,
            "title": title,
            "subtitle": "",
            "kind": "movie",
            "image": _watch_next_image(raw),
            "playable": True,
            "progressPercent": progress,
            **_watch_next_item_metadata(raw),
            "_sort_last_played": last_played,
            "_sort_date": sort_date,
        }

    series_id = raw.get("SeriesId")
    title = (raw.get("SeriesName") or "").strip()
    if not series_id or not title:
        return None
    return {
        "id": item_id,
        "parentId": series_id,
        "title": title,
        "subtitle": _format_episode_subtitle(raw),
        "kind": "episode",
        "image": _watch_next_image(raw),
        "playable": True,
        "progressPercent": progress,
        **_watch_next_item_metadata(raw),
        "_sort_last_played": last_played,
        "_sort_date": sort_date,
        "_series_id": series_id,
    }


def _watch_next_sort_date(raw):
    return raw.get("DateLastContentAdded") or raw.get("DateCreated") or ""


def _apply_watch_next_sort_date(item, sort_date):
    if sort_date:
        item["_sort_date"] = sort_date
    elif "_sort_date" not in item:
        item["_sort_date"] = ""


def _sort_watch_next_items(items):
    items.sort(key=lambda item: item["title"].lower())
    items.sort(key=lambda item: item.get("_sort_date") or "", reverse=True)
    items.sort(key=lambda item: 0 if item["progressPercent"] > 0 else 1)


def _strip_watch_next_sort_keys(item):
    return {key: value for key, value in item.items() if not key.startswith("_")}


def _fetch_jellyfin_resume_raw():
    user_id = _jellyfin_user_id_for_queries()
    if not user_id:
        return []
    data = jellyfin_get(
        f"/Users/{user_id}/Items/Resume",
        {
            "Recursive": "true",
            "MediaTypes": "Video",
            "Fields": WATCH_NEXT_FIELDS,
            "Limit": str(JELLYFIN_PAGE_SIZE),
        },
    )
    return data.get("Items", [])


def _fetch_jellyfin_next_up_raw():
    user_id = _jellyfin_user_id_for_queries()
    if not user_id:
        return []
    data = jellyfin_get(
        "/Shows/NextUp",
        {
            "UserId": user_id,
            "Fields": WATCH_NEXT_FIELDS,
            "Limit": str(JELLYFIN_PAGE_SIZE),
        },
    )
    return data.get("Items", [])


def _fetch_jellyfin_unwatched_movies_raw():
    user_id = _jellyfin_user_id_for_queries()
    if not user_id:
        return []
    items = []
    start = 0
    while True:
        data = jellyfin_get(
            _jellyfin_items_path(),
            {
                "Recursive": "true",
                "IncludeItemTypes": "Movie",
                "Filters": "IsUnplayed",
                "StartIndex": str(start),
                "Limit": str(JELLYFIN_PAGE_SIZE),
                "SortBy": "DateCreated",
                "SortOrder": "Descending",
                "Fields": WATCH_NEXT_FIELDS,
            },
        )
        batch = [
            item for item in data.get("Items", [])
            if _jellyfin_item_is_playable(item, "Movie")
        ]
        items.extend(batch)
        total = data.get("TotalRecordCount", len(items))
        start += len(data.get("Items", []))
        if not data.get("Items") or start >= total:
            break
    return items


def _fetch_jellyfin_unplayed_series_raw():
    user_id = _jellyfin_user_id_for_queries()
    if not user_id:
        return []
    items = []
    start = 0
    while True:
        data = jellyfin_get(
            _jellyfin_items_path(),
            {
                "Recursive": "true",
                "IncludeItemTypes": "Series",
                "Filters": "IsUnplayed",
                "StartIndex": str(start),
                "Limit": str(JELLYFIN_PAGE_SIZE),
                "SortBy": "DateCreated",
                "SortOrder": "Descending",
                "Fields": WATCH_NEXT_FIELDS,
            },
        )
        items.extend(data.get("Items", []))
        total = data.get("TotalRecordCount", len(items))
        start += len(data.get("Items", []))
        if not data.get("Items") or start >= total:
            break
    return items


def _fetch_first_playable_episode_for_series(series_id):
    data = jellyfin_get(
        _jellyfin_items_path(),
        {
            "ParentId": series_id,
            "Recursive": "true",
            "IncludeItemTypes": "Episode",
            "SortBy": "ParentIndexNumber,IndexNumber",
            "SortOrder": "Ascending",
            "Fields": WATCH_NEXT_FIELDS,
            "Limit": "25",
        },
    )
    for raw in data.get("Items", []):
        if _jellyfin_item_is_playable(raw, "Episode"):
            return raw
    return None


def _merge_watch_next_episode(existing, candidate):
    if existing is None:
        return candidate
    if candidate["progressPercent"] > existing["progressPercent"]:
        return candidate
    if candidate["progressPercent"] < existing["progressPercent"]:
        return existing
    if candidate.get("_sort_last_played", "") > existing.get("_sort_last_played", ""):
        return candidate
    return existing


def _fetch_watch_next_items():
    episodes_by_series = {}
    movies = []

    for raw in _fetch_jellyfin_resume_raw():
        mapped = _map_watch_next_item(raw)
        if not mapped:
            continue
        if mapped["kind"] == "movie":
            if mapped["progressPercent"] > 0:
                movies.append(mapped)
            continue
        series_id = mapped.get("_series_id")
        if series_id:
            episodes_by_series[series_id] = _merge_watch_next_episode(
                episodes_by_series.get(series_id),
                mapped,
            )

    for raw in _fetch_jellyfin_next_up_raw():
        series_id = raw.get("SeriesId")
        if not series_id or series_id in episodes_by_series:
            continue
        mapped = _map_watch_next_item(raw, force_progress=0)
        if not mapped or mapped["kind"] != "episode":
            continue
        episodes_by_series[series_id] = mapped

    movie_ids = {movie["id"] for movie in movies}
    for raw in _fetch_jellyfin_unwatched_movies_raw():
        item_id = raw.get("Id")
        if not item_id or item_id in movie_ids:
            continue
        mapped = _map_watch_next_item(raw, force_progress=0)
        if not mapped or mapped["kind"] != "movie":
            continue
        movies.append(mapped)
        movie_ids.add(item_id)

    series_lookups = 0
    for series_raw in _fetch_jellyfin_unplayed_series_raw():
        if series_lookups >= WATCH_NEXT_UNSTARTED_SERIES_LOOKUP_LIMIT:
            break
        series_id = series_raw.get("Id")
        if not series_id or series_id in episodes_by_series:
            continue
        series_lookups += 1
        episode_raw = _fetch_first_playable_episode_for_series(series_id)
        if not episode_raw:
            continue
        mapped = _map_watch_next_item(episode_raw, force_progress=0)
        if not mapped or mapped["kind"] != "episode":
            continue
        _apply_watch_next_sort_date(mapped, _watch_next_sort_date(series_raw))
        episodes_by_series[series_id] = mapped
        if len(movies) + len(episodes_by_series) >= WATCH_NEXT_ITEM_LIMIT:
            break

    items = movies + list(episodes_by_series.values())
    _sort_watch_next_items(items)
    items = items[:WATCH_NEXT_ITEM_LIMIT]
    for item in items:
        if item["kind"] == "episode":
            _apply_series_metadata(item, _get_series_metadata(item["_series_id"]))
    return {"ok": True, "items": [_strip_watch_next_sort_keys(item) for item in items]}


def _get_watch_next_payload():
    cache_key = "watch-next"
    now = time.monotonic()
    cached = settings._jellyfin_cache.get(cache_key)
    if cached and now - cached["ts"] < settings.JELLYFIN_CACHE_TTL:
        return cached["payload"]

    lock = _jellyfin_lock_for(cache_key)
    with lock:
        cached = settings._jellyfin_cache.get(cache_key)
        if cached and now - cached["ts"] < settings.JELLYFIN_CACHE_TTL:
            return cached["payload"]

        payload = _fetch_watch_next_items()
        settings._jellyfin_cache[cache_key] = {"ts": time.monotonic(), "payload": payload}
        return payload

def jellyfin_post(path, query=None, method="POST"):
    url = f"{settings.JELLYFIN_URL}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, method=method)
    req.add_header("X-Emby-Token", settings.JELLYFIN_API_KEY)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=settings.TIMEOUT) as resp:
        if resp.status == 204:
            return {}
        body = resp.read()
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))
