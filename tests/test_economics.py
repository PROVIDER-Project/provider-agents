"""Selective cost exposure must not reprice unexposed costs or purchases."""

from copy import deepcopy

import jsonschema
import pytest

from provider_agents import abstract_provider_agent as contract
from provider_agents.offis_agents import (
    FarmerProviderAgent,
    ProcessProviderAgent,
    TraderProviderAgent,
    TransportProviderAgent,
)


def test_selective_exposure_and_neutral_missing_inputs():
    from provider_agents.offis_agents.economics import operating_cost

    assert operating_cost(100, {"fertilizer": .25}, {"fertilizer": 2}) == 125
    assert operating_cost(100, {"a": .25, "b": .5}, {"a": 2, "b": .5}) == 100
    assert operating_cost(100, {"a": .25}, {}) == 100
    assert operating_cost(100, {}, {"unrelated": 100}) == 100


@pytest.mark.parametrize("shares", [
    [], None, {"a": -1}, {"a": True}, {"a": "0.2"},
    {"a": float("nan")}, {"a": float("inf")}, {"a": .6, "b": .5},
    {"capacity": .1}, {1: .1},
])
def test_invalid_cost_shares(shares):
    from provider_agents.offis_agents.economics import validate_cost_shares

    with pytest.raises(ValueError):
        validate_cost_shares(shares)


@pytest.mark.parametrize("value", [-1, True, "2", float("nan"), float("inf")])
def test_invalid_cost_or_exposed_multiplier(value):
    from provider_agents.offis_agents.economics import operating_cost

    with pytest.raises(ValueError):
        operating_cost(value, {}, {})
    with pytest.raises(ValueError):
        operating_cost(100, {"a": .1}, {"a": value})


@pytest.mark.parametrize("cls,setup,message,expected", [
    (FarmerProviderAgent, {"role": "producer", "base_yield": 10.}, {}, 12.5),
    (TraderProviderAgent, {"role": "feed_trader"}, {"peer_count": 1}, 22.5),
    (ProcessProviderAgent, {"role": "processor"}, {"peer_count": 1}, 22.5),
    (TransportProviderAgent, {"role": "sea_transport", "capacity": 10.},
     {"peer_count": 1}, 22.5),
])
def test_all_actor_quotes_scale_operating_cost_only(cls, setup, message, expected):
    agent = cls()
    agent.setup({**setup, "fixed_costs": 100., "input_cost_shares": {"fuel": .25}})
    result = agent.step({**message, "effects": {"fuel": 2.}, "upstream": [
        {"key": "a", "quantity_available": 10., "unit_price": 10.},
    ]})
    assert result["unit_price"] == pytest.approx(expected)


@pytest.mark.parametrize("fallback", [False, True])
def test_invalid_synchronized_economics_without_optional_validator(fallback, monkeypatch):
    if fallback:
        monkeypatch.setattr(contract, "jsonschema", None)
    agent = FarmerProviderAgent()
    agent.setup({"role": "producer", "base_yield": 10.})
    for state in ({"input_cost_shares": {"a": float("nan")}},
                  {"fixed_costs": -1.}):
        with pytest.raises((ValueError, jsonschema.ValidationError)):
            agent.step({"state": state})


def test_cost_share_state_is_owned_by_each_agent():
    data = {"role": "producer", "base_yield": 10., "input_cost_shares": {"a": .25}}
    original = deepcopy(data)
    one, two = FarmerProviderAgent(), FarmerProviderAgent()
    one.setup(data)
    two.setup(data)
    one.input_cost_shares["a"] = .5
    assert two.input_cost_shares == {"a": .25}
    assert data == original
    one.step({"state": {"input_cost_shares": data["input_cost_shares"]}})
    one.input_cost_shares["a"] = .5
    assert data == original


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("cls,setup,message", [
    (FarmerProviderAgent, {"role": "producer", "base_yield": 0.}, {}),
    (TraderProviderAgent, {"role": "feed_trader"}, {"peer_count": 0}),
    (ProcessProviderAgent, {"role": "processor", "throughput_capacity": 0.},
     {"peer_count": 1, "upstream": [
         {"key": "a", "quantity_available": 10., "unit_price": 1.},
     ]}),
    (TransportProviderAgent, {"role": "sea_transport", "capacity": 0.}, {}),
])
def test_exposed_prices_are_validated_even_without_output(
    cls, setup, message, fallback, monkeypatch,
):
    if fallback:
        monkeypatch.setattr(contract, "jsonschema", None)
    agent = cls()
    agent.setup({**setup, "input_cost_shares": {"fuel": 1.}})
    with pytest.raises(ValueError, match="effects.fuel"):
        agent.step({**message, "effects": {"fuel": float("nan")}})
    assert agent.step({"state": {"active": False},
                       "effects": {"fuel": float("nan")}}) == {}
