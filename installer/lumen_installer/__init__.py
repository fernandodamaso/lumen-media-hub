"""Linux installer command package for Lumen Media Hub."""

from .errors import (
    DriftError,
    ExitCode,
    InstallerError,
    InvalidInputError,
    NotAvailableError,
    PartialError,
)
from .answers import Answers, Resolver
from .dotenv import DotEnvDocument, write_atomic
from .environment import EnvironmentChange, EnvironmentPlan, plan_environment
from .platform import HostFacts, detect_host
from .secrets import ensure_actions_token
from .commands import (
    DEFAULT_TIMEOUT,
    CommandError,
    CommandExecutionError,
    CommandResult,
    CommandRunner,
    normalize_stream,
)
from .docker import (
    COMPOSE_MINIMUM,
    DependencyPlan,
    DecisionRecord,
    DockerPreflight,
    ManifestInspection,
    PlannedCommand,
    PreflightError,
    UnsupportedDistroError,
    UnsupportedPlatformError,
    dependency_plan,
    docker_preflight,
    inspect_manifest_architectures,
    parse_compose_version,
    parse_docker_version,
    run_host_doctor,
    validate_compose_version,
)

__all__ = [
    "DriftError",
    "ExitCode",
    "InstallerError",
    "InvalidInputError",
    "NotAvailableError",
    "PartialError",
    "Answers",
    "DotEnvDocument",
    "EnvironmentChange",
    "EnvironmentPlan",
    "HostFacts",
    "Resolver",
    "detect_host",
    "ensure_actions_token",
    "plan_environment",
    "write_atomic",
    "CommandError",
    "CommandExecutionError",
    "CommandResult",
    "CommandRunner",
    "DEFAULT_TIMEOUT",
    "COMPOSE_MINIMUM",
    "DependencyPlan",
    "DecisionRecord",
    "DockerPreflight",
    "ManifestInspection",
    "PlannedCommand",
    "PreflightError",
    "UnsupportedDistroError",
    "UnsupportedPlatformError",
    "dependency_plan",
    "docker_preflight",
    "inspect_manifest_architectures",
    "parse_compose_version",
    "parse_docker_version",
    "run_host_doctor",
    "validate_compose_version",
    "normalize_stream",
]
