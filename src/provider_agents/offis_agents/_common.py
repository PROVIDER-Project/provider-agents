"""State and schema helpers shared by the standalone OFFIS agents."""

from typing import Any

from ..abstract_provider_agent import AgentSpec

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
}
UPSTREAM = {"type": "array", "items": object_schema(
    SOURCE_PROPERTIES, ("key", "quantity_available", "unit_price"),
)}


def state_properties(defaults):
    types = {bool: "boolean", int: "integer", float: "number", str: "string"}
    return {name: {"type": types[type(value)], "default": value}
            for name, value in defaults.items()}


def make_spec(agent_id, description, defaults, setup_extra=None,
              step_extra=None, output_extra=None, patches=()):
    properties = state_properties(defaults)
    output_fields = {name for patch in patches for name in patch}
    output = object_schema({
        **{name: properties[name] for name in output_fields}, **(output_extra or {}),
    })
    output["anyOf"] = [{"maxProperties": 0}] + [
        {"required": list(patch)} for patch in patches
    ]
    return AgentSpec(
        agent_id=agent_id, contract_version="1.0", description=description,
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
        setattr(agent, name, data.get(name, default))
    return snapshot(agent)


def snapshot(agent) -> dict[str, Any]:
    return {name: getattr(agent, name) for name in agent.defaults}


def synchronize(agent, data):
    for name, value in data.get("state", {}).items():
        if name not in agent.defaults:
            raise ValueError(f"Unknown state field: {name!r}")
        setattr(agent, name, value)


def effective(data, slot):
    return data.get("effects", {}).get(slot, 1.0)
