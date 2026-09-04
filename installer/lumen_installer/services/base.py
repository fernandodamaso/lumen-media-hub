"""Small immutable, secret-free values shared by service adapters.

Adapters keep request payloads and credentials in their private execution
state.  Plans and results contain only stable action labels and generic
decision metadata, so they are safe to print or persist in installer reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ServiceDrift:
    """A managed conflict described without serializing either value."""

    resource: str
    field: str
    reason: str
    action: str = "review"

    def as_dict(self) -> dict[str, str]:
        return {
            "resource": self.resource,
            "field": self.field,
            "reason": self.reason,
            "action": self.action,
        }


@dataclass(frozen=True)
class ServiceCheckpoint:
    """A guided handoff that is intentionally not applied by the adapter."""

    code: str
    reason: str
    action: str = "review"
    severity: str = "warning"

    @property
    def decision(self) -> str:
        return self.action

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "reason": self.reason,
            "action": self.action,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class ServicePlan:
    """An immutable action plan with no request bodies or credentials."""

    service: str
    actions: tuple[str, ...] = ()
    drift: tuple[ServiceDrift, ...] = ()
    checkpoints: tuple[ServiceCheckpoint, ...] = ()
    status: str = "planned"
    dry_run: bool = False
    supported: bool = True
    mode: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "actions", tuple(str(item) for item in self.actions))
        object.__setattr__(self, "drift", tuple(self.drift))
        object.__setattr__(self, "checkpoints", tuple(self.checkpoints))

    @property
    def decision_records(self) -> tuple[ServiceCheckpoint, ...]:
        return self.checkpoints

    @property
    def report(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "status": self.status,
            "supported": self.supported,
            "dry_run": self.dry_run,
            "mode": self.mode,
            "actions": list(self.actions),
            "drift": [record.as_dict() for record in self.drift],
            "checkpoints": [record.as_dict() for record in self.checkpoints],
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    @property
    def steps(self) -> tuple[str, ...]:
        return self.actions


@dataclass(frozen=True)
class ServiceResult:
    """An immutable operation result whose report omits exception text."""

    service: str
    status: str
    actions: tuple[str, ...] = ()
    drift: tuple[ServiceDrift, ...] = ()
    checkpoints: tuple[ServiceCheckpoint, ...] = ()
    dry_run: bool = False
    error: BaseException | None = field(default=None, repr=False, compare=False)
    mode: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "actions", tuple(str(item) for item in self.actions))
        object.__setattr__(self, "drift", tuple(self.drift))
        object.__setattr__(self, "checkpoints", tuple(self.checkpoints))

    @property
    def report(self) -> dict[str, Any]:
        error_code = None
        if self.error is not None:
            error_code = getattr(self.error, "code", None) or type(self.error).__name__
        return {
            "service": self.service,
            "status": self.status,
            "dry_run": self.dry_run,
            "mode": self.mode,
            "actions": list(self.actions),
            "drift": [record.as_dict() for record in self.drift],
            "checkpoints": [record.as_dict() for record in self.checkpoints],
            "error": error_code,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    @property
    def stages(self) -> tuple[str, ...]:
        return self.actions


# Adapter-oriented aliases keep later service modules independent of a single
# naming convention while retaining one shared implementation.
AdapterPlan = ServicePlan
AdapterResult = ServiceResult
Drift = ServiceDrift
Checkpoint = ServiceCheckpoint


__all__ = [
    "AdapterPlan",
    "AdapterResult",
    "Checkpoint",
    "Drift",
    "ServiceCheckpoint",
    "ServiceDrift",
    "ServicePlan",
    "ServiceResult",
]
