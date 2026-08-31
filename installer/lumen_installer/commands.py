"""Safe, injectable command execution for the Linux installer.

The installer deliberately keeps process execution in one small module.  All
callers provide an argument vector; there is no shell interpolation or shell
pipeline escape hatch.  A command result retains its raw streams for trusted
parsers, while its public report and typed failures are redacted.
"""

from __future__ import annotations

import inspect
import math
import queue
import subprocess
import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .errors import InvalidInputError


REDACTED = "<redacted>"
DEFAULT_TIMEOUT = 30.0


class CommandExecutor(Protocol):
    """Protocol for injected command executors.

    Implementations receive the same bounded timeout used by
    :class:`CommandRunner`.  The runner still accepts legacy one-argument
    test seams by inspecting their signature before invocation.
    """

    def __call__(
        self,
        argv: Sequence[str],
        *,
        input_text: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> Any:
        ...


def _redaction_values(redact: Iterable[Any] | Any) -> tuple[str, ...]:
    """Normalize configured secret values, omitting empty values safely."""

    if redact is None:
        return ()
    if isinstance(redact, (str, bytes)):
        values: Iterable[Any] = (redact,)
    else:
        try:
            values = redact
            iter(values)
        except TypeError:
            values = (redact,)
    normalized: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)
        if text:
            normalized.add(text)
    # Replacing longest values first prevents a shorter credential from
    # exposing the remainder of a longer credential in a report.
    return tuple(sorted(normalized, key=lambda value: (-len(value), value)))


def redact_text(value: Any, redact: Iterable[Any] | Any = ()) -> str:
    """Return text with every configured secret value replaced."""

    text = "" if value is None else str(value)
    for secret in _redaction_values(redact):
        text = text.replace(secret, REDACTED)
    return text


