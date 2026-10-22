import json
import subprocess
import sys

import jsonschema
import pytest

from provider_agents import abstract_provider_agent as contract
from provider_agents.offis_agents import (
    FarmerProviderAgent,
    ProcessProviderAgent,
    TraderProviderAgent,
    TransportProviderAgent,
)

AGENTS = [
    (FarmerProviderAgent, "farmer", "producer"),
    (ProcessProviderAgent, "process", "processor"),
    (TraderProviderAgent, "trader", "feed_trader"),
    (TransportProviderAgent, "transport", "sea_transport"),
]


@pytest.mark.parametrize("cls,identifier,role", AGENTS)
def test_specs_describe_validated_public_messages(cls, identifier, role):
    assert isinstance(cls.spec, contract.AgentSpec)
    assert cls.spec.agent_id == identifier
    assert cls.spec.contract_version == "1.0"
    assert cls.spec.description
    for name in ("setup_input_schema", "setup_output_schema",
                 "step_input_schema", "step_output_schema"):
        schema = getattr(cls.spec, name)
        assert schema["properties"]
        jsonschema.Draft202012Validator.check_schema(schema)
    agent = cls()
    initialized = agent.setup({"role": role})
    assert set(initialized) == set(cls.defaults)
    assert agent.step({"state": {"active": False}}) == {}
    with pytest.raises(jsonschema.ValidationError):
        agent.step({"upstream": [{"key": "a", "quantity_available": "bad", "unit_price": 1}]})
    with pytest.raises(jsonschema.ValidationError):
        agent.step({"state": {"unknown": 1}})
    with pytest.raises(jsonschema.ValidationError):
        cls.spec.validate_setup_output({})


@pytest.mark.parametrize("cls,identifier,role", AGENTS)
def test_optional_validator_fallback(cls, identifier, role, monkeypatch):
    monkeypatch.setattr(contract, "jsonschema", None)
    agent = cls()
    agent.setup({"role": role})
    assert agent.step({"state": {"active": False}}) == {}
    with pytest.raises(ValueError, match="Missing required"):
        cls.spec.validate_setup_output({})


def test_standalone_import_and_execution_without_simenv_or_melodie():
    code = '''
import sys
class BlockFramework:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in ('Melodie', 'provider_simenv'):
            raise AssertionError('Framework imported: ' + fullname)
sys.meta_path.insert(0, BlockFramework())
from provider_agents.offis_agents import (
    FarmerProviderAgent, TraderProviderAgent, ProcessProviderAgent, TransportProviderAgent,
)
for cls in (FarmerProviderAgent, TraderProviderAgent, ProcessProviderAgent, TransportProviderAgent):
    agent = cls()
    agent.setup({'active': False})
    assert agent.step({}) == {}
'''
    subprocess.run([sys.executable, "-c", code], check=True)


def test_transport_patch_schema_rejects_bad_source_update():
    with pytest.raises(jsonschema.ValidationError):
        TransportProviderAgent.spec.validate_step_output({
            "quantity_available": 1.0, "utilisation": 1.0, "unit_price": 1.0,
            "upstream_updates": [{"key": "a", "quantity_available": "bad"}],
        })


@pytest.mark.parametrize("cls,identifier,role", AGENTS)
def test_output_spec_rejects_incomplete_action(cls, identifier, role):
    with pytest.raises(jsonschema.ValidationError):
        cls.spec.validate_step_output({"unit_price": 1.0})


def test_schema_messages_are_json_serializable():
    for cls, _, role in AGENTS:
        agent = cls()
        json.loads(json.dumps(agent.setup({"role": role})))
        json.loads(json.dumps(agent.step({})))


def test_transport_source_capacity_is_required_by_nested_schema():
    with pytest.raises(jsonschema.ValidationError):
        TransportProviderAgent.spec.validate_step_input({"upstream": [
            {"key": "a", "quantity_available": 1.0, "unit_price": 1.0, "is_transport": True},
        ]})


def test_wholesaler_source_yield_is_required_by_role_schema():
    with pytest.raises(jsonschema.ValidationError):
        TraderProviderAgent.spec.validate_step_input({
            "state": {"role": "wholesaler"}, "upstream": [
                {"key": "a", "quantity_available": 1.0, "unit_price": 1.0},
            ],
        })


@pytest.mark.parametrize("fallback", [False, True])
def test_wholesaler_requires_source_yield_without_repeated_role(fallback, monkeypatch):
    if fallback:
        monkeypatch.setattr(contract, "jsonschema", None)
    agent = TraderProviderAgent()
    agent.setup({"role": "wholesaler"})
    with pytest.raises((ValueError, jsonschema.ValidationError), match="base_yield"):
        agent.step({"peer_count": 1, "upstream": [
            {"key": "a", "quantity_available": 1.0, "unit_price": 1.0},
        ]})
