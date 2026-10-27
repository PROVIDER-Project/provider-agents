import pytest

from provider_agents.offis_agents.process_provider_agent import ProcessProviderAgent


@pytest.mark.parametrize("role", ["processor", "feed_manufacturer"])
def test_conversion_capacity_and_price(role):
    agent = ProcessProviderAgent()
    agent.setup({"role": role, "conversion_ratio": 0.8, "fixed_costs": 20.0, "margin": 0.1})
    result = agent.step({"peer_count": 2, "effects": {"capacity": 0.5}, "upstream": [
        {"key": "a", "quantity_available": 100.0, "unit_price": 10.0},
    ]})
    assert result == {"input_received": 50.0, "quantity_available": 20.0,
                      "unit_price": pytest.approx(14.85)}


@pytest.mark.parametrize("upstream,peers,ratio", [([], 1, 0.8), (
    [{"key": "a", "quantity_available": 100.0, "unit_price": 10.0}], 0, 0.8), (
    [{"key": "a", "quantity_available": 100.0, "unit_price": 10.0}], 1, 0.0)])
def test_empty_zero_peers_and_zero_conversion(upstream, peers, ratio):
    agent = ProcessProviderAgent()
    agent.setup({"role": "processor", "conversion_ratio": ratio})
    assert agent.step({"upstream": upstream, "peer_count": peers})["unit_price"] == 0.0
    assert agent.step({"state": {"active": False}}) == {}


def test_unknown_role_remains_noop():
    agent = ProcessProviderAgent()
    agent.setup({})
    assert agent.step({}) == {}
