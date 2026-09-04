"""Safe, local Trakt device authorization for the Linux installer."""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dotenv import DotEnvDocument
from .errors import ExitCode, InstallerError, InvalidInputError


TRAKT_USER_AGENT = "lumen-media-hub-installer/1.0"
DEVICE_CODE_URL = "https://auth.trakt.tv/oauth/device/code"
DEVICE_TOKEN_URL = "https://auth.trakt.tv/oauth/device/token"
TERMINAL_DEVICE_STATUSES = frozenset({404, 409, 410, 418})


@dataclass(frozen=True, repr=False)
class TraktTokenState:
    """The renewable token state stored on the host."""

    access_token: str
    refresh_token: str
    expires_at: float
    created_at: float

    @classmethod
    def from_dict(cls, value: Any) -> "TraktTokenState":
        if not isinstance(value, Mapping) or value.get("schema_version") != 1:
            raise ValueError("invalid Trakt token state")

        access_token = value.get("access_token")
        refresh_token = value.get("refresh_token")
        if (
            not isinstance(access_token, str)
            or not access_token
            or not isinstance(refresh_token, str)
            or not refresh_token
        ):
            raise ValueError("invalid Trakt token state")

        try:
            expires_at = float(value["expires_at"])
            created_at = float(value["created_at"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("invalid Trakt token state") from None
        if not math.isfinite(expires_at) or not math.isfinite(created_at):
            raise ValueError("invalid Trakt token state")
        if expires_at <= 0 or created_at <= 0:
            raise ValueError("invalid Trakt token state")
        return cls(access_token, refresh_token, expires_at, created_at)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
        }

    def __repr__(self) -> str:
        return (
            "TraktTokenState(access_token='<redacted>', "
            "refresh_token='<redacted>', "
            f"expires_at={self.expires_at!r}, created_at={self.created_at!r})"
        )


class TraktTokenStore:
    """Read and atomically replace a local Trakt token-state file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> TraktTokenState | None:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid Trakt token state") from exc
        return TraktTokenState.from_dict(value)

    def replace(self, state: TraktTokenState | Mapping[str, Any]) -> None:
        if not isinstance(state, TraktTokenState):
            state = TraktTokenState.from_dict(state)

        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(parent),
        )
        temporary = Path(temporary_name)
        replaced = False
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                descriptor = -1
                json.dump(state.as_dict(), handle, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temporary), str(self.path))
            replaced = True
            try:
                directory_descriptor = os.open(
                    str(parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                )
            except OSError:
                directory_descriptor = -1
            if directory_descriptor >= 0:
                try:
                    os.fsync(directory_descriptor)
                except OSError:
                    pass
                finally:
                    os.close(directory_descriptor)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if not replaced:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass

    save = replace


class TraktAuthorizationError(InvalidInputError):
    """A safe authorization failure that requires another device flow."""

    def __init__(
        self,
        status: int | str | None = None,
        code: str = "reconnect_required",
        message: str = "Trakt reconnect required",
    ) -> None:
        # Accept the compact ``TraktAuthorizationError("reconnect_required")``
        # form used by the service-side implementation without exposing it in
        # a user-facing message.
        if isinstance(status, str) and code == "reconnect_required":
            code = status
            status = None
        self.status = status if isinstance(status, int) else None
        self.code = code if code else "reconnect_required"
        super().__init__(message)


@dataclass(frozen=True)
class _TraktResponse:
    status: int
    payload: Any


def _json_payload(raw: bytes) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _response_status(response: Any) -> int:
    status = getattr(response, "status", None)
    if status is None:
        status = response.getcode()
    return int(status)


def _urllib_transport(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes,
    timeout: float = 10,
) -> _TraktResponse:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _TraktResponse(
                _response_status(response),
                _json_payload(response.read()),
            )
    except urllib.error.HTTPError as error:
        raw = error.read() if error.fp else b""
        return _TraktResponse(int(error.code), _json_payload(raw))
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise InvalidInputError("Trakt authorization request failed") from exc


def _response(value: Any) -> _TraktResponse:
    if isinstance(value, _TraktResponse):
        return value
    if isinstance(value, tuple) and len(value) == 2:
        try:
            return _TraktResponse(int(value[0]), value[1])
        except (TypeError, ValueError) as exc:
            raise InvalidInputError("Trakt authorization returned an invalid response") from exc
    status = getattr(value, "status", None)
    payload = getattr(value, "payload", None)
    if status is not None and hasattr(value, "payload"):
        try:
            return _TraktResponse(int(status), payload)
        except (TypeError, ValueError) as exc:
            raise InvalidInputError("Trakt authorization returned an invalid response") from exc
    raise InvalidInputError("Trakt authorization returned an invalid response")


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


class TraktDeviceAuthorizer:
    """Run Trakt's one-time device flow without exposing credential values."""

    def __init__(
        self,
        client_id: str,
        *,
        token_path: str | Path,
        client_secret: str = "",
        transport: Callable[..., Any] | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], Any] | None = None,
        timeout: float = 10,
    ) -> None:
        self.client_id = client_id if isinstance(client_id, str) else ""
        self.client_secret = client_secret if isinstance(client_secret, str) else ""
        self.token_store = TraktTokenStore(token_path)
        self.transport = transport or _urllib_transport
        self.clock = clock or time.time
        self.sleep = sleep or time.sleep
        self.timeout = timeout

    def _call(self, method: str, url: str, payload: Mapping[str, Any]) -> _TraktResponse:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": TRAKT_USER_AGENT,
        }
        body = json.dumps(dict(payload), separators=(",", ":")).encode("utf-8")
        try:
            try:
                result = self.transport(method, url, headers, body, self.timeout)
            except TypeError:
                # The small four-argument transport is convenient for tests
                # and remains the public injection shape.
                result = self.transport(method, url, headers, body)
            return _response(result)
        except InvalidInputError:
            raise
        except (OSError, urllib.error.URLError, TimeoutError, ValueError, TypeError) as exc:
            raise InvalidInputError("Trakt authorization request failed") from exc

    def authorize(self, output: Callable[[str], Any] | None = None) -> TraktTokenState:
        if not self.client_id or not self.client_secret:
            raise TraktAuthorizationError()

        device = self._call("POST", DEVICE_CODE_URL, {"client_id": self.client_id})
        if device.status < 200 or device.status >= 300 or not isinstance(device.payload, Mapping):
            raise InvalidInputError("Trakt device authorization could not start")

        device_code = device.payload.get("device_code")
        user_code = device.payload.get("user_code")
        verification_url = device.payload.get("verification_url") or device.payload.get(
            "verification_url_https"
        )
        if (
            not _nonempty_text(device_code)
            or not _nonempty_text(user_code)
            or not _nonempty_text(verification_url)
        ):
            raise InvalidInputError("Trakt device authorization returned an invalid response")
        try:
            expires_in = float(device.payload["expires_in"])
            interval = max(1, int(device.payload.get("interval", 5)))
        except (KeyError, TypeError, ValueError):
            raise InvalidInputError("Trakt device authorization returned an invalid response") from None
        if not math.isfinite(expires_in) or expires_in <= 0:
            raise InvalidInputError("Trakt device authorization returned an invalid response")

        if output is not None:
            output(f"Open {verification_url}")
            output(f"Enter device code {user_code}")

        deadline = self.clock() + expires_in
        while self.clock() < deadline:
            self.sleep(interval)
            poll = self._call(
                "POST",
                DEVICE_TOKEN_URL,
                {
                    "code": device_code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            if poll.status == 200:
                if not isinstance(poll.payload, Mapping):
                    raise InvalidInputError("Trakt authorization returned an invalid response")
                access_token = poll.payload.get("access_token")
                refresh_token = poll.payload.get("refresh_token")
                if not _nonempty_text(access_token) or not _nonempty_text(refresh_token):
                    raise InvalidInputError("Trakt authorization returned an invalid response")
                try:
                    token_expires_in = float(poll.payload["expires_in"])
                except (KeyError, TypeError, ValueError):
                    raise InvalidInputError("Trakt authorization returned an invalid response") from None
                if not math.isfinite(token_expires_in) or token_expires_in <= 0:
                    raise InvalidInputError("Trakt authorization returned an invalid response")
                created_at = self.clock()
                state = TraktTokenState(
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_at=created_at + token_expires_in,
                    created_at=created_at,
                )
                self.token_store.replace(state)
                return state
            if poll.status == 400:
                continue
            if poll.status == 429:
                interval += 5
                continue
            if poll.status in TERMINAL_DEVICE_STATUSES:
                raise TraktAuthorizationError(status=poll.status)
            raise InvalidInputError("Trakt authorization failed")

        raise TraktAuthorizationError()


def _environment_from_file(
    env_file: Path,
    environment: Mapping[str, Any] | None,
) -> dict[str, str]:
    values: dict[str, str] = {}
    if env_file.exists():
        try:
            values.update(
                {
                    key: str(value)
                    for key, value in DotEnvDocument.parse(env_file).values.items()
                    if value is not None
                }
            )
        except (OSError, UnicodeError, ValueError) as exc:
            raise InvalidInputError("could not read .env") from exc
    values.update({key: str(value) for key, value in os.environ.items()})
    if environment is not None:
        values.update({str(key): str(value) for key, value in environment.items()})
    return values


def _expanded_path(value: str) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(value)))


