"""Safe, injectable command execution for the Linux installer.

The installer deliberately keeps process execution in one small module.  All
callers provide an argument vector; there is no shell interpolation or shell
pipeline escape hatch.  A command result retains its raw streams for trusted
parsers, while its public report and typed failures are redacted.
"""

from __future__ import annotations

import inspect
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Callable

from .errors import InvalidInputError


REDACTED = "<redacted>"


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
    normalized = {
        value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)
        for value in values
        if value is not None
        and (not isinstance(value, (str, bytes)) or str(value).strip())
    }
    # Replacing longest values first prevents a shorter credential from
    # exposing the remainder of a longer credential in a report.
    return tuple(sorted(normalized, key=lambda value: (-len(value), value)))


def redact_text(value: Any, redact: Iterable[Any] | Any = ()) -> str:
    """Return text with every configured secret value replaced."""

    text = "" if value is None else str(value)
    for secret in _redaction_values(redact):
        text = text.replace(secret, REDACTED)
    return text


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
    ) -> None:
        self._redact = _redaction_values(redact)
        self.argv = tuple(str(item) for item in argv)
        self.returncode = returncode
        self.stdout = "" if stdout is None else str(stdout)
        self.stderr = "" if stderr is None else str(stderr)
        self._raw_message = str(message)
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
            completed.stdout,
            completed.stderr,
            redact,
        )
    return CommandResult(
        tuple(argv),
        int(getattr(completed, "returncode", 0)),
        getattr(completed, "stdout", "") or "",
        getattr(completed, "stderr", "") or "",
        redact,
    )


class CommandRunner:
    """Run argument vectors through ``subprocess.run`` or an injected seam."""

    def __init__(self, executor: Callable[..., Any] | None = None, **kwargs: Any) -> None:
        # ``run`` and ``execute`` are accepted as descriptive dependency
        # injection aliases for tests and later adapters.
        if executor is not None and kwargs:
            raise TypeError("provide only one command executor")
        self._executor = executor or kwargs.pop("run", None) or kwargs.pop("execute", None)
        if kwargs:
            unknown = next(iter(kwargs))
            raise TypeError(f"unexpected CommandRunner option: {unknown}")

    @staticmethod
    def _invoke_executor(executor: Callable[..., Any], argv: list[str], input_text: str | None) -> Any:
        try:
            parameters = inspect.signature(executor).parameters.values()
        except (TypeError, ValueError):
            return executor(argv, input_text=input_text)
        accepts_keyword = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD or parameter.name == "input_text"
            for parameter in parameters
        )
        return executor(argv, input_text=input_text) if accepts_keyword else executor(argv)

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
                completed = self._invoke_executor(self._executor, vector, input_text)
            else:
                completed = subprocess.run(
                    vector,
                    input=input_text,
                    capture_output=True,
                    text=True,
                    check=False,
                    shell=False,
                )
        except (OSError, subprocess.SubprocessError) as exc:
            raise CommandExecutionError(
                f"could not execute {vector[0]}: {exc}",
                argv=vector,
                stderr=str(exc),
                redact=secrets,
            ) from exc

        result = _coerce_completed(vector, completed, secrets)
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
    "CommandExecutionError",
    "CommandResult",
    "CommandRunner",
    "REDACTED",
    "redact_text",
]
