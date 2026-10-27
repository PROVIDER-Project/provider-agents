"""Abstract base contract for simulation agents.

This module introduces a formal ABC for agent implementations.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, ClassVar, Dict, Mapping

try:
    import jsonschema  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    jsonschema = None  # type: ignore


def validate_schema(instance: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    """Validate *instance* against *schema*.

    Uses jsonschema if installed; otherwise falls back to a minimal built-in
    checker covering required fields, type ranges, and enums. This keeps the
    package dependency-free for external teams that just want the interface.
    """
    if not schema:
        return
    if jsonschema is not None:
        # Key by content so mutable AgentSpec schemas cannot leave stale validators.
        validator = _schema_validator(json.dumps(dict(schema), sort_keys=True))
        validator.validate(dict(instance))
        return
    _validate_schema_fallback(instance, schema)


@lru_cache(maxsize=128)
def _schema_validator(serialized_schema: str) -> Any:
    """Check each schema once and reuse its draft-specific validator."""
    schema = json.loads(serialized_schema)
    validator_class = jsonschema.validators.validator_for(schema)
    validator_class.check_schema(schema)
    return validator_class(schema)


def _validate_schema_fallback(instance: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    schema_type = schema.get("type")
    if schema_type == "object":
        required = set(schema.get("required", []))
        missing = required - set(instance.keys())
        if missing:
            raise ValueError(f"Missing required field(s): {sorted(missing)}")
        props = schema.get("properties", {})
        for key, value in instance.items():
            prop_schema = props.get(key)
            if prop_schema is None:
                continue
            if isinstance(value, Mapping):
                _validate_schema_fallback(value, prop_schema)
            else:
                _validate_scalar(value, prop_schema)
        return
    _validate_scalar(instance, schema)


def _validate_scalar(value: Any, schema: Mapping[str, Any]) -> None:
    if "minimum" in schema and value < schema["minimum"]:
        raise ValueError(f"Value {value!r} is below minimum {schema['minimum']}")
    if "maximum" in schema and value > schema["maximum"]:
        raise ValueError(f"Value {value!r} exceeds maximum {schema['maximum']}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"Value {value!r} not in enum {schema['enum']!r}")


@dataclass
class AgentSpec:
    """Canonical, versioned contract for one `AbstractPROVIDERAgent` implementation.

    Declares the JSON Schema each `setup()`/`step()` input and output dict
    must satisfy, so the ABC can validate implementations without needing
    to know their internal state.

    Attributes:
        agent_id: Stable identifier for this agent archetype (e.g. "farmer").
        contract_version: Semver-style string; bump when schemas change shape.
        description: Human-readable summary.
        setup_input_schema: JSON Schema for `setup()`'s `data_in`.
        setup_output_schema: JSON Schema for `setup()`'s returned `data_out`.
        step_input_schema: JSON Schema for `step()`'s `data_in`.
        step_output_schema: JSON Schema for `step()`'s returned `data_out`.
    """

    agent_id: str
    contract_version: str = "1.0"
    description: str = ""

    setup_input_schema: Dict[str, Any] = field(default_factory=dict)
    setup_output_schema: Dict[str, Any] = field(default_factory=dict)
    step_input_schema: Dict[str, Any] = field(default_factory=dict)
    step_output_schema: Dict[str, Any] = field(default_factory=dict)

    def validate_setup_input(self, data_in: Dict[str, Any]) -> None:
        validate_schema(data_in, self.setup_input_schema)

    def validate_setup_output(self, data_out: Dict[str, Any]) -> None:
        validate_schema(data_out, self.setup_output_schema)

    def validate_step_input(self, data_in: Dict[str, Any]) -> None:
        validate_schema(data_in, self.step_input_schema)

    def validate_step_output(self, data_out: Dict[str, Any]) -> None:
        validate_schema(data_out, self.step_output_schema)


class AbstractPROVIDERAgent(ABC):
    """Abstract interface and shared helpers for all supply chain agents."""

    #: Every concrete subclass must set this to an `AgentSpec` describing the
    #: JSON Schemas for its `setup()`/`step()` inputs and outputs.
    spec: ClassVar[AgentSpec]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if getattr(cls, "__abstractmethods__", None):
            return  # still abstract itself; spec not required until concrete
        if not isinstance(getattr(cls, "spec", None), AgentSpec):
            raise TypeError(f"{cls.__name__} must define a class attribute 'spec: AgentSpec'")

    @abstractmethod
    def _setup(self, data_in: dict[str, Any]) -> dict[str, Any]:
        """Initialise shared and role-specific state for the agent. 
        Take any parameters as input from `data_in` and return any initial state via `data_out`."""
        raise NotImplementedError

    @abstractmethod
    def _step(self, data_in: dict[str, Any]) -> dict[str, Any]:
        """Advance the agent by one simulation step. 
        Take all required data as `data_in` and return any agent actions via `data_out`."""
        raise NotImplementedError

    def setup(self, data_in: dict[str, Any]) -> dict[str, Any]:
        """Validate `data_in`/`data_out` against `spec` around `_setup()`."""
        self.spec.validate_setup_input(data_in)
        data_out = self._setup(data_in)
        self.spec.validate_setup_output(data_out)
        return data_out

    def step(self, data_in: dict[str, Any]) -> dict[str, Any]:
        """Validate `data_in`/`data_out` against `spec` around `_step()`."""
        self.spec.validate_step_input(data_in)
        data_out = self._step(data_in)
        self.spec.validate_step_output(data_out)
        return data_out
