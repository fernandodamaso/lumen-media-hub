"""Versioned non-secret answers and deterministic value resolution."""

from __future__ import annotations

import json
import inspect
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

from .errors import InvalidInputError


@dataclass(frozen=True)
class Answers(Mapping[str, Any]):
    """Immutable answer data loaded from a schema-versioned JSON file."""

    schema_version: int
    values: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise InvalidInputError("answers schema_version must be 1")
        if not isinstance(self.values, Mapping):
            raise InvalidInputError("answers must be an object")
        normalized = dict(self.values)
        for name, value in normalized.items():
            if _secret_name(str(name)) and _present(value) and _secret_reference(value) is None:
                raise InvalidInputError(
                    f"secret answer must reference an environment variable: {name}"
                )
        object.__setattr__(self, "values", MappingProxyType(normalized))

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)

    @classmethod
    def load(cls, path: str | Path) -> "Answers":
        """Load only version 1 answers, rejecting malformed input safely."""

        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise InvalidInputError(f"could not load answers file: {Path(path).name}") from exc
        if not isinstance(document, dict):
            raise InvalidInputError("answers file must contain a JSON object")
        version = document.get("schema_version")
        if not isinstance(version, int) or isinstance(version, bool) or version != 1:
            raise InvalidInputError("answers schema_version must be 1")

        if "answers" in document:
            values = document["answers"]
            if not isinstance(values, dict):
                raise InvalidInputError("answers field must contain a JSON object")
        else:
            values = {key: value for key, value in document.items() if key != "schema_version"}
        return cls(schema_version=1, values=values)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    @property
    def data(self) -> Mapping[str, Any]:
        """Compatibility alias for callers that name the payload ``data``."""

        return self.values

    @property
    def answers(self) -> Mapping[str, Any]:
        """Compatibility alias for callers that name the payload ``answers``."""

        return self.values


def _mapping_value(container: Any, name: str) -> Any:
    if container is None:
        return None
    if isinstance(container, Mapping):
        if name in container:
            return container[name]
        upper = name.upper()
        if upper in container:
            return container[upper]
        return None
    try:
        value = getattr(container, name)
    except AttributeError:
        return None
    return value


def _present(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip())


def _environment_key(name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    return f"LUMEN_{normalized}"


def _secret_reference(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key in (
            "env",
            "environment",
            "env_var",
            "env_var_name",
            "environment_variable",
            "secret_env",
        ):
            reference = value.get(key)
            if _present(reference):
                return str(reference).strip()
        return None
    if isinstance(value, str) and value.startswith("env:"):
        reference = value[4:].strip()
        return reference or None
    return None


def _secret_name(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower())
    return any(
        marker in normalized
        for marker in ("password", "secret", "token", "api_key", "client_key", "refresh")
    )


@dataclass
class Resolver:
    """Resolve an answer while retaining only non-secret source metadata."""

    defaults: Mapping[str, Any] = field(default_factory=dict)
    noninteractive: bool = False
    last_report: dict[str, Any] = field(default_factory=dict, init=False)

    def _report(self, name: str, source: str, *, secret: bool = False, **metadata: Any) -> None:
        report: dict[str, Any] = {"name": name, "source": source}
        if secret:
            report["secret"] = True
        report.update(metadata)
        self.last_report = report

    @property
    def report(self) -> dict[str, Any]:
        """Return redacted metadata for the most recent resolution."""

        return dict(self.last_report)

    @staticmethod
    def _invoke_prompt(prompt: Callable[..., Any], name: str, default: Any) -> Any:
        """Call prompt callbacks with one or two supported arguments once."""

        try:
            signature = inspect.signature(prompt)
        except (TypeError, ValueError):
            return prompt(name)
        parameters = tuple(signature.parameters.values())
        accepts_two = any(
            parameter.kind is inspect.Parameter.VAR_POSITIONAL
            for parameter in parameters
        ) or len(
            [
                parameter
                for parameter in parameters
                if parameter.kind
                in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            ]
        ) >= 2
        return prompt(name, default) if accepts_two else prompt(name)

    def get(
        self,
        name: str,
        cli: Any,
        env: Mapping[str, str] | None,
        answers: Answers | Mapping[str, Any] | None,
        prompt: Callable[..., Any] | None,
    ) -> Any:
        """Return the first present value in the approved precedence order."""

        cli_value = _mapping_value(cli, name)
        if _present(cli_value):
            self._report(name, "cli", secret=_secret_name(name))
            return cli_value

        environment = env or {}
        env_key = _environment_key(name)
        env_value = environment.get(env_key)
        if _present(env_value):
            self._report(name, "env", secret=_secret_name(name), environment_variable=env_key)
            return env_value

        answer_value = _mapping_value(answers, name)
        if _present(answer_value):
            reference = _secret_reference(answer_value)
            if reference is not None:
                resolved = environment.get(reference)
                if not _present(resolved):
                    # References normally name the exact process variable;
                    # accepting the LUMEN_ form makes headless invocation
                    # convenient without changing the report contents.
                    resolved = environment.get(_environment_key(reference))
                if not _present(resolved):
                    # A secret answer is deliberately a reference, so do not
                    # fall through to a prompt that could accidentally expose
                    # a password or token in a report.
                    raise InvalidInputError(
                        f"required secret environment variable is missing: {reference}"
                    )
                self._report(
                    name,
                    "answers",
                    secret=True,
                    environment_variable=reference,
                )
                return resolved
            if _secret_name(name):
                raise InvalidInputError(
                    f"secret answer must reference an environment variable: {name}"
                )
            self._report(name, "answers", secret=_secret_name(name))
            return answer_value

        default = _mapping_value(self.defaults, name)
        if self.noninteractive:
            if _present(default):
                self._report(name, "default", secret=_secret_name(name))
                return default
            raise InvalidInputError(f"required answer is missing: {name}")

        prompted = None
        if prompt is not None:
            if not callable(prompt):
                raise InvalidInputError("prompt must be callable")
            prompted = self._invoke_prompt(prompt, name, default)
        if _present(prompted):
            self._report(name, "prompt", secret=_secret_name(name))
            return prompted
        if _present(default):
            self._report(name, "default", secret=_secret_name(name))
            return default
        raise InvalidInputError(f"required answer is missing: {name}")


__all__ = ["Answers", "Resolver"]
