"""Pure Hermes/discover helpers."""

def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _hermes_items(data):
    return [item for item in data.get("items", []) if item.get("source") == "hermes"]


def _normalize_tmdb_id(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _find_hermes_item(data, item_id):
    for item in data.get("items", []):
        if item.get("id") == item_id and item.get("source") == "hermes":
            return item
    return None


def _hermes_identity(item):
    return f"{item.get('type')}:{item.get('tmdb_id')}"
