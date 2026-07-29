"""qBittorrent Web API client."""
import json
import urllib.error
import urllib.parse
import urllib.request

import config as settings

def _qbt_request(url, data=None, method="GET", opener=None):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Referer", f"{settings.QBT_URL}/")
    if data is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    if opener:
        return opener.open(req, timeout=settings.TIMEOUT)
    return urllib.request.urlopen(req, timeout=settings.TIMEOUT)


def qbt_login(opener):
    """Authenticate with the qBittorrent WebAPI and store the session cookie."""
    data = urllib.parse.urlencode(
        {"username": settings.QBT_USERNAME, "password": settings.QBT_PASSWORD}
    ).encode("utf-8")
    with _qbt_request(
        f"{settings.QBT_URL}/api/v2/auth/login", data=data, method="POST", opener=opener
    ) as resp:
        body = resp.read().decode("utf-8", errors="ignore").strip()
        if resp.status < 200 or resp.status >= 300:
            raise RuntimeError(f"qBittorrent login failed: HTTP {resp.status} {body}")
        if body == "Fails.":
            raise RuntimeError("qBittorrent login failed: invalid credentials")
        if body not in ("Ok.", ""):
            raise RuntimeError(
                f"qBittorrent login failed: unexpected login response ({body})"
            )
        if body == "":
            try:
                with _qbt_request(
                    f"{settings.QBT_URL}/api/v2/app/version", method="GET", opener=opener
                ) as ver_resp:
                    ver_resp.read()
            except Exception as exc:
                raise RuntimeError(
                    "qBittorrent login failed: invalid credentials (empty response)"
                ) from exc


def qbt_post(path, params, opener):
    """POST to the qBittorrent WebAPI, logging in first if the session expired."""
    data = urllib.parse.urlencode(params).encode("utf-8")
    url = f"{settings.QBT_URL}{path}"
    try:
        with _qbt_request(url, data=data, method="POST", opener=opener) as resp:
            return resp.status, resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            qbt_login(opener)
            with _qbt_request(url, data=data, method="POST", opener=opener) as resp:
                return resp.status, resp.read().decode("utf-8", errors="ignore")
        raise


def qbt_get_json(path, opener, query=None):
    """GET JSON from the qBittorrent WebAPI, logging in first if needed."""
    url = f"{settings.QBT_URL}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)

    try:
        with _qbt_request(url, method="GET", opener=opener) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            qbt_login(opener)
            with _qbt_request(url, method="GET", opener=opener) as resp:
                return json.loads(resp.read().decode("utf-8"))
        raise
