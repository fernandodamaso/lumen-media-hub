"""Typed errors and stable exit codes for the Linux installer."""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Process exit codes exposed by the installer command line."""

    OK = 0
    INVALID = 2
    DRIFT = 3
    PARTIAL = 4


class InstallerError(Exception):
    """Base class for expected, user-facing installer failures."""

    exit_code = ExitCode.INVALID

    def __init__(
        self,
        message: str = "",
        exit_code: ExitCode | int | None = None,
    ) -> None:
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = ExitCode(exit_code)
        self.message = message


class InvalidInputError(InstallerError):
    """Input or preflight validation failed."""

    exit_code = ExitCode.INVALID


class PreflightError(InvalidInputError):
    """A host or runtime prerequisite cannot be satisfied safely."""


class UnsupportedPlatformError(PreflightError):
    """The host distribution has no approved dependency policy."""


UnsupportedDistroError = UnsupportedPlatformError


class DriftError(InstallerError):
    """Existing configuration requires an explicit decision."""

    exit_code = ExitCode.DRIFT


class PartialError(InstallerError):
    """An operation completed only partially or needs a later phase."""

    exit_code = ExitCode.PARTIAL


class NotAvailableError(PartialError):
    """A command boundary exists but its implementation lands later."""


class HelpRequested(InstallerError):
    """Internal control flow used after argparse prints help text."""

    exit_code = ExitCode.OK


__all__ = [
    "DriftError",
    "ExitCode",
    "HelpRequested",
    "InstallerError",
    "InvalidInputError",
    "PreflightError",
    "NotAvailableError",
    "PartialError",
    "UnsupportedDistroError",
    "UnsupportedPlatformError",
]
