"""State and schema helpers shared by the standalone OFFIS agents."""

from copy import deepcopy
from typing import Any

from ..abstract_provider_agent import AgentSpec
from .economics import nonnegative, validate_cost_effects, validate_cost_shares

SHARED_DEFAULTS = {"quantity_available": 0.0, "unit_price": 0.0, "active": True}
NUMBER = {"type": "number"}
EFFECTS = {"type": "object", "additionalProperties": NUMBER}


def object_schema(properties, required=()):
    return {
        "type": "object", "properties": properties,
        "required": list(required), "additionalProperties": False,
    }


SOURCE_PROPERTIES = {
    "key": {"type": "string"},
    "quantity_available": NUMBER, "unit_price": NUMBER,
    "base_yield": NUMBER, "is_transport": {"type": "boolean"},
    "capacity": NUMBER, "effects": EFFECTS,
    "recipient_count": {"type": "integer"},
}
UPSTREAM = {"type": "array", "items": object_schema(
    SOURCE_PROPERTIES, ("key", "quantity_available", "unit_price"),
)}
UPSTREAM["items"]["allOf"] = [{
    "if": {"required": ["is_transport"],
           "properties": {"is_transport": {"const": True}}},
    "then": {"required": ["capacity"]},
}]
RECEIVED = {"type": "array", "items": object_schema(
    {"key": {"type": "string"}, "quantity": {"type": "number", "minimum": 0}},
    ("key", "quantity"),
)}


class ObservationRequirements:
    """Let hosts avoid gathering observations for no-op/error-only paths."""

    def requires_observations(self, state: dict[str, Any]) -> bool:
        return bool(
            state.get("active", self.active)
            and state.get("role", self.role) in self.observation_roles
        )


def state_properties(defaults):
    types = {bool: "boolean", int: "integer", float: "number", str: "string"}
    properties = {}
    for name, value in defaults.items():
        if name == "input_cost_shares":
            schema = {"type": "object", "additionalProperties": {
                "type": "number", "minimum": 0, "maximum": 1,
            }}
        elif name == "throughput_capacity":
            schema = {"anyOf": [{"type": "number", "minimum": 0}, {"type": "null"}]}
        else:
            schema = {"type": types[type(value)]}
        properties[name] = {**schema, "default": deepcopy(value)}
    return properties


def make_spec(agent_id, description, defaults, setup_extra=None,
              step_extra=None, output_extra=None, patches=()):
    properties = state_properties(defaults)
    output_fields = {name for patch in patches for name in patch}
    output = object_schema({
        **{name: properties[name] for name in output_fields}, "received": RECEIVED,
        **(output_extra or {}),
    })
    output["anyOf"] = [{"maxProperties": 0}] + [
        {"required": list(patch)} for patch in patches
    ]
    return AgentSpec(
        agent_id=agent_id, contract_version="3.0", description=description,
        setup_input_schema=object_schema({**properties, **(setup_extra or {})}),
        setup_output_schema=object_schema(properties, defaults),
        step_input_schema=object_schema({
            "state": object_schema(properties), "effects": EFFECTS,
            "upstream": UPSTREAM, "peer_count": {"type": "integer"},
            **(step_extra or {}),
        }),
        step_output_schema=output,
    )


def initialize(agent, data: dict[str, Any]) -> dict[str, Any]:
    for name, default in agent.defaults.items():
        setattr(agent, name, deepcopy(data.get(name, default)))
    validate_economic_state(agent)
    return snapshot(agent)


def snapshot(agent) -> dict[str, Any]:
    return {name: deepcopy(getattr(agent, name)) for name in agent.defaults}


def synchronize(agent, data):
    for name, value in data.get("state", {}).items():
        if name not in agent.defaults:
            raise ValueError(f"Unknown state field: {name!r}")
        setattr(agent, name, deepcopy(value))
    validate_economic_state(agent)
    if agent.active and agent.role in agent.observation_roles:
        validate_cost_effects(agent.input_cost_shares, data.get("effects", {}))


def validate_economic_state(agent):
    nonnegative(agent.fixed_costs, "fixed_costs")
    validate_cost_shares(agent.input_cost_shares)


def effective(data, slot):
    return data.get("effects", {}).get(slot, 1.0)


def received(upstream, taken):
    total = sum(source["quantity_available"] for source in upstream)
    return [{"key": source["key"],
             "quantity": taken * source["quantity_available"] / total if total > 0 else 0.0}
            for source in upstream]