def normalize_stream(value: Any, *, name: str = "stream", strict: bool = True) -> str:
    """Normalize subprocess streams to UTF-8 text with replacement decoding."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if strict:
        raise ValueError(f"unexpected {name} type: {type(value).__name__}")
    return str(value)


def _redact_argv(argv: Sequence[str], secrets: tuple[str, ...]) -> list[str]:
    return [redact_text(item, secrets) for item in argv]


@dataclass(frozen=True)
class CommandResult:
    """Completed process data with an intentionally redacted report view."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    _redact: tuple[str, ...] = ()

    @property
    def output(self) -> str:
        return self.stdout

    @property
    def report(self) -> dict[str, Any]:
        return {
            "argv": _redact_argv(self.argv, self._redact),
            "returncode": self.returncode,
            "stdout": redact_text(self.stdout, self._redact),
            "stderr": redact_text(self.stderr, self._redact),
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    def __repr__(self) -> str:
        return (
            f"CommandResult(argv={_redact_argv(self.argv, self._redact)!r}, "
            f"returncode={self.returncode!r})"
        )


class CommandExecutionError(InvalidInputError):
    """A process could not be executed or completed successfully."""

    def __init__(
        self,
        message: str,
        *,
        argv: Sequence[str],
        returncode: int | None = None,
        stdout: Any = "",
        stderr: Any = "",
        redact: Iterable[Any] | Any = (),
        timed_out: bool = False,
        timeout: float | None = None,
    ) -> None:
        self._redact = _redaction_values(redact)
        self.argv = tuple(str(item) for item in argv)
        self.returncode = returncode
        self.stdout = normalize_stream(stdout, name="stdout", strict=False)
        self.stderr = normalize_stream(stderr, name="stderr", strict=False)
        self._raw_message = str(message)
        self.timed_out = timed_out
        self.timeout = timeout
        safe_message = redact_text(message, self._redact)
        super().__init__(safe_message)

    @property
    def report(self) -> dict[str, Any]:
        return {
            "argv": _redact_argv(self.argv, self._redact),
            "returncode": self.returncode,
            "stdout": redact_text(self.stdout, self._redact),
            "stderr": redact_text(self.stderr, self._redact),
            "error": redact_text(self._raw_message, self._redact),
            "timed_out": self.timed_out,
            "timeout": self.timeout,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    def __repr__(self) -> str:
        return f"CommandExecutionError(report={self.report!r})"


# A short alias is useful to callers that do not need to distinguish process
# startup failure from a nonzero process exit.
CommandError = CommandExecutionError


def _validate_argv(argv: Sequence[str]) -> list[str]:
    if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence):
        raise TypeError("command argv must be a non-string sequence")
    vector = list(argv)
    if not vector or any(not isinstance(item, str) or not item for item in vector):
        raise ValueError("command argv must contain non-empty strings")
    return vector


def _coerce_completed(argv: Sequence[str], completed: Any, redact: tuple[str, ...]) -> CommandResult:
    if isinstance(completed, CommandResult):
        return CommandResult(
            tuple(argv),
            completed.returncode,
            normalize_stream(completed.stdout, name="stdout"),
            normalize_stream(completed.stderr, name="stderr"),
            redact,
        )
    stdout = normalize_stream(getattr(completed, "stdout", ""), name="stdout")
    stderr = normalize_stream(getattr(completed, "stderr", ""), name="stderr")
    return CommandResult(
        tuple(argv),
        int(getattr(completed, "returncode", 0)),
        stdout,
        stderr,
        redact,
    )


class CommandRunner:
    """Run argument vectors through ``subprocess.run`` or an injected seam."""

    def __init__(
        self,
        executor: Callable[..., Any] | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        **kwargs: Any,
    ) -> None:
        # ``run`` and ``execute`` are accepted as descriptive dependency
        # injection aliases for tests and later adapters.
        if executor is not None and kwargs:
            raise TypeError("provide only one command executor")
        injected = executor
        if injected is None:
            injected = kwargs.pop("run", None)
        if injected is None:
            injected = kwargs.pop("execute", None)
        if injected is not None:
            delegated_run = getattr(injected, "run", None)
            if callable(delegated_run):
                injected = delegated_run
        self._executor = injected
        try:
            self.timeout = float(timeout)
        except (TypeError, ValueError) as exc:
            raise ValueError("command timeout must be a positive finite number") from exc
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("command timeout must be a positive finite number")
        if kwargs:
            unknown = next(iter(kwargs))
            raise TypeError(f"unexpected CommandRunner option: {unknown}")

    @staticmethod
    def _invoke_executor(
        executor: Callable[..., Any],
        argv: list[str],
        input_text: str | None,
        timeout: float,
    ) -> Any:
        try:
            parameters = tuple(inspect.signature(executor).parameters.values())
        except (TypeError, ValueError):
            return executor(argv, input_text=input_text, timeout=timeout)

        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters
        )
        positional = [argv]
        keyword: dict[str, Any] = {}
        for parameter in parameters[1:]:
            if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
                if parameter.name == "input_text":
                    positional.append(input_text)
                elif parameter.name == "timeout":
                    positional.append(timeout)
                elif parameter.default is inspect.Parameter.empty:
                    # Let Python produce the usual invocation TypeError for
                    # unsupported required positional parameters.
                    return executor(*positional)
            elif parameter.name == "input_text":
                keyword[parameter.name] = input_text
            elif parameter.name == "timeout":
                keyword[parameter.name] = timeout
        if accepts_kwargs:
            keyword.setdefault("input_text", input_text)
            keyword.setdefault("timeout", timeout)
        return executor(*positional, **keyword)

    def _run_injected(
        self,
        executor: Callable[..., Any],
        argv: list[str],
        input_text: str | None,
    ) -> Any:
        """Run an injected seam with the same wall-clock bound as subprocesses."""

        result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

        def invoke() -> None:
            try:
                result_queue.put(
                    (True, self._invoke_executor(executor, argv, input_text, self.timeout))
                )
            except BaseException as error:
                # Preserve KeyboardInterrupt/SystemExit for the caller while
                # still transporting ordinary executor failures safely.
                result_queue.put((False, error))

        thread = threading.Thread(target=invoke, daemon=True)
        thread.start()
        thread.join(self.timeout)
        if thread.is_alive():
            raise subprocess.TimeoutExpired(argv, self.timeout)
        try:
            succeeded, value = result_queue.get_nowait()
        except queue.Empty as error:
            raise RuntimeError("injected executor returned no result") from error
        if not succeeded:
            raise value
        return value

    def run(
        self,
        argv: Sequence[str],
        *,
        input_text: str | None = None,
        redact: Iterable[Any] | Any = (),
    ) -> CommandResult:
        """Execute one vector without a shell and raise on nonzero status."""

        vector = _validate_argv(argv)
        secrets = _redaction_values(redact)
        try:
            if self._executor is not None:
                completed = self._run_injected(self._executor, vector, input_text)
            else:
                completed = subprocess.run(
                    vector,
                    input=input_text,
                    capture_output=True,
                    text=True,
                    check=False,
                    shell=False,
                    timeout=self.timeout,
                )
        except subprocess.TimeoutExpired as exc:
            raise CommandExecutionError(
                f"command timed out: {vector[0]}",
                argv=vector,
                stdout=exc.output,
                stderr=exc.stderr,
                redact=secrets,
                timed_out=True,
                timeout=self.timeout,
            ) from exc
        except Exception as exc:
            raise CommandExecutionError(
                f"could not execute {vector[0]}: {exc}",
                argv=vector,
                stderr=str(exc),
                redact=secrets,
            ) from exc
        try:
            result = _coerce_completed(vector, completed, secrets)
        except Exception as exc:
            raise CommandExecutionError(
                f"invalid output from {vector[0]}: {exc}",
                argv=vector,
                redact=secrets,
            ) from exc
        if result.returncode != 0:
            raise CommandExecutionError(
                f"command exited with status {result.returncode}: {vector[0]}",
                argv=vector,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                redact=secrets,
            )
        return result


__all__ = [
    "CommandError",
    "CommandExecutor",
    "CommandExecutionError",
    "CommandResult",
    "CommandRunner",
    "DEFAULT_TIMEOUT",
    "REDACTED",
    "normalize_stream",
    "redact_text",
]
