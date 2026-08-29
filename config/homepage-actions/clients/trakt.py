"""Renewable, local-only Trakt OAuth client."""
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

TRAKT_USER_AGENT = "media-stack-dashboard/1.0"


class TraktAuthError(RuntimeError):
    """A safe authentication error suitable for a public API response."""

    def __init__(self, code="reconnect_required", message="Trakt reconnect required"):
        super().__init__(message)
        self.code = code


class TraktHttpError(RuntimeError):
    def __init__(self, status, *, payload=None, headers=None):
        self.status = status
        self.payload = payload if payload is not None else {}
        self.headers = dict(headers or {})
        super().__init__(
            "Trakt request unauthorized" if status == 401 else "Trakt request failed"
        )


@dataclass(frozen=True)
class TraktTokenState:
    access_token: str
    refresh_token: str
    expires_at: float
    created_at: float

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ValueError("invalid Trakt token state")
        values = [value.get(key) for key in ("access_token", "refresh_token")]
        if any(not isinstance(token, str) or not token for token in values):
            raise ValueError("invalid Trakt token state")
        try:
            expires_at = float(value["expires_at"])
            created_at = float(value["created_at"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("invalid Trakt token state") from None
        if expires_at <= 0 or created_at <= 0:
            raise ValueError("invalid Trakt token state")
        return cls(value["access_token"], value["refresh_token"], expires_at, created_at)

    def as_dict(self):
        return {
            "schema_version": 1,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
        }


class TraktTokenStore:
    """Load and atomically replace a single local token-state JSON file."""

    def __init__(self, path):
        self.path = os.fspath(path)

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as handle:
                return TraktTokenState.from_dict(json.load(handle))
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("invalid Trakt token state") from None
        except OSError as error:
            raise RuntimeError("Trakt temporarily unavailable") from error

    def replace(self, state):
        if not isinstance(state, TraktTokenState):
            state = TraktTokenState.from_dict(state)
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".trakt-token-", suffix=".tmp", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(state.as_dict(), handle, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    save = replace


@dataclass(frozen=True)
class _Response:
    status: int
    payload: object
    headers: object = None


def _urllib_transport(method, url, headers, body, timeout):
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return _Response(response.status, json.loads(raw) if raw else {}, dict(response.headers))
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8") if error.fp else ""
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        return _Response(error.code, payload, dict(error.headers))
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RuntimeError("Trakt temporarily unavailable") from error


class TraktClient:
    """Authenticated Trakt API client with single-use refresh-token protection."""

    _refresh_lock = threading.Lock()

    def __init__(
        self,
        client_id,
        client_secret="",
        token_path=None,
        transport=None,
        clock=None,
        timeout=10,
    ):
        self.client_id = client_id or ""
        self.client_secret = client_secret or ""
        self.token_store = TraktTokenStore(token_path) if token_path else None
        self.transport = transport or _urllib_transport
        self.clock = clock or time.time
        self.timeout = timeout

    def _call(self, method, url, headers, body=None):
        try:
            response = self.transport(method, url, headers, body, self.timeout)
        except TypeError:
            # Keep injection convenient for small tests and local adapters.
            response = self.transport(method, url, headers, body)
        if isinstance(response, _Response):
            return response
        if hasattr(response, "status") and hasattr(response, "payload"):
            return _Response(response.status, response.payload, getattr(response, "headers", None))
        if isinstance(response, tuple) and len(response) == 3:
            return _Response(int(response[0]), response[1], response[2])
        if isinstance(response, tuple) and len(response) == 2:
            return _Response(int(response[0]), response[1])
        raise RuntimeError("invalid Trakt transport response")

    def _state(self):
        if self.token_store:
            try:
                state = self.token_store.load()
            except ValueError as error:
                raise TraktAuthError() from error
            except OSError as error:
                raise RuntimeError("Trakt temporarily unavailable") from error
            if state:
                return state
        raise TraktAuthError()

    def _refresh_locked(self, state):
        if not state.refresh_token or not self.client_id or not self.client_secret:
            raise TraktAuthError()
        body = json.dumps(
            {
                "refresh_token": state.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        response = self._call(
            "POST",
            "https://auth.trakt.tv/oauth/token",
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": TRAKT_USER_AGENT,
            },
            body,
        )
        if response.status in (400, 401):
            raise TraktAuthError()
        if response.status >= 400 or not isinstance(response.payload, dict):
            raise RuntimeError("Trakt temporarily unavailable")
        access = response.payload.get("access_token")
        refresh = response.payload.get("refresh_token")
        expires_in = response.payload.get("expires_in")
        if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh:
            raise RuntimeError("Trakt temporarily unavailable")
        try:
            expires_at = self.clock() + float(expires_in)
        except (TypeError, ValueError):
            raise RuntimeError("Trakt temporarily unavailable") from None
        replacement = TraktTokenState(access, refresh, expires_at, self.clock())
        if self.token_store:
            self.token_store.replace(replacement)
        return replacement

    def _current_state(self, state):
        if state.expires_at - self.clock() >= 60:
            return state
        with self._refresh_lock:
            latest = self._state()
            if latest.expires_at - self.clock() >= 60:
                return latest
            return self._refresh_locked(latest)

    def _api_headers(self, state):
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": TRAKT_USER_AGENT,
            "trakt-api-version": "2",
            "trakt-api-key": self.client_id,
            "Authorization": "Bearer " + state.access_token,
        }

    def _request(self, method, path, state, body=None):
        response = self._call(
            method,
            "https://api.trakt.tv" + path,
            self._api_headers(state),
            body,
        )
        if response.status >= 400:
            raise TraktHttpError(
                response.status,
                payload=response.payload,
                headers=response.headers,
            )
        return response

    def _authorized_request(self, method, path, body=None):
        state = self._current_state(self._state())
        try:
            return self._request(method, path, state, body)
        except TraktHttpError as error:
            if error.status != 401:
                raise
        with self._refresh_lock:
            latest = self._state()
            if latest.access_token != state.access_token:
                state = latest
            else:
                state = self._refresh_locked(latest)
        try:
            return self._request(method, path, state, body)
        except TraktHttpError as error:
            if error.status == 401:
                raise TraktAuthError() from error
            raise

    def get_page(self, path):
        return self._authorized_request("GET", path)

    def get(self, path):
        return self.get_page(path).payload

    def post(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        return self._authorized_request("POST", path, body).payload


class TraktDeviceAuthorizer:
    """Run Trakt's one-time device flow without exposing token values."""

    def __init__(
        self,
        client_id,
        *,
        token_path,
        client_secret="",
        transport=None,
        clock=None,
        sleep=None,
        timeout=10,
    ):
        self.client_id = client_id or ""
        self.client_secret = client_secret or ""
        self.token_store = TraktTokenStore(token_path)
        self.transport = transport or _urllib_transport
        self.clock = clock or time.time
        self.sleep = sleep or time.sleep
        self.timeout = timeout

    def _call(self, method, url, body):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": TRAKT_USER_AGENT,
        }
        try:
            response = self.transport(method, url, headers, body, self.timeout)
        except TypeError:
            response = self.transport(method, url, headers, body)
        if isinstance(response, _Response):
            return response
        if isinstance(response, tuple) and len(response) == 2:
            return _Response(int(response[0]), response[1])
        if hasattr(response, "status") and hasattr(response, "payload"):
            return _Response(response.status, response.payload)
        raise RuntimeError("invalid Trakt transport response")

    def authorize(self, output=None):
        if not self.client_id or not self.client_secret:
            raise TraktAuthError("reconnect_required")
        response = self._call(
            "POST",
            "https://auth.trakt.tv/oauth/device/code",
            json.dumps({"client_id": self.client_id}).encode("utf-8"),
        )
        if response.status >= 400 or not isinstance(response.payload, dict):
            raise RuntimeError("Trakt device authorization temporarily unavailable")
        payload = response.payload
        try:
            device_code = payload["device_code"]
            user_code = payload["user_code"]
        except (KeyError, TypeError):
            raise RuntimeError("Trakt device authorization temporarily unavailable") from None
        # Accept Trakt's normal URL key and its alternate URI spelling.
        verification_url = payload.get("verification_url") or payload.get("verification_url_https")
        if not isinstance(verification_url, str) or not verification_url:
            raise RuntimeError("Trakt device authorization temporarily unavailable")
        try:
            deadline = self.clock() + float(payload["expires_in"])
            interval = max(1, int(payload.get("interval", 5)))
        except (KeyError, TypeError, ValueError):
            raise RuntimeError("Trakt device authorization temporarily unavailable") from None
        if output:
            output("Open " + verification_url)
            output("Enter device code " + str(user_code))
        while self.clock() < deadline:
            self.sleep(interval)
            poll = self._call(
                "POST",
                "https://auth.trakt.tv/oauth/device/token",
                json.dumps(
                    {"code": device_code, "client_id": self.client_id, "client_secret": self.client_secret}
                ).encode("utf-8"),
            )
            if poll.status == 200 and isinstance(poll.payload, dict):
                access = poll.payload.get("access_token")
                refresh = poll.payload.get("refresh_token")
                try:
                    expires_in = float(poll.payload["expires_in"])
                except (KeyError, TypeError, ValueError):
                    raise RuntimeError("Trakt device authorization temporarily unavailable") from None
                if isinstance(access, str) and access and isinstance(refresh, str) and refresh:
                    state = TraktTokenState(access, refresh, self.clock() + expires_in, self.clock())
                    self.token_store.replace(state)
                    return state
                raise RuntimeError("Trakt device authorization temporarily unavailable")
            if poll.status == 400:
                continue
            if poll.status == 429:
                interval += 5
                continue
            if poll.status in (404, 409, 410, 418):
                raise TraktAuthError("reconnect_required")
            raise RuntimeError("Trakt device authorization temporarily unavailable")
        raise TraktAuthError("reconnect_required")
