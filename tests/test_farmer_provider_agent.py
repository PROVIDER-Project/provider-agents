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
        "stock": 50.0, "quantity_available": 50.0, "unit_price": 5.28,
    }
    assert agent.step({"state": {"active": False}}) == {}


def test_producer_carries_what_was_not_shipped():
    agent = FarmerProviderAgent()
    agent.setup({"role": "producer", "base_yield": 100.0, "fixed_costs": 200.0, "margin": 0.1})
    first = agent.step({})
    assert first["stock"] == 100.0
    second = agent.step({"shipped": 60.0})
    assert second["stock"] == second["quantity_available"] == 140.0
    assert second["unit_price"] == first["unit_price"]
    assert agent.step({"shipped": 500.0})["stock"] == 100.0
    dry = agent.step({"shipped": 0.0, "effects": {"capacity": 0.0}})
    assert dry["stock"] == 100.0
    assert dry["unit_price"] == first["unit_price"]


def test_consumer_sharing_starvation_and_recovery():
    agent = FarmerProviderAgent()
    agent.setup({"role": "consumer"})
    result = agent.step({"upstream": [
        {"key": "feed", "quantity_available": 100.0, "unit_price": 10.0, "recipient_count": 2},
    ]})
    assert result["feed_received"] == result["livestock_output"] == 50.0
    assert result["received"] == [{"key": "feed", "quantity": 50.0}]
    for _ in range(20):
        assert agent.step({})["active"] is True
    assert agent.step({}) == {
        "feed_received": 0.0, "livestock_output": 0.0,
        "days_without_input": 21, "active": False, "received": [],
    }
    assert agent.step({}) == {}
    result = agent.step({"state": {"active": True},
                         "upstream": [{"key": "f", "quantity_available": 1.0,
                                       "unit_price": 0.0, "recipient_count": 1}]})
    assert result["days_without_input"] == 0


def test_defaults_and_unknown_role():
    agent = FarmerProviderAgent()
    assert agent.setup({})["quantity_available"] == 0.0
    with pytest.raises(ValueError, match="unknown role"):
        agent.step({})


def test_each_feed_source_is_shared_only_across_its_own_recipients():
    agent = FarmerProviderAgent()
    agent.setup({"role": "consumer"})
    result = agent.step({"upstream": [
        {"key": "a", "quantity_available": 100.0, "unit_price": 1.0, "recipient_count": 2},
        {"key": "b", "quantity_available": 60.0, "unit_price": 1.0, "recipient_count": 1},
    ]})
    assert result["feed_received"] == result["livestock_output"] == 110.0
    assert result["received"] == [{"key": "a", "quantity": 50.0},
                                  {"key": "b", "quantity": 60.0}]


def feed(key, delivered, spare=0.0):
    return {"key": key, "quantity_available": delivered, "unit_price": 1.0,
            "delivered": delivered, "spare": spare}


def consumer(baseline):
    agent = FarmerProviderAgent()
    agent.setup({"role": "consumer", "baseline_orders": dict(baseline),
                 "last_orders": dict(baseline)})
    return agent


def test_producer_delivers_against_orders():
    agent = FarmerProviderAgent()
    agent.setup({"role": "producer", "base_yield": 100.0, "fixed_costs": 200.0, "margin": 0.1})
    orders = [{"key": "a", "quantity": 70.0}, {"key": "b", "quantity": 30.0}]
    full = agent.step({"orders": orders})
    assert full["stock"] == 100.0
    assert full["deliveries"] == orders
    short = agent.step({"orders": orders, "shipped": 100.0, "effects": {"capacity": 0.5}})
    assert short["stock"] == 50.0
    assert short["deliveries"] == [{"key": "a", "quantity": 35.0}, {"key": "b", "quantity": 15.0}]
    assert "deliveries" not in agent.step({})


def test_consumer_on_orders_feeds_its_need_and_reorders():
    result = consumer({"t": 80.0}).step({"orders": [], "upstream": [feed("t", 80.0)]})
    assert result == {
        "stock": 80.0, "feed_received": 80.0, "livestock_output": 80.0,
        "days_without_input": 0, "active": True, "last_orders": {"t": 80.0},
        "orders": [{"key": "t", "quantity": 80.0}],
    }


def test_consumer_keeps_surplus_and_orders_less():
    agent = consumer({"t": 80.0})
    first = agent.step({"orders": [], "upstream": [feed("t", 100.0)]})
    assert (first["stock"], first["livestock_output"]) == (100.0, 80.0)
    assert first["orders"] == [{"key": "t", "quantity": 60.0}]
    second = agent.step({"orders": [], "upstream": [feed("t", 60.0)]})
    assert (second["stock"], second["livestock_output"]) == (80.0, 80.0)
    assert second["orders"] == [{"key": "t", "quantity": 80.0}]


def test_consumer_feeds_from_stock_before_it_starves():
    agent = consumer({"t": 80.0})
    agent.step({"orders": [], "upstream": [feed("t", 100.0)]})
    cushioned = agent.step({"orders": [], "upstream": [feed("t", 0.0)]})
    assert (cushioned["livestock_output"], cushioned["days_without_input"]) == (20.0, 0)
    empty = agent.step({"orders": [], "upstream": [feed("t", 0.0)]})
    assert (empty["livestock_output"], empty["days_without_input"]) == (0.0, 1)


def test_consumer_shifts_a_shortfall_to_the_other_trader():
    result = consumer({"a": 40.0, "b": 40.0}).step({"orders": [], "upstream": [
        feed("a", 20.0), feed("b", 40.0, spare=30.0),
    ]})
    assert result["livestock_output"] == 60.0
    assert result["orders"] == [{"key": "a", "quantity": 40.0}, {"key": "b", "quantity": 60.0}]


def test_consumer_without_baseline_feeds_nothing():
    agent = FarmerProviderAgent()
    agent.setup({"role": "consumer"})
    result = agent.step({"orders": [], "upstream": [feed("t", 50.0)]})
    assert (result["stock"], result["livestock_output"]) == (50.0, 0.0)
    assert result["days_without_input"] == 1


def test_consumer_sources_need_no_recipient_count_on_orders():
    FarmerProviderAgent.spec.validate_step_input({
        "state": {"role": "consumer"}, "orders": [],
        "upstream": [{"key": "a", "quantity_available": 1.0, "unit_price": 1.0,
                      "delivered": 1.0}],
    })
