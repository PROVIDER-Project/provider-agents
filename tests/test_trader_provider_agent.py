import pytest

from provider_agents.offis_agents.trader_provider_agent import TraderProviderAgent


def test_wholesaler_storage_and_price():
    agent = TraderProviderAgent()
    initial = agent.setup({"role": "wholesaler", "storage_capacity": 40.0,
                           "fixed_costs": 20.0, "margin": 0.1})
    assert initial["markup"] == 0.1
    result = agent.step({"peer_count": 2, "upstream": [
        {"key": "a", "quantity_available": 100.0, "unit_price": 10.0, "base_yield": 80.0},
    ]})
    assert result == {"stock": 40.0, "quantity_available": 40.0,
                      "storage_utilization": 1.0, "unit_price": pytest.approx(11.55),
                      "received": [{"key": "a", "quantity": 40.0}]}
    assert agent.step({"peer_count": 1}) == {
        "stock": 0.0, "quantity_available": 0.0, "unit_price": 0.0, "storage_utilization": 0.0,
        "received": [],
    }


def test_feed_trader_weighting_and_empty_input_preserves_price():
    agent = TraderProviderAgent()
    agent.setup({"role": "feed_trader", "margin": 0.1, "fixed_costs": 20.0})
    result = agent.step({"peer_count": 2, "upstream": [
        {"key": "a", "quantity_available": 20.0, "unit_price": 5.0},
        {"key": "b", "quantity_available": 80.0, "unit_price": 10.0},
    ]})
    assert result == {"stock": 50.0, "quantity_available": 50.0,
                      "unit_price": pytest.approx(10.34),
                      "received": [{"key": "a", "quantity": 10.0},
                                   {"key": "b", "quantity": 40.0}]}
    assert agent.step({"peer_count": 1}) == {"stock": 0.0, "quantity_available": 0.0,
                                             "received": []}
    assert agent.step({"peer_count": 0, "upstream": [
        {"key": "a", "quantity_available": 20.0, "unit_price": 5.0},
    ]})["received"] == [{"key": "a", "quantity": 0.0}]
    assert agent.unit_price == result["unit_price"]
    assert agent.step({"state": {"active": False}}) == {}


def test_feed_trader_carries_what_was_not_shipped():
    agent = TraderProviderAgent()
    agent.setup({"role": "feed_trader", "fixed_costs": 20.0})
    supply = [{"key": "a", "quantity_available": 100.0, "unit_price": 10.0}]
    first = agent.step({"peer_count": 1, "upstream": supply})
    assert first["stock"] == 100.0
    second = agent.step({"peer_count": 1, "upstream": supply, "shipped": 70.0})
    assert second["stock"] == second["quantity_available"] == 130.0
    assert second["received"] == [{"key": "a", "quantity": 100.0}]
    assert second["unit_price"] == first["unit_price"]
    assert agent.step({"peer_count": 1, "shipped": 0.0})["stock"] == 130.0
    assert agent.unit_price == first["unit_price"]


def test_wholesaler_carry_counts_against_storage():
    agent = TraderProviderAgent()
    agent.setup({"role": "wholesaler", "storage_capacity": 40.0})
    supply = [{"key": "a", "quantity_available": 100.0, "unit_price": 10.0,
               "base_yield": 100.0}]
    assert agent.step({"peer_count": 1, "upstream": supply})["stock"] == 40.0
    result = agent.step({"peer_count": 1, "upstream": supply, "shipped": 10.0})
    assert result["stock"] == 40.0
    assert result["received"] == [{"key": "a", "quantity": 10.0}]
    assert result["storage_utilization"] == 1.0
    empty = agent.step({"peer_count": 1, "shipped": 0.0})
    assert empty["stock"] == 40.0
    assert empty["unit_price"] == result["unit_price"]


def test_unknown_role_remains_noop():
    agent = TraderProviderAgent()
    agent.setup({})
    assert agent.step({}) == {}
