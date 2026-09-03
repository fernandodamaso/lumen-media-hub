"""HTTP-backed service adapters used by the Linux installer."""

from .base import (
    AdapterPlan,
    AdapterResult,
    Checkpoint,
    Drift,
    ServiceCheckpoint,
    ServiceDrift,
    ServicePlan,
    ServiceResult,
)
from .jellyfin import (
    JellyfinAdapter,
    JellyfinAuthenticationError,
    JellyfinAuthError,
    JellyfinCapability,
    JellyfinCapabilityError,
    JellyfinError,
    JellyfinResult,
    JellyfinSchemaError,
    JellyfinSession,
    configure_jellyfin,
    plan_jellyfin,
)

__all__ = [
    "AdapterPlan",
    "AdapterResult",
    "Checkpoint",
    "Drift",
    "JellyfinAdapter",
    "JellyfinAuthenticationError",
    "JellyfinAuthError",
    "JellyfinCapability",
    "JellyfinCapabilityError",
    "JellyfinError",
    "JellyfinResult",
    "JellyfinSchemaError",
    "JellyfinSession",
    "ServiceCheckpoint",
    "ServiceDrift",
    "ServicePlan",
    "ServiceResult",
    "configure_jellyfin",
    "plan_jellyfin",
]