def resolve_token_path(root: str | Path, environment: Mapping[str, Any]) -> Path:
    """Resolve the container token path onto the configured host state root."""

    host_root = Path(root)
    state_value = str(environment.get("TRAKT_STATE_PATH") or "./.state/trakt")
    state_root = _expanded_path(state_value)
    if not state_root.is_absolute():
        state_root = host_root / state_root

    token_value = str(environment.get("TRAKT_TOKEN_PATH") or "/state/trakt-token.json")
    token_value = os.path.expanduser(os.path.expandvars(token_value))
    if token_value == "/state":
        return state_root
    if token_value.startswith("/state/"):
        return state_root / token_value[len("/state/") :]
    token_path = Path(token_value)
    if token_path.is_absolute():
        return token_path
    return state_root / token_path


@dataclass(frozen=True)
class TraktWarmupResult:
    status: str

    @property
    def report(self) -> dict[str, str]:
        return {"status": self.status}


@dataclass(frozen=True)
class TraktConnectResult:
    status: str
    dry_run: bool
    report: dict[str, Any]
    exit_code: int
    warmup: TraktWarmupResult


def _default_warmup() -> None:
    """Best-effort cache warmup; authorization remains successful if it fails."""

    for media_type in ("movies", "shows"):
        query = urllib.parse.urlencode({"type": media_type, "refresh_watched": "true"})
        request = urllib.request.Request(
            f"http://127.0.0.1:8085/discover/trakt?{query}",
            headers={"Accept": "application/json", "User-Agent": TRAKT_USER_AGENT},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                if _response_status(response) != 200:
                    raise OSError("warmup returned non-success")
                response.read()
        except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise InvalidInputError("Trakt warmup failed") from exc


def _failed_result(
    *,
    token_path: Path,
    dry_run: bool,
    error: InstallerError,
) -> TraktConnectResult:
    report: dict[str, Any] = {
        "status": "failed",
        "token_path": str(token_path),
        "reason": "authorization_failed",
    }
    if isinstance(error, TraktAuthorizationError):
        report["code"] = error.code
        if error.status is not None:
            report["http_status"] = error.status
    return TraktConnectResult(
        status="failed",
        dry_run=dry_run,
        report=report,
        exit_code=int(error.exit_code),
        warmup=TraktWarmupResult("skipped"),
    )


def run_connect_trakt(
    root: str | Path | None = None,
    *,
    env_file: str | Path | None = None,
    environment: Mapping[str, Any] | None = None,
    token_path: str | Path | None = None,
    transport: Callable[..., Any] | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], Any] | None = None,
    warmup: Callable[[], Any] | None = None,
    dry_run: bool = False,
) -> TraktConnectResult:
    """Load local credentials and run an explicit Trakt reconnect flow."""

    host_root = Path(root) if root is not None else Path.cwd()
    environment_path = Path(env_file) if env_file is not None else host_root / ".env"
    values = _environment_from_file(environment_path, environment)
    resolved_token_path = Path(token_path) if token_path is not None else resolve_token_path(host_root, values)

    client_id = values.get("TRAKT_CLIENT_ID", "")
    client_secret = values.get("TRAKT_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        error = InvalidInputError("Set Trakt client credentials in .env before connecting")
        return _failed_result(token_path=resolved_token_path, dry_run=dry_run, error=error)

    if dry_run:
        result = TraktWarmupResult("skipped")
        return TraktConnectResult(
            status="dry-run",
            dry_run=True,
            report={
                "status": "dry-run",
                "token_path": str(resolved_token_path),
                "warmup": result.report,
            },
            exit_code=int(ExitCode.OK),
            warmup=result,
        )

    try:
        TraktDeviceAuthorizer(
            client_id,
            client_secret=client_secret,
            token_path=resolved_token_path,
            transport=transport,
            clock=clock,
            sleep=sleep,
        ).authorize(output=print)
    except InstallerError as error:
        return _failed_result(token_path=resolved_token_path, dry_run=False, error=error)
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        safe_error = InvalidInputError("Trakt authorization failed")
        return _failed_result(token_path=resolved_token_path, dry_run=False, error=safe_error)

    warmup_result = TraktWarmupResult("skipped")
    warmup_callable = warmup or _default_warmup
    try:
        warmup_callable()
    except Exception:
        warmup_result = TraktWarmupResult("failed")
    else:
        warmup_result = TraktWarmupResult("ok")

    return TraktConnectResult(
        status="ok",
        dry_run=False,
        report={
            "status": "ok",
            "token_path": str(resolved_token_path),
            "warmup": warmup_result.report,
        },
        exit_code=int(ExitCode.OK),
        warmup=warmup_result,
    )


__all__ = [
    "TERMINAL_DEVICE_STATUSES",
    "TraktAuthorizationError",
    "TraktConnectResult",
    "TraktDeviceAuthorizer",
    "TraktTokenState",
    "TraktTokenStore",
    "TraktWarmupResult",
    "resolve_token_path",
    "run_connect_trakt",
]
