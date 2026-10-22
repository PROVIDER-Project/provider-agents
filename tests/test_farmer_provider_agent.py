import numpy as np
import pytest

from provider_agents.offis_agents.farmer_provider_agent import FarmerProviderAgent


def test_seeded_size_matches_simenv():
    agent = FarmerProviderAgent()
    state = agent.setup({
        "role": "producer", "base_yield": 100.0, "fixed_costs": 200.0,
        "size_sigma": 0.4, "farm_size_seed": 42, "agent_id": 3,
    })
    expected = float(np.random.default_rng(45).lognormal(0.0, 0.4))
    assert state["size_factor"] == expected
    assert state["base_yield"] == 100.0 * expected
    assert state["fixed_costs"] == 200.0 * expected


def test_producer_effects_and_external_state():
    agent = FarmerProviderAgent()
    assert agent.setup({"role": "producer", "base_yield": 100.0,
                        "fixed_costs": 200.0, "margin": 0.1})["unit_price"] == 2.2
    assert agent.step({"effects": {"capacity": 0.5, "fertilizer": 1.2}}) == {
        "quantity_available": 50.0, "unit_price": 5.28,
    }
    assert agent.step({"state": {"active": False}}) == {}


def test_consumer_sharing_starvation_and_recovery():
    agent = FarmerProviderAgent()
    agent.setup({"role": "consumer"})
    result = agent.step({"consumer_count": 2, "upstream": [
        {"key": "feed", "quantity_available": 100.0, "unit_price": 10.0},
    ]})
    assert result["feed_received"] == result["livestock_output"] == 50.0
    for _ in range(20):
        assert agent.step({})["active"] is True
    assert agent.step({}) == {
        "feed_received": 0.0, "livestock_output": 0.0,
        "days_without_input": 21, "active": False,
    }
    assert agent.step({}) == {}
    result = agent.step({"state": {"active": True}, "consumer_count": 1,
                         "upstream": [{"key": "f", "quantity_available": 1.0,
                                       "unit_price": 0.0}]})
    assert result["days_without_input"] == 0


def test_defaults_and_unknown_role():
    agent = FarmerProviderAgent()
    assert agent.setup({})["quantity_available"] == 0.0
    with pytest.raises(ValueError, match="unknown role"):
        agent.step({})
