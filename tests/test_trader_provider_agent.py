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


def supply(key, delivered, price=10.0, offered=None, spare=0.0):
    return {"key": key, "quantity_available": delivered if offered is None else offered,
            "unit_price": price, "delivered": delivered, "spare": spare}


def trader(role, baseline, **state):
    agent = TraderProviderAgent()
    agent.setup({"role": role, "baseline_orders": dict(baseline),
                 "last_orders": dict(baseline), **state})
    return agent


def test_wholesaler_on_orders_receives_delivers_and_reorders():
    agent = trader("wholesaler", {"farms": 100.0}, storage_capacity=150.0,
                   fixed_costs=20.0, margin=0.1)
    result = agent.step({"orders": [{"key": "santos", "quantity": 70.0},
                                    {"key": "paranagua", "quantity": 30.0}],
                         "upstream": [supply("farms", 100.0)]})
    assert (result["stock"], result["quantity_available"]) == (100.0, 100.0)
    assert result["storage_utilization"] == pytest.approx(100.0 / 150.0)
    assert result["unit_price"] == pytest.approx((10.0 + 20.0 / 100.0) * 1.1)
    assert result["deliveries"] == [{"key": "santos", "quantity": 70.0},
                                    {"key": "paranagua", "quantity": 30.0}]
    assert result["orders"] == [{"key": "farms", "quantity": 100.0}]
    assert result["last_orders"] == {"farms": 100.0}
    assert "received" not in result


def test_wholesaler_keeps_what_was_not_ordered_and_orders_within_storage():
    agent = trader("wholesaler", {"farms": 100.0}, storage_capacity=110.0)
    orders = [{"key": "santos", "quantity": 50.0}, {"key": "paranagua", "quantity": 30.0}]
    first = agent.step({"orders": orders, "upstream": [supply("farms", 100.0)]})
    assert first["deliveries"] == orders
    assert first["orders"] == [{"key": "farms", "quantity": 90.0}]
    second = agent.step({"orders": orders, "shipped": 80.0,
                         "upstream": [supply("farms", 90.0)]})
    assert second["stock"] == 110.0
    assert second["storage_utilization"] == 1.0


def test_wholesaler_splits_a_short_supply_proportionally():
    agent = trader("wholesaler", {"farms": 100.0}, storage_capacity=150.0)
    result = agent.step({"orders": [{"key": "santos", "quantity": 70.0},
                                    {"key": "paranagua", "quantity": 30.0}],
                         "upstream": [supply("farms", 50.0)]})
    assert result["deliveries"] == [{"key": "santos", "quantity": 35.0},
                                    {"key": "paranagua", "quantity": 15.0}]
    assert result["orders"] == [{"key": "farms", "quantity": 100.0}]


def test_feed_trader_orders_its_baseline_without_a_limit():
    agent = trader("feed_trader", {"mill": 240.0})
    orders = [{"key": key, "quantity": 80.0} for key in ("poultry", "pigs", "dairy")]
    result = agent.step({"orders": orders, "upstream": [supply("mill", 300.0)]})
    assert result["stock"] == 300.0
    assert result["deliveries"] == orders
    assert result["orders"] == [{"key": "mill", "quantity": 240.0}]


def test_trader_price_is_weighted_by_what_was_delivered():
    agent = trader("feed_trader", {"a": 10.0, "b": 40.0}, fixed_costs=20.0, margin=0.1)
    result = agent.step({"orders": [], "upstream": [
        supply("a", 10.0, price=5.0, offered=100.0), supply("b", 40.0, price=10.0),
    ]})
    assert result["unit_price"] == pytest.approx((450.0 / 50.0 + 20.0 / 50.0) * 1.1)


def test_wholesaler_sources_need_no_base_yield_on_orders():
    TraderProviderAgent.spec.validate_step_input({
        "state": {"role": "wholesaler"}, "orders": [],
        "upstream": [{"key": "a", "quantity_available": 1.0, "unit_price": 1.0,
                      "delivered": 1.0}],
    })
