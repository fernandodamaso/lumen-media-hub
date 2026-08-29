"""Pure AI Picks/discover helpers."""

def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _ai_picks_items(data):
    return [item for item in data.get("items", []) if item.get("source") == "ai"]


def _normalize_tmdb_id(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _find_ai_picks_item(data, item_id):
    for item in data.get("items", []):
        if item.get("id") == item_id and item.get("source") == "ai":
            return item
    return None


def _ai_picks_identity(item):
    return f"{item.get('type')}:{item.get('tmdb_id')}"
